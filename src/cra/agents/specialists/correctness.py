"""Correctness Agent：逻辑正确性审查专家。

Phase 1 的核心 Agent，后续会扩展 Security/Performance/Architecture 等。

v0.2 改进：
- 基于 hunk 上下文，行号映射到原始文件
- Prompt 中明确告诉 LLM 代码的起始行号
- mock 模式作为无 API Key 时的降级方案
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cra.core.models import AgentContext, Category, Finding, Severity

if TYPE_CHECKING:
    from cra.agents.llm import LlmClient

logger = logging.getLogger(__name__)


# ============================================================
# System Prompt
# ============================================================

SYSTEM_PROMPT = """你是代码逻辑正确性审查专家，专注于发现会导致运行时错误或逻辑错误的缺陷。

## 核心原则（必须遵守）

1. **克制原则**：只报告你有充分证据相信是真实问题的发现。
   - 不报告样式、格式、命名偏好问题
   - 当不确定时，宁可不报

2. **证据原则**：每个发现必须有代码证据。
   - 引用具体的代码行作为证据
   - 说明推理过程

3. **可操作原则**：提供具体修复建议。

## 检查清单

- **空值/None 处理**：未检查 None 就访问属性
- **边界条件**：off-by-one、空集合、零除
- **异常处理**：捕获过宽、吞掉异常、finally 中 return
- **并发问题**：竞态条件、死锁
- **类型混淆**：隐式类型转换问题
- **资源泄漏**：未关闭的文件/连接
- **状态假设**：未检查返回值
- **安全问题**：SQL 注入、命令注入（如发现请标 severity=critical）

## 输出规范

输出严格 JSON 数组，每个元素：
```json
{
  "severity": "critical|high|medium|low|info",
  "category": "correctness",
  "start_line": 123,
  "end_line": 125,
  "title": "一句话总结",
  "description": "详细说明",
  "suggestion": "修复建议或代码",
  "evidence": "推理证据",
  "confidence": 0.0
}
```

**重要**：
- `start_line` 和 `end_line` 必须使用代码片段中显示的行号
- `suggestion` 字段中的代码块必须使用正确的语言标签
  （如审查 TypeScript 时用 ```typescript，Python 时用 ```python）

