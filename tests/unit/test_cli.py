"""CLI 入口测试（强制 mock 模式，无 LLM）。

覆盖：
- version / info 命令
- review 命令的 mock 模式（无 --base，缺 --diff 报错等）
- 各格式输出（text/markdown/json/sarif）的基本正确性
- --confidence 范围校验
- 退出码（0 / 1 / 2）
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cra.cli.main import app


@pytest.fixture(autouse=True)
def force_mock_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """强制 mock 模式：避免本地 .env 文件触发真实 LLM 调用。

    直接 monkeypatch ``_has_any_api_key`` 让所有 LlmClient 实例进入 mock 模式。
    这比删环境变量更可靠（pydantic-settings 会从 .env 文件读取）。
    """
    import cra.agents.llm as llm_module  # noqa: PLC0415

    monkeypatch.setattr(llm_module, "_has_any_api_key", lambda: False)


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ============================================================
# version / info 命令
# ============================================================


class TestVersionInfo:
    def test_version_prints_version_number(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert "code-review-agent" in result.output
        assert "v" in result.output

    def test_info_shows_config(self, runner: CliRunner) -> None:
        result = runner.invoke(app, ["info"])
        assert result.exit_code == 0
        # info 应包含关键字段
        assert "default_model" in result.output or "Configuration" in result.output


# ============================================================
# review 命令：参数校验
# ============================================================


class TestReviewArgValidation:
    def test_missing_base_and_diff_errors(self, runner: CliRunner) -> None:
        """没有 --base 也没有 --diff 应该报错（exit_code 2）。"""
        result = runner.invoke(app, ["review"])
        assert result.exit_code == 2

    def test_confidence_out_of_range_rejected(self, runner: CliRunner, tmp_path: Path) -> None:
        """confidence 超出 [0,1] 应被 typer 拒绝。"""
        # 创建一个临时 diff 文件
        diff_file = tmp_path / "test.diff"
        diff_file.write_text("", encoding="utf-8")

        result = runner.invoke(
            app,
            [
                "review",
                "--diff",
                str(diff_file),
                "--confidence",
                "5.0",
            ],
        )
        assert result.exit_code != 0
        assert "confidence" in result.output.lower() or "Invalid value" in result.output

    def test_confidence_zero_accepted(self, runner: CliRunner, tmp_path: Path) -> None:
        """confidence=0.0 应该能通过校验（即使后续可能因空 diff 报错）。"""
        diff_file = tmp_path / "test.diff"
        diff_file.write_text("", encoding="utf-8")

        result = runner.invoke(
            app,
            [
                "review",
                "--diff",
                str(diff_file),
                "--confidence",
                "0.0",
                "--quiet",  # 抑制 banner
            ],
        )
        # 不会因为 confidence 校验失败
        assert "confidence" not in result.output.lower() or result.exit_code == 0


# ============================================================
# review 命令：mock 模式端到端
# ============================================================


class TestReviewMockEndToEnd:
    """mock 模式下完整跑一次 review（无 LLM）。"""

    @pytest.fixture
    def sample_diff(self, tmp_path: Path) -> Path:
        """生成一个含违规的 diff 文件。"""
        diff_file = tmp_path / "test.diff"
        diff_file.write_text(
            "diff --git a/app.py b/app.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/app.py\n"
            "@@ -0,0 +1,3 @@\n"
            "+import os\n"
            "+except Exception:\n"
            "+    pass\n",
            encoding="utf-8",
        )
        return diff_file

    def test_review_text_output(self, runner: CliRunner, sample_diff: Path) -> None:
        result = runner.invoke(
            app,
            [
                "review",
                "--diff",
                str(sample_diff),
                "--format",
                "text",
                "--quiet",
            ],
        )
        assert result.exit_code == 0
        assert "app.py" in result.output

    def test_review_json_output_is_valid_json(self, runner: CliRunner, sample_diff: Path) -> None:
        result = runner.invoke(
            app,
            [
                "review",
                "--diff",
                str(sample_diff),
                "--format",
                "json",
                "--quiet",
            ],
        )
        assert result.exit_code == 0
        # stdout 应该是合法 JSON
        data = json.loads(result.stdout)
        assert "findings" in data
        assert "stats" in data

    def test_review_sarif_output_is_valid_sarif(self, runner: CliRunner, sample_diff: Path) -> None:
        result = runner.invoke(
            app,
            [
                "review",
                "--diff",
                str(sample_diff),
                "--format",
                "sarif",
                "--quiet",
            ],
        )
        assert result.exit_code == 0
        sarif = json.loads(result.stdout)
        assert sarif["version"] == "2.1.0"
        assert "$schema" in sarif
        assert sarif["runs"][0]["tool"]["driver"]["name"] == "Code Review Agent"

    def test_review_markdown_output(self, runner: CliRunner, sample_diff: Path) -> None:
        result = runner.invoke(
            app,
            [
                "review",
                "--diff",
                str(sample_diff),
                "--format",
                "markdown",
                "--quiet",
            ],
        )
        assert result.exit_code == 0
        assert "Code Review" in result.output or "#" in result.output

    def test_review_output_to_file(
        self, runner: CliRunner, sample_diff: Path, tmp_path: Path
    ) -> None:
        out_file = tmp_path / "report.json"
        result = runner.invoke(
            app,
            [
                "review",
                "--diff",
                str(sample_diff),
                "--format",
                "json",
                "--output",
                str(out_file),
                "--quiet",
            ],
        )
        assert result.exit_code == 0
        assert out_file.exists()
        # 文件内容应该是合法 JSON
        data = json.loads(out_file.read_text(encoding="utf-8"))
        assert "findings" in data


# ============================================================
# --agents 参数
# ============================================================


class TestAgentsSelection:
    """--agents 参数应能选择启用的 agent。"""

    def test_only_correctness(self, runner: CliRunner, tmp_path: Path) -> None:
        diff_file = tmp_path / "test.diff"
        diff_file.write_text(
            "diff --git a/app.py b/app.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/app.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+except Exception:\n"
            "+    pass\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            [
                "review",
                "--diff",
                str(diff_file),
                "--agents",
                "correctness",
                "--format",
                "json",
                "--quiet",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.stdout)
        # 只启用 correctness，所有 finding 的 agent 应该是 correctness
        # （custom_rules 默认空，不会产生 agent="custom"）
        for f in data.get("findings", []):
            assert f["agent"] in ("correctness",), f"应该只有 correctness，但出现了 {f['agent']}"


# ============================================================
# 退出码
# ============================================================


class TestExitCodes:
    """review 命令的退出码语义。"""

    def test_empty_diff_exits_zero(self, runner: CliRunner, tmp_path: Path) -> None:
        diff_file = tmp_path / "empty.diff"
        diff_file.write_text("", encoding="utf-8")
        result = runner.invoke(
            app,
            [
                "review",
                "--diff",
                str(diff_file),
                "--quiet",
            ],
        )
        # 空 diff 无 findings → exit 0
        assert result.exit_code == 0

    def test_clean_code_exits_zero(self, runner: CliRunner, tmp_path: Path) -> None:
        """无违规的代码 → exit 0。"""
        diff_file = tmp_path / "clean.diff"
        diff_file.write_text(
            "diff --git a/clean.py b/clean.py\n"
            "new file mode 100644\n"
            "--- /dev/null\n"
            "+++ b/clean.py\n"
            "@@ -0,0 +1,2 @@\n"
            "+def add(a, b):\n"
            "+    return a + b\n",
            encoding="utf-8",
        )
        result = runner.invoke(
            app,
            [
                "review",
                "--diff",
                str(diff_file),
                "--quiet",
            ],
        )
        assert result.exit_code == 0
