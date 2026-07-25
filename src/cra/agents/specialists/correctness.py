"""Correctness Agent：逻辑正确性审查专家。

v0.8.2：继承 BaseSpecialist，仅保留 prompt + mock 规则。
"""

from __future__ import annotations

from cra.agents.specialists.base import BaseSpecialist
from cra.core.models import Category, Finding, Severity

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


def _run_mock_rules(code: str, original_start: int, file_path: str) -> list[Finding]:
    """Mock 模式：基于规则的简单匹配。返回带原始文件行号的 finding。"""
    findings: list[Finding] = []
    lines = code.splitlines()
    for i, line in enumerate(lines, start=1):  # 相对行号 1-based
        for pattern, sev, cat, title, desc, conf in _MOCK_PATTERNS:
            pattern_first = pattern.split("\n")[0]
            if pattern_first in line:
                # 相对行号 → 原始文件行号
                orig_line = original_start + i - 1
                findings.append(
                    Finding(
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
                    )
                )
    return findings


# ============================================================
# Agent 实现（继承 BaseSpecialist，仅声明特化信息）
# ============================================================


class CorrectnessAgent(BaseSpecialist):
    """正确性审查 Agent。"""

    name = "correctness"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    default_category = Category.CORRECTNESS

    def _run_mock_rules(self, code: str, original_start: int, file_path: str) -> list[Finding]:
        return _run_mock_rules(code, original_start, file_path)
