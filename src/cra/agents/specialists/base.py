"""Specialist Agent 基类：抽取 4 个专项 Agent 的公共逻辑。

v0.8.2 引入。在此之前，correctness/security/performance/architecture
4 个 Agent 各自重复实现了 review() + _parse_finding() + 语言标签映射 + LLM 调用，
违反 DRY。本模块抽出公共骨架，子类只需声明：

- ``name``: Agent 名（也用作 Finding.agent）
- ``SYSTEM_PROMPT``: 系统 prompt
- ``default_category``: 默认类别（LLM 未指定时使用）
- ``_run_mock_rules()``: mock 模式下的规则匹配

设计原则：
- **OCP**: 新增 Agent 只需继承 + 实现抽象方法，不修改本基类
- **DRY**: review 流程 + LLM 调用 + finding 解析只在基类实现一次
- **KISS**: 不引入不必要的抽象层（如 AgentState、Tool 接口等）
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from cra.core.models import AgentContext, Category, Finding, Severity

if TYPE_CHECKING:
    from cra.agents.llm import LlmClient

logger = logging.getLogger(__name__)


# ============================================================
# 公共工具函数
# ============================================================


# 扩展名 → markdown 代码块语言标签
_LANG_TAG_BY_EXT: dict[str, str] = {
    "py": "python",
    "js": "javascript",
    "jsx": "jsx",
    "ts": "typescript",
    "tsx": "tsx",
    "java": "java",
    "go": "go",
}


def lang_tag(file_path: str) -> str:
    """从文件扩展名推断 markdown 代码块语言标签。

    用于 LLM prompt 中的代码块标记，让 LLM 用正确语法解析代码。
    """
    ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else ""
    return _LANG_TAG_BY_EXT.get(ext, "")


def format_with_line_numbers(code: str, start_line: int) -> str:
    """给代码每行加 ``[N]`` 前缀（N 是原始文件行号）。

    让 LLM 输出的 ``start_line`` 直接对应原始文件行号，
    无需后续映射。

    示例::

        [4] query = f"SELECT ..."
        [5] cursor.execute(query)
    """
    return "\n".join(f"[{start_line + i}] {line}" for i, line in enumerate(code.splitlines()))


# ============================================================
# BaseSpecialist 抽象基类
# ============================================================


class BaseSpecialist(ABC):
    """专项 Agent 基类（template method 模式）。

    子类必须声明：
        - ``name``: str
        - ``SYSTEM_PROMPT``: str
        - ``default_category``: Category

    子类必须实现：
        - ``_run_mock_rules(code, original_start, file_path) -> list[Finding]``

    子类可选覆盖：
        - ``build_user_msg(ctx, code_block) -> str``: 自定义 user message
    """

    # 类属性（子类必须覆盖）
    name: str = ""
    SYSTEM_PROMPT: str = ""
    default_category: Category = Category.MAINTAINABILITY

    def __init__(self, llm_client: LlmClient) -> None:
        self.llm = llm_client

    # ============================================================
    # 主流程（template method）
    # ============================================================

    async def review(self, ctx: AgentContext) -> list[Finding]:
        """审查给定的上下文。

        流程：
        1. mock 模式 → 调用子类 ``_run_mock_rules``
        2. 真实 LLM → 构造 prompt → 调用 → 解析 JSON
        """
        if self.llm.mock_mode:
            return self._run_mock_rules(ctx.file_content, ctx.original_start_line, ctx.file_path)

        numbered = format_with_line_numbers(ctx.file_content, ctx.original_start_line)
        tag = lang_tag(ctx.file_path)
        code_block = f"```{tag}\n{numbered}\n```" if tag else f"```\n{numbered}\n```"

        user_msg = self.build_user_msg(ctx, code_block)
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        parsed, response = await self.llm.complete_json(messages)
        if not isinstance(parsed, list):
            logger.warning(
                "%s LLM returned non-array: %s",
                self.name,
                (response.content[:200] if response.content else "empty"),
            )
            return []

        findings: list[Finding] = []
        for item in parsed:
            finding = self.parse_finding(item, ctx)
            if finding:
                findings.append(finding)
        return findings

    # ============================================================
    # 可覆盖的钩子
    # ============================================================

    def build_user_msg(self, ctx: AgentContext, code_block: str) -> str:
        """构造 user message。

        默认实现给出标准审查 prompt。子类可覆盖以定制指令
        （如 security/performance/architecture 各自的审查重点）。
        """
        return (
            f"文件：{ctx.file_path}\n"
            f"以下代码片段在原文件中位于第 {ctx.original_start_line}-"
            f"{ctx.original_end_line} 行。\n\n"
            f"{code_block}\n\n"
            f"输出 JSON findings 数组。start_line 必须是代码片段中 "
            f"显示的行号（方括号内的数字）。"
        )

    def parse_finding(self, item: dict, ctx: AgentContext) -> Finding | None:
        """把 LLM 返回的 dict 解析为 Finding。

        - 行号越界保护：截断到 ``[original_start_line, original_end_line]``
        - category 优先用 LLM 返回值，无效则用 ``default_category``
        - 解析失败返回 None（不抛异常，让上层继续处理其他 finding）
        """
        try:
            sev_str = str(item.get("severity", "info")).lower()
            severity = Severity(sev_str)

            # category: LLM 指定 → 用之；否则用 default_category
            category = self.default_category
            category_str = str(item.get("category", "")).lower()
            if category_str:
                try:
                    category = Category(category_str)
                except ValueError:
                    pass  # 保持默认

            start_line = int(item.get("start_line", ctx.original_start_line))
            end_line = int(item.get("end_line", start_line))

            # 越界保护
            start_line = max(start_line, ctx.original_start_line)
            end_line = min(end_line, ctx.original_end_line)
            if end_line < start_line:
                end_line = start_line

            return Finding(
                agent=self.name,
                severity=severity,
                category=category,
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
            logger.warning(
                "%s failed to parse finding %r: %s",
                self.name,
                item,
                e,
            )
            return None

    # ============================================================
    # 抽象方法：子类必须实现
    # ============================================================

    @abstractmethod
    def _run_mock_rules(self, code: str, original_start: int, file_path: str) -> list[Finding]:
        """Mock 模式（无 API Key）下的规则匹配。

        必须返回带原始文件行号的 finding。
        """
        ...
