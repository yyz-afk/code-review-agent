"""BaseSpecialist 单元测试。

验证 v0.8.2 的抽象基类行为：
- 公共 review 流程（mock 模式 / LLM 模式）
- 公共 parse_finding 行为（越界保护、category fallback、错误处理）
- 工具函数 lang_tag / format_with_line_numbers
- 子类抽象方法强制实现
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from cra.agents.specialists.base import (
    BaseSpecialist,
    format_with_line_numbers,
    lang_tag,
)
from cra.core.models import AgentContext, Category, Finding, Severity

if TYPE_CHECKING:
    pass


# ============================================================
# 工具函数测试
# ============================================================


class TestLangTag:
    """lang_tag 扩展名映射。"""

    @pytest.mark.parametrize(
        "file_path,expected",
        [
            ("app.py", "python"),
            ("App.tsx", "tsx"),
            ("app.js", "javascript"),
            ("app.jsx", "jsx"),
            ("Main.java", "java"),
            ("main.go", "go"),
            ("readme.md", ""),
            ("Makefile", ""),
            ("no_ext", ""),
        ],
    )
    def test_extension_mapping(self, file_path: str, expected: str) -> None:
        assert lang_tag(file_path) == expected


class TestFormatWithLineNumbers:
    """行号前缀工具。"""

    def test_single_line(self) -> None:
        assert format_with_line_numbers("x = 1", 5) == "[5] x = 1"

    def test_multiple_lines(self) -> None:
        result = format_with_line_numbers("a\nb\nc", 10)
        assert result == "[10] a\n[11] b\n[12] c"

    def test_start_line_1(self) -> None:
        assert format_with_line_numbers("x", 1) == "[1] x"

    def test_empty_code(self) -> None:
        # splitlines() of "" → []
        assert format_with_line_numbers("", 1) == ""


# ============================================================
# BaseSpecialist 抽象方法强制
# ============================================================


class TestAbstractEnforcement:
    """BaseSpecialist 必须被子类继承且实现 _run_mock_rules。"""

    def test_cannot_instantiate_base_directly(self) -> None:
        """BaseSpecialist 是 ABC，不能直接实例化。"""
        from cra.agents.llm import LlmClient  # noqa: PLC0415

        with pytest.raises(TypeError):
            BaseSpecialist(LlmClient(enable_mock=True))  # type: ignore[abstract]

    def test_subclass_without_run_mock_rules_fails(self) -> None:
        """子类不实现 _run_mock_rules 不能实例化。"""
        from cra.agents.llm import LlmClient  # noqa: PLC0415

        class IncompleteAgent(BaseSpecialist):
            name = "incomplete"
            SYSTEM_PROMPT = "test"
            default_category = Category.MAINTAINABILITY
            # 缺 _run_mock_rules

        with pytest.raises(TypeError):
            IncompleteAgent(LlmClient(enable_mock=True))  # type: ignore[abstract]


# ============================================================
# parse_finding 行为契约
# ============================================================


def _make_ctx(
    start: int = 10,
    end: int = 20,
    file_path: str = "test.py",
) -> AgentContext:
    return AgentContext(
        file_path=file_path,
        file_content="x",  # 不重要
        original_start_line=start,
        original_end_line=end,
    )


def _make_agent() -> BaseSpecialist:
    """构造一个最小的可实例化 Agent。"""
    from cra.agents.llm import LlmClient  # noqa: PLC0415

    class TestAgent(BaseSpecialist):
        name = "test"
        SYSTEM_PROMPT = "test"
        default_category = Category.CORRECTNESS

        def _run_mock_rules(self, code: str, original_start: int, file_path: str) -> list[Finding]:
            return []

    return TestAgent(LlmClient(enable_mock=True))


class TestParseFinding:
    """parse_finding 公共行为。"""

    def test_normal_case(self) -> None:
        agent = _make_agent()
        ctx = _make_ctx(10, 20)
        item = {
            "severity": "high",
            "category": "correctness",
            "start_line": 15,
            "end_line": 16,
            "title": "test issue",
            "description": "desc",
            "suggestion": "fix it",
            "evidence": "see L15",
            "confidence": 0.9,
        }
        f = agent.parse_finding(item, ctx)
        assert f is not None
        assert f.agent == "test"  # 用 self.name
        assert f.severity == Severity.HIGH
        assert f.category == Category.CORRECTNESS
        assert f.start_line == 15
        assert f.end_line == 16
        assert f.confidence == 0.9

    def test_default_category_when_missing(self) -> None:
        """LLM 没给 category 时用 default_category。"""
        agent = _make_agent()
        ctx = _make_ctx(10, 20)
        item = {"severity": "low", "start_line": 10}
        f = agent.parse_finding(item, ctx)
        assert f is not None
        assert f.category == Category.CORRECTNESS

    def test_invalid_category_falls_back_to_default(self) -> None:
        """LLM 给的 category 无效时用 default_category。"""
        agent = _make_agent()
        ctx = _make_ctx(10, 20)
        item = {
            "severity": "low",
            "category": "unknown_category",
            "start_line": 10,
        }
        f = agent.parse_finding(item, ctx)
        assert f is not None
        assert f.category == Category.CORRECTNESS

    def test_line_out_of_range_clamped(self) -> None:
        """行号越界时截断到 [start, end]。"""
        agent = _make_agent()
        ctx = _make_ctx(10, 20)
        item = {
            "severity": "low",
            "start_line": 5,  # < 10
            "end_line": 100,  # > 20
        }
        f = agent.parse_finding(item, ctx)
        assert f is not None
        assert f.start_line == 10
        assert f.end_line == 20

    def test_end_less_than_start_fixed(self) -> None:
        agent = _make_agent()
        ctx = _make_ctx(10, 20)
        item = {
            "severity": "low",
            "start_line": 15,
            "end_line": 12,  # < start
        }
        f = agent.parse_finding(item, ctx)
        assert f is not None
        assert f.start_line == 15
        assert f.end_line == 15  # = start

    def test_title_truncated_to_200(self) -> None:
        agent = _make_agent()
        ctx = _make_ctx(10, 20)
        long_title = "x" * 300
        item = {"severity": "low", "start_line": 10, "title": long_title}
        f = agent.parse_finding(item, ctx)
        assert f is not None
        assert len(f.title) == 200

    def test_invalid_severity_returns_none(self) -> None:
        """无效 severity 不应该抛异常，返回 None。"""
        agent = _make_agent()
        ctx = _make_ctx(10, 20)
        item = {"severity": "invalid_severity", "start_line": 10}
        f = agent.parse_finding(item, ctx)
        assert f is None

    def test_invalid_confidence_returns_none(self) -> None:
        """confidence 非数字时返回 None。"""
        agent = _make_agent()
        ctx = _make_ctx(10, 20)
        item = {"severity": "low", "start_line": 10, "confidence": "high"}
        f = agent.parse_finding(item, ctx)
        assert f is None

    def test_missing_start_line_uses_ctx_default(self) -> None:
        agent = _make_agent()
        ctx = _make_ctx(10, 20)
        item = {"severity": "low"}  # 没 start_line
        f = agent.parse_finding(item, ctx)
        assert f is not None
        assert f.start_line == 10  # ctx.original_start_line


# ============================================================
# review() 主流程
# ============================================================


class TestReviewFlow:
    """review() 的 mock 模式和 LLM 模式分支。"""

    @pytest.mark.asyncio
    async def test_mock_mode_calls_run_mock_rules(self) -> None:
        """mock 模式下应调用子类的 _run_mock_rules。"""
        from cra.agents.llm import LlmClient  # noqa: PLC0415

        class TestAgent(BaseSpecialist):
            name = "test"
            SYSTEM_PROMPT = "test"
            default_category = Category.CORRECTNESS
            mock_called = False

            def _run_mock_rules(
                self, code: str, original_start: int, file_path: str
            ) -> list[Finding]:
                self.mock_called = True
                return [
                    Finding(
                        agent="test",
                        severity=Severity.LOW,
                        category=Category.CORRECTNESS,
                        file_path=file_path,
                        start_line=original_start,
                        end_line=original_start,
                        title="mock finding",
                        description="d",
                        confidence=0.5,
                    )
                ]

        agent = TestAgent(LlmClient(enable_mock=True))
        ctx = AgentContext(
            file_path="test.py",
            file_content="x = 1",
            original_start_line=1,
            original_end_line=1,
        )
        findings = await agent.review(ctx)
        assert agent.mock_called is True
        assert len(findings) == 1
        assert findings[0].title == "mock finding"


# ============================================================
# build_user_msg 默认与定制
# ============================================================


class TestBuildUserMsg:
    """build_user_msg 的默认实现 + 覆盖能力。"""

    def test_default_message_includes_line_range(self) -> None:
        agent = _make_agent()
        ctx = _make_ctx(10, 20)
        msg = agent.build_user_msg(ctx, "```\ncode\n```")
        assert "test.py" in msg
        assert "10" in msg
        assert "20" in msg
        assert "JSON" in msg or "json" in msg.lower()

    def test_override_allowed(self) -> None:
        """子类可以覆盖 build_user_msg（如 performance/architecture）。"""
        from cra.agents.llm import LlmClient  # noqa: PLC0415

        class CustomAgent(BaseSpecialist):
            name = "custom"
            SYSTEM_PROMPT = "x"
            default_category = Category.MAINTAINABILITY

            def build_user_msg(self, ctx: AgentContext, code_block: str) -> str:
                return f"CUSTOM: {ctx.file_path}"

            def _run_mock_rules(
                self, code: str, original_start: int, file_path: str
            ) -> list[Finding]:
                return []

        agent = CustomAgent(LlmClient(enable_mock=True))
        ctx = _make_ctx(file_path="foo.py")
        msg = agent.build_user_msg(ctx, "irrelevant")
        assert msg == "CUSTOM: foo.py"


# ============================================================
# 4 个真实 specialist 仍然能正常工作（继承验证）
# ============================================================


class TestRealSpecialistsInheritance:
    """验证 4 个真实 Agent 都正确继承了 BaseSpecialist。"""

    def test_correctness_is_base_specialist(self) -> None:
        from cra.agents.specialists.correctness import CorrectnessAgent

        assert issubclass(CorrectnessAgent, BaseSpecialist)

    def test_security_is_base_specialist(self) -> None:
        from cra.agents.specialists.security import SecurityAgent

        assert issubclass(SecurityAgent, BaseSpecialist)

    def test_performance_is_base_specialist(self) -> None:
        from cra.agents.specialists.performance import PerformanceAgent

        assert issubclass(PerformanceAgent, BaseSpecialist)

    def test_architecture_is_base_specialist(self) -> None:
        from cra.agents.specialists.architecture import ArchitectureAgent

        assert issubclass(ArchitectureAgent, BaseSpecialist)

    def test_all_share_same_review_implementation(self) -> None:
        """4 个 Agent 的 review 方法应该来自 BaseSpecialist（同一份代码）。"""
        from cra.agents.specialists.correctness import CorrectnessAgent
        from cra.agents.specialists.security import SecurityAgent

        # review 是从 BaseSpecialist 继承的，没被覆盖（除 performance/architecture 定制了 build_user_msg）
        for cls in (CorrectnessAgent, SecurityAgent):
            assert "review" not in cls.__dict__, f"{cls.__name__} 不应该覆盖 review()"
            assert cls.review is BaseSpecialist.review

    def test_all_share_same_parse_finding(self) -> None:
        """parse_finding 应该完全继承自基类（无覆盖）。"""
        from cra.agents.specialists.architecture import ArchitectureAgent
        from cra.agents.specialists.correctness import CorrectnessAgent
        from cra.agents.specialists.performance import PerformanceAgent
        from cra.agents.specialists.security import SecurityAgent

        for cls in (CorrectnessAgent, SecurityAgent, PerformanceAgent, ArchitectureAgent):
            assert "parse_finding" not in cls.__dict__, f"{cls.__name__} 不应该覆盖 parse_finding()"
