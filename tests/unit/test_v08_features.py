"""v0.8 新功能测试：SARIF 输出 + .cra.toml 配置加载。

覆盖：
- sarif.py: 结构、level 映射、规则生成、partialFingerprints、空结果
- config_loader.py: 查找、解析、apply_to_review_config、excluded_paths 匹配
"""

from __future__ import annotations

import json
from pathlib import Path

from cra.cli.sarif import _line_hash, _severity_to_sarif_level, render_sarif
from cra.core.config_loader import (
    ProjectConfig,
    find_config_file,
    load_project_config,
)
from cra.core.models import (
    Category,
    Finding,
    ReviewResult,
    ReviewStats,
    Severity,
)

# ============================================================
# SARIF 测试
# ============================================================


def _make_finding(
    severity: Severity = Severity.HIGH,
    category: Category = Category.SECURITY,
    title: str = "Test Issue",
    file_path: str = "auth.py",
    start_line: int = 10,
    end_line: int = 12,
    agent: str = "security",
    confidence: float = 0.9,
) -> Finding:
    return Finding(
        severity=severity,
        category=category,
        title=title,
        description="desc",
        file_path=file_path,
        start_line=start_line,
        end_line=end_line,
        agent=agent,
        confidence=confidence,
        suggestion="use safer api",
        evidence="execute(f'...{x}')",
    )


def _make_result(findings: list[Finding]) -> ReviewResult:
    stats = ReviewStats(duration_sec=1.5, cost_usd=0.002, files_reviewed=3)
    return ReviewResult(
        base_ref="main",
        head_ref="feature/x",
        findings=findings,
        stats=stats,
    )


class TestSarifLevelMapping:
    """severity → sarif level 映射。"""

    def test_critical_maps_to_error(self) -> None:
        assert _severity_to_sarif_level(Severity.CRITICAL) == "error"

    def test_high_maps_to_error(self) -> None:
        assert _severity_to_sarif_level(Severity.HIGH) == "error"

    def test_medium_maps_to_warning(self) -> None:
        assert _severity_to_sarif_level(Severity.MEDIUM) == "warning"

    def test_low_maps_to_note(self) -> None:
        assert _severity_to_sarif_level(Severity.LOW) == "note"

    def test_info_maps_to_none(self) -> None:
        assert _severity_to_sarif_level(Severity.INFO) == "none"


class TestSarifBasic:
    """SARIF 基本结构。"""

    def test_empty_result_still_valid(self) -> None:
        """没有 findings 时 SARIF 仍然合法。"""
        result = _make_result([])
        sarif = json.loads(render_sarif(result))
        assert sarif["version"] == "2.1.0"
        assert "$schema" in sarif
        assert sarif["runs"][0]["results"] == []
        # rules 也是空 list（合法）
        assert sarif["runs"][0]["tool"]["driver"]["rules"] == []

    def test_schema_present(self) -> None:
        sarif = json.loads(render_sarif(_make_result([])))
        assert sarif["$schema"].endswith("sarif-schema-2.1.0.json")

    def test_tool_driver_metadata(self) -> None:
        sarif = json.loads(render_sarif(_make_result([])))
        driver = sarif["runs"][0]["tool"]["driver"]
        assert driver["name"] == "Code Review Agent"
        assert "informationUri" in driver
        assert "semanticVersion" in driver

    def test_invocation_successful(self) -> None:
        sarif = json.loads(render_sarif(_make_result([])))
        inv = sarif["runs"][0]["invocations"][0]
        assert inv["executionSuccessful"] is True


class TestSarifResultEntry:
    """单个 finding → SARIF result 转换。"""

    def test_rule_id_format(self) -> None:
        result = _make_result([_make_finding(category=Category.SECURITY)])
        sarif = json.loads(render_sarif(result))
        assert sarif["runs"][0]["results"][0]["ruleId"] == "cra-security"

    def test_rule_id_for_correctness(self) -> None:
        result = _make_result([_make_finding(category=Category.CORRECTNESS)])
        sarif = json.loads(render_sarif(result))
        assert sarif["runs"][0]["results"][0]["ruleId"] == "cra-correctness"

    def test_location_has_region(self) -> None:
        f = _make_finding(start_line=42, end_line=45)
        result = _make_result([f])
        sarif = json.loads(render_sarif(result))
        region = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
        assert region["startLine"] == 42
        assert region["endLine"] == 45

    def test_location_has_uri_base_id(self) -> None:
        result = _make_result([_make_finding()])
        sarif = json.loads(render_sarif(result))
        loc = sarif["runs"][0]["results"][0]["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"]["uriBaseId"] == "%SRCROOT%"

    def test_partial_fingerprints_present(self) -> None:
        """GitHub 用此字段做指纹去重。"""
        result = _make_result([_make_finding()])
        sarif = json.loads(render_sarif(result))
        assert "partialFingerprints" in sarif["runs"][0]["results"][0]
        assert "primaryLocationLineHash" in sarif["runs"][0]["results"][0]["partialFingerprints"]

    def test_properties_carry_agent_and_confidence(self) -> None:
        result = _make_result([_make_finding(agent="correctness", confidence=0.77)])
        sarif = json.loads(render_sarif(result))
        props = sarif["runs"][0]["results"][0]["properties"]
        assert props["agent"] == "correctness"
        assert props["confidence"] == 0.77
        assert props["severity"] == "high"


