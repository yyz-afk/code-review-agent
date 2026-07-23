"""Performance Agent：专项性能审查。

聚焦于性能反模式：N+1 查询、循环内 IO、资源泄漏、不必要计算等。
与 CorrectnessAgent 分工：correctness 查"运行时错误"，performance 查"性能瓶颈"。

Phase 1 v0.6：作为第三个专项 Agent 加入 Orchestrator。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cra.core.models import AgentContext, Category, Finding, Severity

if TYPE_CHECKING:
    from cra.agents.llm import LlmClient

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是代码性能审查专家，专注于发现会导致性能问题的反模式。

## 核心原则

1. **证据原则**：必须有量级估算或明确反模式，不凭感觉报告性能问题。
2. **量化**：说明预期数据规模（如"循环可能 > 1000 次"）。
3. **可操作**：给出具体优化方案与替代代码。

## 检查清单（按优先级）

### Critical / High（明显性能 Bug）
- **N+1 查询**：循环内执行数据库/HTTP 查询
- **资源泄漏**：未关闭的连接/文件/锁
- **同步 IO 阻塞异步**：async 函数中调用同步 IO
- **大集合低效操作**：list 线性查找（应用 set）、多次遍历

### Medium（值得优化的反模式）
- **不必要的嵌套循环**：O(n²) 或更差，且 n 较大
- **循环内重复计算**：可提到循环外的常量
- **低效字符串拼接**：循环内 `+=`（应用 join）
- **缺少索引的数据库查询**：WHERE/JOIN 字段无索引（结合 schema）
- **未批处理**：可批量但逐个调用

### Low（微优化）
- **不必要的函数调用**：循环内的 lambda/属性查找
- **过大的全局变量**：模块加载时初始化大对象

## 输出规范

输出严格 JSON 数组：
```json
{
  "severity": "critical|high|medium|low|info",
  "category": "performance",
  "start_line": 123,
  "end_line": 125,
  "title": "一句话总结（含反模式名）",
  "description": "性能影响 + 数据规模估算",
  "suggestion": "优化代码（用对应语言代码块标签）",
  "evidence": "具体反模式位置 + 复杂度分析",
  "confidence": 0.0
}
```

无问题返回 `[]`。**绝对不要**报告无依据的微优化。
"""


# ============================================================
# Mock 规则匹配（无 API Key 时降级）
# ============================================================

_MOCK_PATTERNS: list[tuple[str, Severity, str, str, float]] = [
    # N+1：循环内的数据库调用（execute/query）
    (
        "for ",
        Severity.HIGH,
        "疑似 N+1 查询（循环内 DB 调用）",
        "循环内执行数据库查询可能导致 N+1，应改为批量查询。",
        0.7,
    ),
    # list 内 in 查找（应为 set）
    (
        "_LIST = [",
        Severity.MEDIUM,
        "list 用于 in 查找应改为 set",
        "list 的 in 操作是 O(n)，set 是 O(1)。如果用于成员判断，应用 set。",
        0.6,
    ),
    # 同步 time.sleep 在 async
    (
        "asyncio.sleep",
        Severity.LOW,
        "提示：确认是否需要异步 sleep",
        "在 async 函数中应用 asyncio.sleep，不要用 time.sleep。",
        0.5,
    ),
]


def _run_mock_rules(
    code: str, original_start: int, file_path: str
) -> list[Finding]:
    """Mock 模式：简单规则匹配。

    真实的性能问题需要上下文理解，mock 模式只能做模式匹配。
    """
    findings: list[Finding] = []
    lines = code.splitlines()

    # N+1：循环 + execute/query
    in_loop = False
    for i, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith(("for ", "while ")):
            in_loop = True
            # 检查循环体内是否有 DB 调用（看后续 5 行）
            for j in range(i, min(i + 5, len(lines) + 1)):
                inner = lines[j - 1] if j - 1 < len(lines) else ""
                if any(p in inner for p in (".execute(", ".query(", "fetchone", "fetchall")):
                    orig_line = original_start + j - 1
                    findings.append(Finding(
                        agent="performance",
                        severity=Severity.HIGH,
                        category=Category.PERFORMANCE,
                        file_path=file_path,
                        start_line=orig_line,
                        end_line=orig_line,
                        title="疑似 N+1 查询（循环内 DB 调用）",
                        description=(
                            f"循环（L{original_start + i - 1}）内执行 DB 调用 "
                            f"(L{orig_line})，可能导致 N+1 查询。"
                            "如果循环次数可能 > 10，应改为批量查询。"
                        ),
                        evidence=f"循环 + DB 调用：\n  L{original_start + i - 1}: {lines[i-1].strip()}\n  L{orig_line}: {inner.strip()}",
                        confidence=0.75,
                    ))
                    break
            in_loop = False

    return findings


# ============================================================
# Agent 实现
# ============================================================


class PerformanceAgent:
    """性能审查 Agent。"""

    name = "performance"

    def __init__(self, llm_client: "LlmClient") -> None:
        self.llm = llm_client

    async def review(self, ctx: AgentContext) -> list[Finding]:
        """审查给定的上下文。"""
        if self.llm.mock_mode:
            return _run_mock_rules(
                ctx.file_content, ctx.original_start_line, ctx.file_path
            )

        from cra.agents.specialists.correctness import (  # noqa: PLC0415
            _format_with_line_numbers,
        )

        numbered_code = _format_with_line_numbers(
            ctx.file_content, ctx.original_start_line
        )

        ext = ctx.file_path.rsplit(".", 1)[-1].lower() if "." in ctx.file_path else ""
        lang_tag = {
            "py": "python", "js": "javascript", "ts": "typescript",
            "java": "java", "go": "go",
        }.get(ext, "")
        code_block = (
            f"```{lang_tag}\n{numbered_code}\n```"
            if lang_tag else f"```\n{numbered_code}\n```"
        )

        user_msg = (
            f"文件：{ctx.file_path}\n"
            f"代码片段位于原文件第 {ctx.original_start_line}-"
            f"{ctx.original_end_line} 行。\n\n"
            f"{code_block}\n\n"
            f"进行性能审查。输出 JSON findings 数组。"
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        parsed, response = await self.llm.complete_json(messages)
        if not isinstance(parsed, list):
            logger.warning(
                "Performance LLM returned non-array: %s",
                (response.content[:200] if response.content else "empty"),
            )
            return []

        findings: list[Finding] = []
        for item in parsed:
            finding = self._parse_finding(item, ctx)
            if finding:
                findings.append(finding)
        return findings

    @staticmethod
    def _parse_finding(item: dict, ctx: AgentContext) -> Finding | None:
        try:
            sev_str = str(item.get("severity", "info")).lower()
            severity = Severity(sev_str)
            start_line = int(item.get("start_line", ctx.original_start_line))
            end_line = int(item.get("end_line", start_line))
            start_line = max(start_line, ctx.original_start_line)
            end_line = min(end_line, ctx.original_end_line)
            if end_line < start_line:
                end_line = start_line
            return Finding(
                agent="performance",
                severity=severity,
                category=Category.PERFORMANCE,
                file_path=ctx.file_path,
                start_line=start_line,
                end_line=end_line,
                title=str(item.get("title", "Untitled"))[:200],
                description=str(item.get("description", "")),
                suggestion=item.get("suggestion"),
                evidence=item.get("evidence"),
                confidence=float(item.get("confidence", 0.5)),
            )
        except (ValueError, KeyError, TypeError) as e:
            logger.warning("Failed to parse performance finding %r: %s", item, e)
            return None