无问题返回 `[]`。绝对不要输出 JSON 以外内容。
"""


# ============================================================
# Mock 规则匹配（无 API Key 时的降级方案）
# ============================================================

_MOCK_PATTERNS: list[tuple[str, Severity, Category, str, str, float]] = [
    # (pattern, severity, category, title, description, confidence)
    (
        "except Exception",
        Severity.MEDIUM,
        Category.CORRECTNESS,
        "宽泛异常捕获",
        "except Exception 会捕获所有异常包括 KeyboardInterrupt，"
        "可能导致关键错误被隐藏。建议捕获具体的异常类型。",
        0.75,
    ),
    (
        "except:\n    pass",
        Severity.MEDIUM,
        Category.CORRECTNESS,
        "异常被吞掉",
        "捕获所有异常后直接 pass，会隐藏真实错误。",
        0.85,
    ),
    (
        "execute(f'",
        Severity.CRITICAL,
        Category.SECURITY,
        "SQL 注入风险（f-string 拼接）",
        "SQL 查询通过 f-string 拼接用户输入，存在 SQL 注入风险。",
        0.95,
    ),
    (
        'execute(f"',
        Severity.CRITICAL,
        Category.SECURITY,
        "SQL 注入风险（f-string 拼接）",
        "SQL 查询通过 f-string 拼接用户输入，存在 SQL 注入风险。",
        0.95,
    ),
]


def _run_mock_rules(
    code: str, original_start: int, file_path: str
) -> list[Finding]:
    """Mock 模式：基于规则的简单匹配。返回带原始文件行号的 finding。"""
    findings: list[Finding] = []
    lines = code.splitlines()
    for i, line in enumerate(lines, start=1):  # 相对行号 1-based
        for pattern, sev, cat, title, desc, conf in _MOCK_PATTERNS:
            pattern_first = pattern.split("\n")[0]
            if pattern_first in line:
                # 相对行号 → 原始文件行号
                orig_line = original_start + i - 1
                findings.append(Finding(
                    agent="correctness",
                    severity=sev,
                    category=cat,
                    file_path=file_path,
                    start_line=orig_line,
                    end_line=orig_line,
                    title=title,
                    description=desc,
                    evidence=f"L{orig_line}: {line.strip()!r} 匹配模式: {pattern!r}",
                    confidence=conf,
                ))
    return findings


# ============================================================
# Agent 实现
# ============================================================


class CorrectnessAgent:
    """正确性审查 Agent。"""

    name = "correctness"

    def __init__(self, llm_client: LlmClient) -> None:
        self.llm = llm_client

    async def review(self, ctx: AgentContext) -> list[Finding]:
        """审查给定的上下文。"""
        if self.llm.mock_mode:
            # Mock 模式：规则匹配，已经用原始行号
            return _run_mock_rules(
                ctx.file_content, ctx.original_start_line, ctx.file_path
            )

        # 真实 LLM 调用
        # 构造带行号前缀的代码，让 LLM 输出基于原始文件的行号
        numbered_code = _format_with_line_numbers(
            ctx.file_content, ctx.original_start_line
        )

        # 根据扩展名推断代码块语言标记（影响 LLM 的语法理解）
        ext = ctx.file_path.rsplit(".", 1)[-1].lower() if "." in ctx.file_path else ""
        lang_tag = {
            "py": "python", "js": "javascript", "jsx": "jsx",
            "ts": "typescript", "tsx": "tsx",
            "java": "java", "go": "go",
        }.get(ext, "")

        code_block = f"```{lang_tag}\n{numbered_code}\n```" if lang_tag else f"```\n{numbered_code}\n```"

        user_msg = (
            f"文件：{ctx.file_path}\n"
            f"以下代码片段在原文件中位于第 {ctx.original_start_line}-"
            f"{ctx.original_end_line} 行。\n\n"
            f"{code_block}\n\n"
            f"输出 JSON findings 数组。start_line 必须是代码片段中 "
            f"显示的行号（方括号内的数字）。"
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        parsed, response = await self.llm.complete_json(messages)
        if not isinstance(parsed, list):
            logger.warning(
                "LLM returned non-array: %s",
                (response.content[:200] if response.content else "empty"),
            )
            return []

        findings: list[Finding] = []
        for item in parsed:
            finding = self._parse_finding(item, ctx)
            if finding:
                findings.append(finding)

        return findings

    @staticmethod
    def _parse_finding(item: dict, ctx: AgentContext) -> Finding | None:
        """把 LLM 返回的 dict 解析为 Finding。"""
        try:
            sev_str = str(item.get("severity", "info")).lower()
            severity = Severity(sev_str)
            category_str = str(item.get("category", "correctness")).lower()
            try:
                category = Category(category_str)
            except ValueError:
                category = Category.CORRECTNESS

            # 行号：LLM 应该已经基于原始文件行号返回
            start_line = int(item.get("start_line", ctx.original_start_line))
            end_line = int(item.get("end_line", start_line))

            # 越界保护：如果行号不在 hunk 范围内，截断到合理范围
            start_line = max(start_line, ctx.original_start_line)
            end_line = min(end_line, ctx.original_end_line)
            if end_line < start_line:
                end_line = start_line

            return Finding(
                agent="correctness",
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
            logger.warning("Failed to parse finding %r: %s", item, e)
            return None


def _format_with_line_numbers(code: str, start_line: int) -> str:
    """给代码每行加上原始文件行号前缀。

    示例：
        [4] query = f"SELECT ..."
        [5] cursor.execute(query)
    """
    lines = code.splitlines()
    return "\n".join(
        f"[{start_line + i}] {line}"
        for i, line in enumerate(lines)
    )
