"""PerformanceAgent / ArchitectureAgent 单元测试。"""

from __future__ import annotations

import pytest

from cra.agents.llm import LlmClient
from cra.agents.specialists.architecture import (
    ArchitectureAgent,
)
from cra.agents.specialists.architecture import (
    _run_mock_rules as arch_mock,
)
from cra.agents.specialists.performance import (
    PerformanceAgent,
)
from cra.agents.specialists.performance import (
    _run_mock_rules as perf_mock,
)
from cra.core.models import AgentContext


@pytest.fixture
def mock_llm() -> LlmClient:
    return LlmClient(enable_mock=True)


@pytest.fixture
def perf_agent(mock_llm: LlmClient) -> PerformanceAgent:
    return PerformanceAgent(mock_llm)


@pytest.fixture
def arch_agent(mock_llm: LlmClient) -> ArchitectureAgent:
    return ArchitectureAgent(mock_llm)


# ============================================================
# PerformanceAgent
# ============================================================


class TestPerformanceMockRules:
    def test_detects_n_plus_1_pattern(self) -> None:
        """循环 + DB 调用 → N+1 警告。"""
        code = """\
for user in users:
    cur.execute(f"SELECT * FROM orders WHERE uid = {user.id}")
"""
        findings = perf_mock(code, original_start=10, file_path="db.py")
        assert len(findings) == 1
        assert findings[0].agent == "performance"
        assert findings[0].category.value == "performance"
        assert findings[0].severity.value == "high"

    def test_no_false_positive_without_loop(self) -> None:
        code = 'cur.execute("SELECT 1")'
        findings = perf_mock(code, 1, "x.py")
        assert findings == []

    def test_no_false_positive_on_isolated_db_call(self) -> None:
        code = """\
def get(x):
    cur.execute(f"SELECT * FROM u WHERE id = {x}")
"""
        findings = perf_mock(code, 1, "x.py")
        # 函数体内没有循环，不应触发 N+1
        assert findings == []


class TestPerformanceAgentInterface:
    @pytest.mark.asyncio
    async def test_review_uses_mock(self, perf_agent: PerformanceAgent) -> None:
        ctx = AgentContext(
            file_path="test.py",
            file_content='for u in users:\n    cur.execute("SELECT 1")',
            original_start_line=1,
            original_end_line=2,
        )
        findings = await perf_agent.review(ctx)
        assert all(f.agent == "performance" for f in findings)
        assert all(f.category.value == "performance" for f in findings)

    def test_name(self, perf_agent: PerformanceAgent) -> None:
        assert perf_agent.name == "performance"


# ============================================================
# ArchitectureAgent
# ============================================================


class TestArchitectureMockRules:
    def test_detects_long_function(self) -> None:
        """超过 50 行的函数应触发警告。"""
        code = "def long_func():\n" + "\n".join(["    x = 1"] * 55)
        findings = arch_mock(code, 1, "big.py")
        assert len(findings) >= 1
        assert findings[0].agent == "architecture"
        assert findings[0].category.value == "architecture"

    def test_short_function_no_warning(self) -> None:
        code = "def small():\n    return 1\n"
        findings = arch_mock(code, 1, "x.py")
        assert findings == []


class TestArchitectureAgentInterface:
    @pytest.mark.asyncio
    async def test_review_uses_mock(self, arch_agent: ArchitectureAgent) -> None:
        ctx = AgentContext(
            file_path="test.py",
            file_content="def x():\n    pass\n",
            original_start_line=1,
            original_end_line=2,
        )
        # 短函数，应该没有 finding
        findings = await arch_agent.review(ctx)
        assert findings == []

    def test_name(self, arch_agent: ArchitectureAgent) -> None:
        assert arch_agent.name == "architecture"