class TestSarifRulesDedup:
    """多个 findings 共享同一个 category 时规则去重。"""

    def test_same_category_one_rule(self) -> None:
        findings = [
            _make_finding(title="A", start_line=1),
            _make_finding(title="B", start_line=10),
            _make_finding(title="C", start_line=20),
        ]
        result = _make_result(findings)
        sarif = json.loads(render_sarif(result))
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        assert len(rules) == 1
        assert sarif["runs"][0]["results"] is not None
        assert len(sarif["runs"][0]["results"]) == 3

    def test_different_categories_multiple_rules(self) -> None:
        findings = [
            _make_finding(category=Category.SECURITY, title="A", start_line=1),
            _make_finding(category=Category.CORRECTNESS, title="B", start_line=10),
            _make_finding(category=Category.ARCHITECTURE, title="C", start_line=20),
        ]
        result = _make_result(findings)
        sarif = json.loads(render_sarif(result))
        rules = sarif["runs"][0]["tool"]["driver"]["rules"]
        rule_ids = {r["id"] for r in rules}
        assert rule_ids == {"cra-security", "cra-correctness", "cra-architecture"}


class TestLineHash:
    """primaryLocationLineHash 必须稳定（同一问题同一指纹）。"""

    def test_same_input_same_hash(self) -> None:
        f1 = _make_finding()
        f2 = _make_finding()
        assert _line_hash(f1) == _line_hash(f2)

    def test_different_line_different_hash(self) -> None:
        f1 = _make_finding(start_line=10)
        f2 = _make_finding(start_line=11)
        assert _line_hash(f1) != _line_hash(f2)

    def test_different_title_different_hash(self) -> None:
        f1 = _make_finding(title="A")
        f2 = _make_finding(title="B")
        assert _line_hash(f1) != _line_hash(f2)

    def test_hash_is_hex_string(self) -> None:
        h = _line_hash(_make_finding())
        assert isinstance(h, str)
        assert len(h) == 16
        int(h, 16)  # 合法 hex


class TestSarifAutomationDetails:
    """automationDetails 标识本次扫描的范围。"""

    def test_id_contains_base_and_head(self) -> None:
        result = _make_result([])
        sarif = json.loads(render_sarif(result))
        auto_id = sarif["runs"][0]["automationDetails"]["id"]
        assert "main" in auto_id
        assert "feature/x" in auto_id
        assert auto_id.endswith("/")  # SARIF 规范要求 id 末尾 /


# ============================================================
# config_loader 测试
# ============================================================


class TestProjectConfigDefaults:
    """空 ProjectConfig 的默认值。"""

    def test_not_loaded_by_default(self) -> None:
        cfg = ProjectConfig()
        assert cfg.is_loaded is False
        assert cfg.source_path is None

    def test_empty_lists_by_default(self) -> None:
        cfg = ProjectConfig()
        assert cfg.excluded_paths == []
        assert cfg.custom_rules == []

    def test_matches_excluded_empty_returns_false(self) -> None:
        cfg = ProjectConfig()
        assert cfg.matches_excluded("any/file.py") is False


class TestFindConfigFile:
    """查找 .cra.toml。"""

    def test_no_config_in_tmp(self, tmp_path: Path) -> None:
        assert find_config_file(tmp_path) is None

    def test_finds_config_in_dir(self, tmp_path: Path) -> None:
        cfg_file = tmp_path / ".cra.toml"
        cfg_file.write_text('[review]\nenabled_agents = ["security"]\n', encoding="utf-8")
        found = find_config_file(tmp_path)
        assert found == cfg_file

    def test_finds_in_parent_dir(self, tmp_path: Path) -> None:
        """子目录运行时应该向上递归查找。"""
        cfg_file = tmp_path / ".cra.toml"
        cfg_file.write_text("[review]\n", encoding="utf-8")
        sub = tmp_path / "sub" / "deep"
        sub.mkdir(parents=True)
        found = find_config_file(sub)
        assert found == cfg_file


