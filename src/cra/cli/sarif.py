"""SARIF 输出格式实现。

SARIF (Static Analysis Results Interchange Format) 是 OASIS 标准，
被 GitHub Code Scanning 原生支持。上传 SARIF 后会显示在仓库的
Security 标签页。

规范：https://docs.oasis-open.org/sarif/sarif/v2.1.0/sarif-v2.1.0.html
GitHub 上传限制：https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning
"""

from __future__ import annotations

import json
from pathlib import Path

from cra import __version__
from cra.core.models import Category, ReviewResult, Severity


# SARIF Level 映射（GitHub 识别的级别）
_SARIF_LEVEL = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "none",
}

# 规则 ID 前缀（避免与其他工具冲突）
_RULE_ID_PREFIX = "cra"


def _severity_to_sarif_level(sev: Severity) -> str:
    return _SARIF_LEVEL.get(sev, "note")


def _category_to_rule_short_name(cat: Category) -> str:
    """Category → 短名（用于构造 rule id，如 cra-security）。"""
    return cat.value


def render_sarif(result: ReviewResult) -> str:
    """渲染 ReviewResult 为 SARIF JSON 字符串。"""
    sarif = _build_sarif(result)
    return json.dumps(sarif, indent=2, ensure_ascii=False)


def save_sarif(result: ReviewResult, path: Path) -> None:
    """保存为 .sarif 文件。"""
    path.write_text(render_sarif(result), encoding="utf-8")


def _build_sarif(result: ReviewResult) -> dict:
    """构建完整的 SARIF 文档。"""
    # 收集所有规则（按 category 去重）
    rules: dict[str, dict] = {}
    results: list[dict] = []

    for finding in result.findings:
        rule_id = f"{_RULE_ID_PREFIX}-{_category_to_rule_short_name(finding.category)}"

        # 注册规则（如果还没有）
        if rule_id not in rules:
            rules[rule_id] = {
                "id": rule_id,
                "name": _category_to_rule_short_name(finding.category).upper(),
                "shortDescription": {
                    "text": f"Code Review Agent: {finding.category.value}"
                },
                "fullDescription": {
                    "text": (
                        f"Issues reported by the {finding.agent} agent "
                        f"specialized in {finding.category.value}."
                    )
                },
                "helpUri": "https://github.com/xuxiaxuan/code-review-agent",
                "properties": {
                    "tags": ["ai", "code-review", finding.category.value],
                    "precision": "medium",
                },
            }

        # 构造 result
        message = finding.title
        if finding.description and finding.description != finding.title:
            message = f"{finding.title}\n\n{finding.description}"

        result_entry = {
            "ruleId": rule_id,
            "level": _severity_to_sarif_level(finding.severity),
            "message": {"text": message},
            "locations": [
                {
                    "physicalLocation": {
                        "artifactLocation": {
                            "uri": finding.file_path,
                            "uriBaseId": "%SRCROOT%",
                        },
                        "region": {
                            "startLine": finding.start_line,
                            "endLine": finding.end_line,
                        },
                    }
                }
            ],
            "partialFingerprints": {
                "primaryLocationLineHash": _line_hash(finding),
            },
            "properties": {
                "agent": finding.agent,
                "confidence": finding.confidence,
                "severity": finding.severity.value,
                "category": finding.category.value,
                "verified_by_tool": finding.verified_by_tool,
                "evidence": finding.evidence,
                "suggestion": finding.suggestion,
            },
        }
        results.append(result_entry)

    return {
        "$schema": (
            "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/main/"
            "Schemata/sarif-schema-2.1.0.json"
        ),
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Code Review Agent",
                        "semanticVersion": __version__,
                        "informationUri": "https://github.com/xuxiaxuan/code-review-agent",
                        "rules": list(rules.values()),
                    }
                },
                "automationDetails": {
                    "id": f"{result.base_ref}...{result.head_ref}/",
                    "guid": None,
                },
                "results": results,
                "invocations": [
                    {
                        "executionSuccessful": True,
                        "toolExecutionNotifications": [],
                    }
                ],
            }
        ],
        "properties": {
            "total_findings": len(result.findings),
            "duration_sec": result.stats.duration_sec,
            "cost_usd": result.stats.cost_usd,
            "files_reviewed": result.stats.files_reviewed,
        },
    }


def _line_hash(finding) -> str:
    """简单的行哈希（用于 GitHub fingerprint 去重）。

    GitHub 要求 partialFingerprints 来识别同一问题在不同运行中的同一性。
    完整实现应用 SHA256，这里用简单拼接（满足基本需求）。
    """
    import hashlib  # noqa: PLC0415

    raw = f"{finding.file_path}:{finding.start_line}:{finding.title}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
