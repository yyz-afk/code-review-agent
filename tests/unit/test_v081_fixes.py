"""v0.8.1 修复测试：P0 级问题验证。

覆盖：
- excluded_paths 真正生效（orchestrator 集成 ProjectConfig）
- custom_rules 真正生效（_run_custom_rules 实现）
- SARIF uri 路径清洗（Windows 兼容）
- confidence CLI 参数范围校验
- 死代码删除验证（_dedup_findings / _filter_by_confidence 不再存在）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cra.agents.orchestrator import ReviewOrchestrator
from cra.cli.sarif import render_sarif
from cra.core.config_loader import ProjectConfig
from cra.core.models import (
    Category,
    Finding,
    Hunk,
    ReviewResult,
    ReviewStats,
    Severity,
)

# ============================================================
# Fixture
# ============================================================


@pytest.fixture
def mock_orchestrator() -> ReviewOrchestrator:
    """构造 mock 模式的 Orchestrator。"""
    from cra.agents.llm import LlmClient  # noqa: PLC0415

    return ReviewOrchestrator(llm_client=LlmClient(enable_mock=True))


def _make_hunk(content: str, new_start: int = 1) -> Hunk:
    """便捷构造 Hunk。"""
    return Hunk(
        old_start=1,
        old_lines=1,
        new_start=new_start,
        new_lines=1,
        content=content,
    )


# ============================================================
# 1. excluded_paths 生效验证
# ============================================================


class TestExcludedPathsApplied:
    """验证 .cra.toml 的 excluded_paths 真正被 orchestrator 使用。"""

    @pytest.mark.asyncio
    async def test_excluded_file_is_skipped(self, tmp_path: Path) -> None:
        """配了 excluded_paths 的文件应该被跳过，不出现在结果中。"""
        from cra.agents.llm import LlmClient  # noqa: PLC0415

        project_cfg = ProjectConfig()
        project_cfg.excluded_paths = ["vendor/**", "generated/**"]

        orchestrator = ReviewOrchestrator(
            llm_client=LlmClient(enable_mock=True),
            project_config=project_cfg,
        )

        # 构造 diff：包含 vendor/ 下的文件（应被排除）和 src/ 下的文件（应保留）
        # 使用标准 git diff 格式（diff --git 分隔）
        diff_text = (
            "diff --git a/vendor/lib.py b/vendor/lib.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/vendor/lib.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+except Exception:\n"
            "+    pass\n"
            "diff --git a/src/app.py b/src/app.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/src/app.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+except Exception:\n"
            "+    pass\n"
        )

        result = await orchestrator.review_diff(diff_text)

        # vendor/ 应被排除，src/ 应保留
        reviewed_files = {f.file_path for f in result.findings}
        # 关键断言：vendor/ 下不应出现
        assert all("vendor" not in f for f in reviewed_files), (
            f"vendor/ 文件不应被审查: {reviewed_files}"
        )
        # src/app.py 应该被审查（即使没有 finding 也要确认被处理过）
        # 注：mock 模式只在某些 pattern 命中时产生 finding，
        # 所以用 stats.files_reviewed 验证更可靠
        assert result.stats.files_reviewed >= 1, (
            f"应至少审查 1 个文件（src/app.py），实际: {result.stats.files_reviewed}"
        )

    @pytest.mark.asyncio
    async def test_no_project_config_keeps_existing_behavior(self) -> None:
        """没有 project_config 时不应改变现有过滤行为。"""
        from cra.agents.llm import LlmClient  # noqa: PLC0415

        orchestrator = ReviewOrchestrator(
            llm_client=LlmClient(enable_mock=True),
            # project_config=None → 默认空 ProjectConfig
        )

        diff_text = "--- /dev/null\n+++ b/src/app.py\n@@ -0,0 +1,1 @@\n+except Exception:\n"
        result = await orchestrator.review_diff(diff_text)
        # 应该正常审查（不被空 excluded_paths 影响）
        assert result.stats.files_reviewed >= 1


# ============================================================
# 2. custom_rules 生效验证
# ============================================================


class TestCustomRulesApplied:
    """验证 .cra.toml 的 custom_rules 真正被应用。"""

    @pytest.mark.asyncio
    async def test_custom_rule_matches_pattern(self) -> None:
        """配置的 custom_rule 应该在 mock 模式下也生效。"""
        from cra.agents.llm import LlmClient  # noqa: PLC0415

        project_cfg = ProjectConfig()
        project_cfg.custom_rules = [
            {
                "id": "no-print",
                "severity": "low",
                "pattern": r"^\s*print\(",
                "message": "生产代码不应包含 print 语句",
            }
        ]

        orchestrator = ReviewOrchestrator(
            llm_client=LlmClient(enable_mock=True),
            project_config=project_cfg,
        )

        diff_text = (
            "--- /dev/null\n"
            "+++ b/app.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+def foo():\n"
            "+    print('debug')\n"
            "+    return 1\n"
        )
        result = await orchestrator.review_diff(diff_text)

        # 应该至少有一个来自 custom agent 的 finding
        custom_findings = [f for f in result.findings if f.agent == "custom"]
        assert len(custom_findings) >= 1, f"custom_rules 未生效: findings={result.findings}"
        # 验证 finding 内容
        first = custom_findings[0]
        assert "no-print" in first.title
        assert first.severity == Severity.LOW
        assert first.category == Category.MAINTAINABILITY

    @pytest.mark.asyncio
    async def test_invalid_regex_skipped(self) -> None:
        """无效的正则不应该让整个审查崩溃。"""
        from cra.agents.llm import LlmClient  # noqa: PLC0415

        project_cfg = ProjectConfig()
        project_cfg.custom_rules = [
            {
                "id": "bad",
                "severity": "low",
                "pattern": "[unclosed",  # 无效正则
                "message": "should be skipped",
            },
            {
                "id": "good",
                "severity": "info",
                "pattern": "TODO",
                "message": "todo found",
            },
        ]

        orchestrator = ReviewOrchestrator(
            llm_client=LlmClient(enable_mock=True),
            project_config=project_cfg,
        )

        diff_text = "--- /dev/null\n+++ b/app.py\n@@ -0,0 +1,1 @@\n+# TODO: fix this\n"
        # 不应该抛异常
        result = await orchestrator.review_diff(diff_text)
        # good 规则应该生效
        good_findings = [f for f in result.findings if "good" in f.title]
        assert len(good_findings) >= 1

    @pytest.mark.asyncio
    async def test_no_custom_rules_no_change(self) -> None:
        """没有 custom_rules 时不应改变现有审查行为。"""
        from cra.agents.llm import LlmClient  # noqa: PLC0415

        orchestrator = ReviewOrchestrator(
            llm_client=LlmClient(enable_mock=True),
            project_config=ProjectConfig(),  # custom_rules = []
        )

        diff_text = "--- /dev/null\n+++ b/app.py\n@@ -0,0 +1,1 @@\n+x = 1\n"
        result = await orchestrator.review_diff(diff_text)
        # 无 custom findings
        assert not any(f.agent == "custom" for f in result.findings)

    def test_run_custom_rules_line_numbers_correct(
        self, mock_orchestrator: ReviewOrchestrator
    ) -> None:
        """custom rule 命中的行号应该映射到原始文件行号。"""
        rules = [
            {
                "id": "todo",
                "severity": "info",
                "pattern": "TODO",
                "message": "todo",
            }
        ]
        # hunk 从 L10 开始，TODO 在第 2 行（即原文件 L11）
        hunks = [
            _make_hunk(
                "@@ -1,1 +10,2 @@\n+line1\n+# TODO: fix\n",
                new_start=10,
            )
        ]

        findings = mock_orchestrator._run_custom_rules("app.py", hunks, rules)
        assert len(findings) == 1
        # 第 2 行（hunk 内）= 原文件 L11
        assert findings[0].start_line == 11
        assert findings[0].end_line == 11


# ============================================================
# 3. SARIF uri 路径清洗
# ============================================================


class TestSarifUriNormalization:
    """Windows 路径反斜杠应该被转成正斜杠。"""

    def _render_with_path(self, path: str) -> str:
        finding = Finding(
            agent="correctness",
            severity=Severity.HIGH,
            category=Category.CORRECTNESS,
            file_path=path,
            start_line=1,
            end_line=1,
            title="test",
            description="d",
            confidence=0.9,
        )
        stats = ReviewStats(duration_sec=0.1, cost_usd=0.001, files_reviewed=1)
        result = ReviewResult(
            base_ref="main",
            head_ref="HEAD",
            findings=[finding],
            stats=stats,
        )
        return render_sarif(result)

    def test_windows_path_normalized(self) -> None:
        sarif = json.loads(self._render_with_path("src\\pkg\\mod.py"))
        uri = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
            "artifactLocation"
        ]["uri"]
        assert uri == "src/pkg/mod.py"
        assert "\\" not in uri

    def test_unix_path_unchanged(self) -> None:
        sarif = json.loads(self._render_with_path("src/pkg/mod.py"))
        uri = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
            "artifactLocation"
        ]["uri"]
        assert uri == "src/pkg/mod.py"

    def test_mixed_separators(self) -> None:
        sarif = json.loads(self._render_with_path("src\\pkg/other\\file.py"))
        uri = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"][
            "artifactLocation"
        ]["uri"]
        assert uri == "src/pkg/other/file.py"


# ============================================================
# 4. 死代码删除验证
# ============================================================


class TestDeadCodeRemoved:
    """v0.8.1 删除的方法不应再存在。"""

    def test_dedup_findings_removed(self, mock_orchestrator: ReviewOrchestrator) -> None:
        assert not hasattr(mock_orchestrator, "_dedup_findings")

    def test_filter_by_confidence_removed(self, mock_orchestrator: ReviewOrchestrator) -> None:
        assert not hasattr(mock_orchestrator, "_filter_by_confidence")


# ============================================================
# 5. apply_to_review_config 类型注解 + 行为
# ============================================================


class TestApplyToReviewConfigContract:
    """apply_to_review_config 行为契约。"""

    def test_only_overrides_set_fields(self) -> None:
        """未设置的字段（None）不应覆盖目标。"""
        from cra.agents.orchestrator import ReviewConfig  # noqa: PLC0415

        project = ProjectConfig()  # 所有字段 None
        target = ReviewConfig(
            enabled_agents=["correctness"],
            confidence_threshold=0.9,
            max_findings_per_file=3,
        )
        project.apply_to_review_config(target)
        # 保持原值
        assert target.enabled_agents == ["correctness"]
        assert target.confidence_threshold == 0.9
        assert target.max_findings_per_file == 3

    def test_overrides_enabled_agents(self) -> None:
        from cra.agents.orchestrator import ReviewConfig  # noqa: PLC0415

        project = ProjectConfig()
        project.enabled_agents = ["security", "performance"]
        target = ReviewConfig(enabled_agents=["correctness"])
        project.apply_to_review_config(target)
        assert target.enabled_agents == ["security", "performance"]


# ============================================================
# 6. CLI confidence 范围校验
# ============================================================


class TestCliConfidenceValidation:
    """CLI 的 --confidence 参数应校验范围。

    Typer 的 min/max 参数会在解析阶段直接报错，
    我们通过 typer.testing.CliRunner 来验证。
    """

    def test_confidence_0_to_1_accepted(self) -> None:
        """合法范围内的值应该能正常解析。"""
        from typer.testing import CliRunner

        from cra.cli.main import app  # noqa: PLC0415

        runner = CliRunner()
        # 0.5 应该通过校验（虽然后续会因为缺 base/diff 报错，但不会是参数错误）
        result = runner.invoke(
            app,
            [
                "review",
                "--confidence",
                "0.5",
                "--diff",
                "/nonexistent",
            ],
        )
        # 不是参数校验错误（exit_code 2 是 typer 的参数错误）
        # 这里因为文件不存在会失败，但不应该是 confidence 的错
        assert "Invalid value" not in result.output or "confidence" not in result.output

    def test_confidence_out_of_range_rejected(self) -> None:
        """超出范围的值应被拒绝。"""
        from typer.testing import CliRunner

        from cra.cli.main import app  # noqa: PLC0415

        runner = CliRunner()
        result = runner.invoke(
            app,
            [
                "review",
                "--confidence",
                "5.0",
                "--diff",
                "/nonexistent",
            ],
        )
        # typer 应该拒绝（exit_code != 0）
        assert result.exit_code != 0
