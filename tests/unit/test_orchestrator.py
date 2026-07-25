"""Orchestrator 单元测试：聚焦行号映射与去重逻辑（不依赖 LLM）。

这些都是 Phase 1 修复的核心逻辑，必须有测试覆盖以防回归。
"""

from __future__ import annotations

import pytest

from cra.agents.orchestrator import (
    ReviewOrchestrator,
    _parse_hunk_to_lines,
)
from cra.core.models import (
    Category,
    Finding,
    Hunk,
    Severity,
)

# ============================================================
# _parse_hunk_to_lines：hunk → 原始行号映射（核心修复点）
# ============================================================


class TestParseHunkToLines:
    """测试 hunk 内容到带原始行号的代码行的转换。"""

    def test_new_start_is_respected(self) -> None:
        """hunk.new_start 应该作为代码首行的原始行号。"""
        hunk = Hunk(
            old_start=1, old_lines=2, new_start=10, new_lines=3,
            content="""\
@@ -1,2 +10,3 @@
 ctx
-old
+new1
+new2""",
        )
        lines = _parse_hunk_to_lines(hunk)
        # 应该是 [(10, ctx), (11, new1), (12, new2)]
        assert lines[0] == (10, "ctx")
        assert lines[1] == (11, "new1")
        assert lines[2] == (12, "new2")

    def test_deleted_lines_do_not_advance_line_number(self) -> None:
        """删除行（-）不应该让新文件行号前进。"""
        hunk = Hunk(
            old_start=10, old_lines=3, new_start=10, new_lines=2,
            content="""\
@@ -10,3 +10,2 @@
 ctx
-deleted
 kept""",
        )
        lines = _parse_hunk_to_lines(hunk)
        # ctx 在 L10，deleted 跳过，kept 在 L11（不是 L12）
        assert (10, "ctx") in lines
        assert (11, "kept") in lines
        assert len(lines) == 2

    def test_empty_lines_are_preserved(self) -> None:
        """空行（无前缀）应该按上下文处理。"""
        hunk = Hunk(
            old_start=1, old_lines=3, new_start=1, new_lines=3,
            content="""\
@@ -1,3 +1,3 @@
 line1

 line3""",
        )
        lines = _parse_hunk_to_lines(hunk)
        # 3 行：L1, L2, L3（中间空行保留）
        assert len(lines) == 3

    def test_skip_hunk_header_and_file_headers(self) -> None:
        """@@/---/+++ 行应该被跳过。"""
        hunk = Hunk(
            old_start=1, old_lines=1, new_start=1, new_lines=1,
            content="""\
@@ -1,1 +1,1 @@
-old
+new""",
        )
        lines = _parse_hunk_to_lines(hunk)
        # 只应该有 1 行（new），header 被跳过
        assert len(lines) == 1
        assert lines[0] == (1, "new")

    def test_empty_hunk_returns_empty_list(self) -> None:
        hunk = Hunk(
            old_start=1, old_lines=0, new_start=1, new_lines=0,
            content="@@ -1,0 +1,0 @@",
        )
        assert _parse_hunk_to_lines(hunk) == []


# ============================================================
# Fixture 与工具：供后续测试使用
# ============================================================


@pytest.fixture
def orchestrator_no_llm() -> ReviewOrchestrator:
    """构造不连真实 LLM 的 Orchestrator（mock 模式）。"""
    from cra.agents.llm import LlmClient  # noqa: PLC0415

    mock_llm = LlmClient(enable_mock=True)
    return ReviewOrchestrator(llm_client=mock_llm)


def _make_finding(
    file: str = "a.py",
    line: int = 10,
    title: str = "test issue",
    confidence: float = 0.8,
    severity: Severity = Severity.MEDIUM,
) -> Finding:
    """便捷构造 Finding。"""
    from uuid import uuid4  # noqa: PLC0415

    return Finding(
        id=uuid4(),
        agent="correctness",
        severity=severity,
        category=Category.CORRECTNESS,
        file_path=file,
        start_line=line,
        end_line=line,
        title=title,
        description="d",
        confidence=confidence,
    )


# 注：v0.8.1 起，_dedup_findings 和 _filter_by_confidence 已从 Orchestrator 删除
# （去重/过滤由独立 CriticAgent 负责，测试见 test_critic.py）


# ============================================================
# _extract_symbols_from_hunk：AST 行号偏移修正
# ============================================================


class TestSymbolLineOffset:
    """AST 识别的符号行号偏移修正。"""

    def test_offset_applied(self, orchestrator_no_llm: ReviewOrchestrator) -> None:
        """hunk 从 L10 开始，符号 func 在 hunk 内 L1-L2，应修正为 L10-L11。"""
        code = "def func():\n    return 1"
        symbols = orchestrator_no_llm._extract_symbols_from_hunk(
            code=code,
            original_start=10,
            file_path="test.py",
            language="python",
        )
        assert len(symbols) == 1
        assert symbols[0].name == "func"
        assert symbols[0].start_line == 10
        assert symbols[0].end_line == 11

    def test_offset_zero_for_first_line(
        self, orchestrator_no_llm: ReviewOrchestrator
    ) -> None:
        """original_start=1 时，偏移为 0。"""
        code = "def func():\n    pass"
        symbols = orchestrator_no_llm._extract_symbols_from_hunk(
            code=code, original_start=1, file_path="t.py", language="python"
        )
        assert symbols[0].start_line == 1
