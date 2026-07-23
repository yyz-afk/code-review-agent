"""审查编排器：Phase 1 的简化版本。

Phase 1 范围（YAGNI）：
- 单 Agent（CorrectnessAgent）
- v0.4：多文件并行审查（asyncio.gather）
- 无 LangGraph 编排（Phase 2 再上）
- Critic 验证层（v0.2：去重 + 置信度过滤）

行号映射：以 hunk 为单位，保留原始文件行号。
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cra.agents.llm import LlmClient
from cra.agents.specialists.correctness import CorrectnessAgent
from cra.agents.specialists.security import SecurityAgent
from cra.context.ast_engine import get_ast_engine
from cra.context.diff_parser import DiffParser
from cra.core.models import (
    AgentContext,
    Finding,
    Hunk,
    ReviewResult,
    ReviewStats,
    Severity,
    SymbolInfo,
)
from cra.core.models import _is_noise_file

logger = logging.getLogger(__name__)


@dataclass
class ReviewConfig:
    """审查配置。"""

    confidence_threshold: float = 0.5
    max_findings_per_file: int = 5
    skip_noise_files: bool = True
    max_concurrent_files: int = 5  # v0.4：并行文件数上限（防限流）
    # v0.5：启用的 Agent 列表（顺序执行，可并行）
    enabled_agents: list[str] = field(
        default_factory=lambda: ["correctness", "security"]
    )


class ReviewOrchestrator:
    """审查编排器（Phase 1）。"""

    def __init__(
        self,
        llm_client: LlmClient | None = None,
        config: ReviewConfig | None = None,
    ) -> None:
        self.llm = llm_client or _get_default_llm()
        self.config = config or ReviewConfig()
        self.diff_parser = DiffParser()
        self.ast_engine = get_ast_engine()

        # Agent 注册表：name → instance
        self._agents: dict[str, Any] = {
            "correctness": CorrectnessAgent(self.llm),
            "security": SecurityAgent(self.llm),
        }

    async def review_diff(self, diff_text: str) -> ReviewResult:
        """审查 diff 文本。"""
        files = self.diff_parser.parse_unified_diff(diff_text)
        return await self._review_files(files, base_ref="diff", head_ref="head")

    async def review_git(
        self, repo_path: Path, base: str, head: str
    ) -> ReviewResult:
        """审查 Git 仓库中 base...head 的变更。"""
        diff = self.diff_parser.get_diff_from_git(repo_path, base, head)
        return await self._review_files(diff.files, base, head)

    async def _review_files(
        self, files: list, base_ref: str, head_ref: str
    ) -> ReviewResult:
        """审查文件列表（v0.4：并行处理多文件）。"""
        start = time.perf_counter()

        # 过滤 + 收集要审查的文件
        tasks: list[asyncio.Task] = []
        task_files: list[str] = []  # 与 tasks 一一对应，便于错误归属

        for file_change in files:
            if self.config.skip_noise_files and _is_noise_file(file_change.path):
                logger.debug("Skip noise file: %s", file_change.path)
                continue
            if not file_change.hunks:
                continue
            language = self.ast_engine.get_language(file_change.path)
            if language is None:
                logger.debug(
                    "Skip unsupported language file: %s", file_change.path
                )
                continue

            # 用 lambda 捕获循环变量需要默认参数
            tasks.append(asyncio.create_task(
                self._safe_review_single_file(
                    file_change.path, file_change.hunks, language
                )
            ))
            task_files.append(file_change.path)

        # 并行执行（单 Agent 内的文件级并行）
        # 设置并发上限避免触发 LLM 限流（默认 5）
        semaphore = asyncio.Semaphore(self.config.max_concurrent_files)
        results = await asyncio.gather(
            *[_limit_concurrency(t, semaphore) for t in tasks],
            return_exceptions=False,
        )

        # 聚合结果
        raw_findings: list[Finding] = []
        errors: list[str] = []
        files_reviewed = 0

        for file_path, result in zip(task_files, results, strict=False):
            file_findings, file_errors = result
            raw_findings.extend(file_findings)
            errors.extend(file_errors)
            if not file_errors:
                files_reviewed += 1
            else:
                # 即使部分出错，仍算审查过（前提是有 findings 或无致命错误）
                if file_findings:
                    files_reviewed += 1

        # Critic 层：去重 + 过滤
        deduped = self._dedup_findings(raw_findings)
        filtered = self._filter_by_confidence(deduped)

        elapsed = time.perf_counter() - start
        stats = self._build_stats(filtered, files_reviewed, elapsed, errors)

        return ReviewResult(
            base_ref=base_ref,
            head_ref=head_ref,
            findings=filtered,
            stats=stats,
            errors=errors,
        )

    async def _safe_review_single_file(
        self, file_path: str, hunks: list[Hunk], language: str
    ) -> tuple[list[Finding], list[str]]:
        """带异常隔离的文件审查，返回 (findings, errors)。"""
        try:
            findings = await self._review_single_file(
                file_path, hunks, language
            )
            return findings, []
        except Exception as e:  # noqa: BLE001
            logger.exception("Failed to review %s", file_path)
            return [], [f"{file_path}: {e}"]

    async def _review_single_file(
        self, file_path: str, hunks: list[Hunk], language: str
    ) -> list[Finding]:
        """审查单个文件的多个 hunk（v0.5：多 Agent 并行）。"""
        all_findings: list[Finding] = []

        # 每个 hunk × 每个启用 Agent → 一个审查任务
        tasks: list[asyncio.Task] = []
        task_meta: list[tuple[str, str]] = []  # (hunk_id, agent_name)

        for hunk_idx, hunk in enumerate(hunks):
            numbered_lines = _parse_hunk_to_lines(hunk)
            if not numbered_lines:
                continue

            original_start = numbered_lines[0][0]
            original_end = numbered_lines[-1][0]
            code_content = "\n".join(line for _, line in numbered_lines)

            changed_symbols = self._extract_symbols_from_hunk(
                code_content, original_start, file_path, language
            )

            ctx = AgentContext(
                file_path=file_path,
                file_content=code_content,
                original_start_line=original_start,
                original_end_line=original_end,
                changed_symbols=changed_symbols,
                diff_hunks=[hunk],
            )

            # 为每个启用的 Agent 创建任务
            for agent_name in self.config.enabled_agents:
                agent = self._agents.get(agent_name)
                if agent is None:
                    continue
                tasks.append(asyncio.create_task(agent.review(ctx)))
                task_meta.append((f"hunk{hunk_idx}", agent_name))

        # 并行执行（同文件内的多 hunk × 多 Agent）
        semaphore = asyncio.Semaphore(self.config.max_concurrent_files)
        results = await asyncio.gather(
            *[_limit_concurrency(t, semaphore) for t in tasks],
            return_exceptions=True,
        )

        for (hunk_id, agent_name), result in zip(task_meta, results, strict=False):
            if isinstance(result, Exception):
                logger.warning(
                    "Agent %s failed on %s/%s: %s",
                    agent_name, file_path, hunk_id, result,
                )
                continue
            if isinstance(result, list):
                all_findings.extend(result)

        # 按文件截断
        if len(all_findings) > self.config.max_findings_per_file:
            all_findings = sorted(all_findings, key=lambda f: f.severity.rank)
            all_findings = all_findings[: self.config.max_findings_per_file]

        return all_findings

    def _extract_symbols_from_hunk(
        self,
        code: str,
        original_start: int,
        file_path: str,
        language: str,
    ) -> list[SymbolInfo]:
        """从 hunk 重建代码中识别符号，并修正为原始文件行号。

        AST 解析的是 hunk 内的相对行号（1-based），
        需要加上 (original_start - 1) 偏移才能得到原始文件行号。
        """
        try:
            symbols = self.ast_engine.extract_symbols(code, language, file_path)
        except Exception:  # noqa: BLE001
            return []

        # 修正行号
        offset = original_start - 1
        fixed: list[SymbolInfo] = []
        for sym in symbols:
            fixed.append(sym.model_copy(update={
                "start_line": sym.start_line + offset,
                "end_line": sym.end_line + offset,
            }))
        return fixed

    def _dedup_findings(self, findings: list[Finding]) -> list[Finding]:
        """去重：相同 file + 相近行号 + 相同 title 视为重复。

        保留置信度最高的那条。
        """
        if not findings:
            return []

        # 按 (file, title, 近似行号) 聚类
        groups: dict[tuple, Finding] = {}
        for f in findings:
            # 行号 ±3 视为同一位置
            line_bucket = f.start_line // 3
            key = (f.file_path, f.title.strip().lower(), line_bucket)
            existing = groups.get(key)
            if existing is None or f.confidence > existing.confidence:
                groups[key] = f
        return list(groups.values())

    def _filter_by_confidence(self, findings: list[Finding]) -> list[Finding]:
        """按置信度阈值过滤。"""
        threshold = self.config.confidence_threshold
        return [f for f in findings if f.confidence >= threshold]

    def _build_stats(
        self,
        findings: list[Finding],
        files_reviewed: int,
        elapsed: float,
        errors: list[str],
    ) -> ReviewStats:
        by_sev: dict[str, int] = {}
        by_cat: dict[str, int] = {}
        for f in findings:
            by_sev[f.severity.value] = by_sev.get(f.severity.value, 0) + 1
            by_cat[f.category.value] = by_cat.get(f.category.value, 0) + 1

        return ReviewStats(
            files_reviewed=files_reviewed,
            agents_run=1,
            duration_sec=round(elapsed, 3),
            tokens_used=self.llm.stats.total_tokens,
            cost_usd=round(self.llm.stats.total_cost, 4),
            findings_by_severity=by_sev,
            findings_by_category=by_cat,
        )


def _parse_hunk_to_lines(hunk: Hunk) -> list[tuple[int, str]]:
    """解析 hunk 内容，返回带原始行号的代码行列表。

    Returns:
        [(original_line_no, code_line), ...]
        original_line_no 是该行在原始（新）文件中的行号。

    解析规则：
    - "@@ ..." 是 hunk header，跳过
    - "+xxx" 是新增行，行号 = new_start 起算
    - " xxx" 是上下文行，行号 = new_start 起算
    - "-xxx" 是删除行，不影响新文件行号
    - "--- " / "+++ " 是文件头，跳过
    """
    result: list[tuple[int, str]] = []
    current_line = hunk.new_start

    for line in hunk.content.splitlines():
        if (
            line.startswith("@@")
            or line.startswith("--- ")
            or line.startswith("+++ ")
        ):
            continue
        if line.startswith("+"):
            result.append((current_line, line[1:]))
            current_line += 1
        elif line.startswith("-"):
            # 删除行不影响新文件行号
            continue
        elif line.startswith(" "):
            result.append((current_line, line[1:]))
            current_line += 1
        # 空行或其他也按上下文处理
        elif line == "":
            result.append((current_line, ""))
            current_line += 1

    return result


def _get_default_llm() -> LlmClient:
    """获取默认 LLM 客户端。"""
    from cra.agents.llm import get_llm_client  # noqa: PLC0415

    return get_llm_client()


async def _limit_concurrency(task: asyncio.Task, semaphore: asyncio.Semaphore) -> Any:
    """用 semaphore 限制并发：获取→等待 task→释放。

    asyncio.gather 会立刻创建所有协程，semaphore 限制真正执行的并发数。
    """
    async with semaphore:
        return await task
