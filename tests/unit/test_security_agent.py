"""SecurityAgent 单元测试。"""

from __future__ import annotations

import pytest

from cra.agents.llm import LlmClient
from cra.agents.specialists.security import (
    SecurityAgent,
    _run_mock_rules,
)
from cra.core.models import AgentContext


@pytest.fixture
def mock_llm() -> LlmClient:
    return LlmClient(enable_mock=True)


@pytest.fixture
def agent(mock_llm: LlmClient) -> SecurityAgent:
    return SecurityAgent(mock_llm)


@pytest.fixture
def ctx() -> AgentContext:
    return AgentContext(
        file_path="test.py",
        file_content="",
        original_start_line=1,
        original_end_line=1,
    )


class TestMockRules:
    """规则匹配（无 API Key 时的降级）。"""

    def test_detects_sql_injection_fstring_double_quote(self) -> None:
        code = 'cursor.execute(f"SELECT * FROM users WHERE id = {uid}")'
        findings = _run_mock_rules(code, original_start=10, file_path="db.py")
        assert len(findings) == 1
        assert findings[0].agent == "security"
        assert findings[0].severity.value == "critical"
        assert findings[0].category.value == "security"
        assert findings[0].start_line == 10

    def test_detects_sql_injection_fstring_single_quote(self) -> None:
        code = "cursor.execute(f'SELECT * FROM u WHERE id = {x}')"
        findings = _run_mock_rules(code, 5, "a.py")
        assert len(findings) == 1
        assert findings[0].start_line == 5

    def test_detects_shell_true(self) -> None:
        code = 'subprocess.call(cmd, shell=True)'
        findings = _run_mock_rules(code, 3, "x.py")
        assert len(findings) == 1
        assert findings[0].severity.value == "critical"

    def test_detects_hardcoded_api_key(self) -> None:
        code = 'API_KEY = "sk-xxx"'
        findings = _run_mock_rules(code, 1, "config.py")
        assert len(findings) == 1
        assert findings[0].severity.value == "high"

    def test_detects_hardcoded_password(self) -> None:
        code = 'password = "secret123"'
        findings = _run_mock_rules(code, 1, "auth.py")
        assert len(findings) == 1

    def test_detects_pickle_loads(self) -> None:
        code = "data = pickle.loads(raw)"
        findings = _run_mock_rules(code, 7, "p.py")
        assert len(findings) == 1
        assert findings[0].severity.value == "high"

    def test_detects_yaml_unsafe_load(self) -> None:
        code = "cfg = yaml.load(text)"
        findings = _run_mock_rules(code, 1, "y.py")
        assert len(findings) == 1

    def test_no_false_positive_on_safe_code(self) -> None:
        code = "result = a + b"
        findings = _run_mock_rules(code, 1, "safe.py")
        assert findings == []

    def test_line_number_offset_applied(self) -> None:
        """original_start=100 时，第一行应是 L100。"""
        code = 'cursor.execute(f"SELECT 1")'
        findings = _run_mock_rules(code, 100, "x.py")
        assert findings[0].start_line == 100

    def test_multiple_violations_in_same_code(self) -> None:
        code = '''API_KEY = "sk-xxx"
cursor.execute(f"SELECT * WHERE id = {uid}")
pickle.loads(data)'''
        findings = _run_mock_rules(code, 1, "multi.py")
        assert len(findings) == 3


class TestAgentInterface:
    """Agent 接口测试。"""

    @pytest.mark.asyncio
    async def test_mock_mode_returns_findings(
        self, agent: SecurityAgent, ctx: AgentContext
    ) -> None:
        # 用含漏洞的代码填充 ctx
        ctx.file_content = 'cursor.execute(f"SELECT * FROM u WHERE id = {uid}")'
        ctx.original_start_line = 1
        ctx.original_end_line = 1
        findings = await agent.review(ctx)
        assert len(findings) >= 1
        assert all(f.agent == "security" for f in findings)
        assert all(f.category.value == "security" for f in findings)

    @pytest.mark.asyncio
    async def test_mock_mode_clean_code_returns_empty(
        self, agent: SecurityAgent, ctx: AgentContext
    ) -> None:
        ctx.file_content = "x = 1 + 2\n"
        findings = await agent.review(ctx)
        assert findings == []

    def test_agent_name(self, agent: SecurityAgent) -> None:
        assert agent.name == "security"