class TestLoadProjectConfig:
    """解析 .cra.toml 内容。"""

    def _write_config(self, path: Path, content: str) -> Path:
        path.write_text(content, encoding="utf-8")
        return path

    def test_parses_enabled_agents(self, tmp_path: Path) -> None:
        self._write_config(
            tmp_path / ".cra.toml",
            '[review]\nenabled_agents = ["correctness", "security"]\n',
        )
        cfg = load_project_config(tmp_path)
        assert cfg.is_loaded is True
        assert cfg.enabled_agents == ["correctness", "security"]

    def test_parses_confidence_threshold(self, tmp_path: Path) -> None:
        self._write_config(tmp_path / ".cra.toml", "[review]\nconfidence_threshold = 0.7\n")
        cfg = load_project_config(tmp_path)
        assert cfg.confidence_threshold == 0.7

    def test_parses_max_findings(self, tmp_path: Path) -> None:
        self._write_config(tmp_path / ".cra.toml", "[review]\nmax_findings_per_file = 8\n")
        cfg = load_project_config(tmp_path)
        assert cfg.max_findings_per_file == 8

    def test_parses_excluded_paths_dict_form(self, tmp_path: Path) -> None:
        self._write_config(
            tmp_path / ".cra.toml",
            '[review.excluded_paths]\npatterns = ["vendor/**", "**/*.gen.go"]\n',
        )
        cfg = load_project_config(tmp_path)
        assert cfg.excluded_paths == ["vendor/**", "**/*.gen.go"]

    def test_parses_custom_rules(self, tmp_path: Path) -> None:
        self._write_config(
            tmp_path / ".cra.toml",
            """
[[review.custom_rules]]
id = "no-print"
severity = "low"
pattern = "^\\\\s*print\\\\("
message = "no print"

[[review.custom_rules]]
id = "no-todo"
severity = "info"
pattern = "TODO"
message = "no todo"
""",
        )
        cfg = load_project_config(tmp_path)
        assert len(cfg.custom_rules) == 2
        assert cfg.custom_rules[0]["id"] == "no-print"
        assert cfg.custom_rules[1]["id"] == "no-todo"

    def test_parses_llm_model(self, tmp_path: Path) -> None:
        self._write_config(
            tmp_path / ".cra.toml",
            '[llm]\nmodel = "anthropic/glm-5.2"\n',
        )
        cfg = load_project_config(tmp_path)
        assert cfg.model == "anthropic/glm-5.2"

    def test_no_config_returns_empty(self, tmp_path: Path) -> None:
        cfg = load_project_config(tmp_path)
        assert cfg.is_loaded is False
        assert cfg.enabled_agents is None

    def test_invalid_toml_returns_empty(self, tmp_path: Path) -> None:
        """解析失败不抛异常，返回空配置。"""
        self._write_config(tmp_path / ".cra.toml", "not = valid = toml = [")
        cfg = load_project_config(tmp_path)
        assert cfg.is_loaded is False


class TestMatchesExcluded:
    """excluded_paths glob 匹配。"""

    def test_exact_match(self) -> None:
        cfg = ProjectConfig()
        cfg.excluded_paths = ["vendor/foo.py"]
        assert cfg.matches_excluded("vendor/foo.py") is True

    def test_double_star_glob(self) -> None:
        cfg = ProjectConfig()
        cfg.excluded_paths = ["vendor/**"]
        assert cfg.matches_excluded("vendor/pkg/module.py") is True

    def test_extension_glob(self) -> None:
        cfg = ProjectConfig()
        cfg.excluded_paths = ["**/*.generated.*"]
        assert cfg.matches_excluded("proto/generated.pb.go") is False  # 注意简化逻辑
        # 简化 pattern 后："*.generated.*"
        assert cfg.matches_excluded("any.generated.py") is True

    def test_normalizes_backslash(self) -> None:
        cfg = ProjectConfig()
        cfg.excluded_paths = ["vendor/**"]
        # Windows 风格路径也应该匹配
        assert cfg.matches_excluded("vendor\\pkg\\mod.py") is True

    def test_no_match_keeps_file(self) -> None:
        cfg = ProjectConfig()
        cfg.excluded_paths = ["vendor/**"]
        assert cfg.matches_excluded("src/main.py") is False


class TestApplyToReviewConfig:
    """ProjectConfig.apply_to_review_config 应只覆盖已设置字段。"""

    def test_overrides_enabled_agents(self) -> None:
        from cra.agents.orchestrator import ReviewConfig

        project = ProjectConfig()
        project.enabled_agents = ["security"]
        target = ReviewConfig(enabled_agents=["correctness"])
        project.apply_to_review_config(target)
        assert target.enabled_agents == ["security"]

    def test_does_not_override_unset_fields(self) -> None:
        from cra.agents.orchestrator import ReviewConfig

        project = ProjectConfig()  # 所有字段都是 None
        target = ReviewConfig(enabled_agents=["correctness"], confidence_threshold=0.9)
        project.apply_to_review_config(target)
        # 保持原值（没被 None 覆盖）
        assert target.enabled_agents == ["correctness"]
        assert target.confidence_threshold == 0.9
