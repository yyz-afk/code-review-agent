"""报告生成器。

支持四种输出格式：
- text（默认）：人类可读的彩色控制台输出
- markdown：Markdown 格式报告
- json：结构化 JSON
- sarif：SARIF v2.1.0（GitHub Code Scanning 标准）
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from cra.cli.sarif import render_sarif
from cra.core.models import ReviewResult, Severity


def render_text(result: ReviewResult, file=None) -> str:
    """渲染为彩色文本（控制台）。"""
    file = file or StringIO()
    w = file.write

    # 头部
    w("=" * 60 + "\n")
    w("  📋 Code Review Report".center(60) + "\n")
    w("=" * 60 + "\n")
    w(f"  {result.base_ref}...{result.head_ref}\n")
    w(f"  Files reviewed: {result.stats.files_reviewed}\n")
    w(f"  Duration: {result.stats.duration_sec}s\n")
    w(f"  Cost: ${result.stats.cost_usd:.4f}\n")
    if result.errors:
        w(f"  Errors: {len(result.errors)}\n")
    w("-" * 60 + "\n\n")

    # Findings
    if not result.findings:
        w("  ✅ No issues found.\n\n")
    else:
        w(f"  Findings: {len(result.findings)}\n\n")
        sorted_findings = sorted(result.findings, key=lambda f: f.severity.rank)
        for i, f in enumerate(sorted_findings, 1):
            w(f"  {i}. {f.severity.icon} [{f.severity.value.upper():8s}] "
              f"[{f.category.value}]\n")
            w(f"     📍 {f.file_path}:{f.start_line}-{f.end_line} "
              f"(by {f.agent}, conf={f.confidence:.2f})\n")
            w(f"     💡 {f.title}\n")
            if f.description:
                for line in f.description.splitlines()[:3]:
                    w(f"        {line}\n")
            if f.suggestion:
                w("     🔧 Suggestion:\n")
                for line in str(f.suggestion).splitlines()[:5]:
                    w(f"        {line}\n")
            w("\n")

    # 统计
    if result.stats.findings_by_severity:
        w("-" * 60 + "\n")
        w("  By severity:\n")
        for sev, count in sorted(result.stats.findings_by_severity.items()):
            icon = Severity(sev).icon
            w(f"    {icon} {sev}: {count}\n")

    w("=" * 60 + "\n")
    return file.getvalue() if isinstance(file, StringIO) else ""


def render_markdown(result: ReviewResult) -> str:
    """渲染为 Markdown。"""
    lines: list[str] = []
    lines.append("# 📋 Code Review Report")
    lines.append("")
    lines.append(f"- **Range**: `{result.base_ref}...{result.head_ref}`")
    lines.append(f"- **Files reviewed**: {result.stats.files_reviewed}")
    lines.append(f"- **Duration**: {result.stats.duration_sec}s")
    lines.append(f"- **Cost**: ${result.stats.cost_usd:.4f}")
    if result.errors:
        lines.append(f"- **⚠️ Errors**: {len(result.errors)}")
    lines.append("")

    if not result.findings:
        lines.append("✅ No issues found.")
        return "\n".join(lines)

    lines.append(f"## Findings ({len(result.findings)})")
    lines.append("")

    sorted_findings = sorted(result.findings, key=lambda f: f.severity.rank)
    for i, f in enumerate(sorted_findings, 1):
        lines.append(f"### {i}. {f.severity.icon} {f.title}")
        lines.append("")
        lines.append(f"- **Severity**: `{f.severity.value}`")
        lines.append(f"- **Category**: `{f.category.value}`")
        lines.append(f"- **Location**: `{f.file_path}:{f.start_line}-{f.end_line}`")
        lines.append(f"- **Agent**: `{f.agent}` (confidence: {f.confidence:.2f})")
        lines.append("")
        lines.append("**Description**:")
        lines.append("")
        lines.append(f"> {f.description}")
        lines.append("")
        if f.suggestion:
            lines.append("**Suggestion**:")
            lines.append("")
            lines.append("```python")
            lines.append(str(f.suggestion))
            lines.append("```")
            lines.append("")
        if f.evidence:
            lines.append("<details><summary>Evidence</summary>")
            lines.append("")
            lines.append(f"```\n{f.evidence}\n```")
            lines.append("")
            lines.append("</details>")
            lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def render_json(result: ReviewResult) -> str:
    """渲染为 JSON。"""
    return result.model_dump_json(indent=2)


def save_report(result: ReviewResult, path: Path, fmt: str = "text") -> None:
    """保存报告到文件。"""
    content = render(result, fmt)
    path.write_text(content, encoding="utf-8")


def render(result: ReviewResult, fmt: str = "text") -> str:
    """统一渲染入口。"""
    if fmt == "json":
        return render_json(result)
    if fmt == "sarif":
        return render_sarif(result)
    if fmt == "markdown" or fmt == "md":
        return render_markdown(result)
    return render_text(result, StringIO())
