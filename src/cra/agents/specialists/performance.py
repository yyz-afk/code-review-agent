"""Performance Agent：专项性能审查。

v0.8.2：继承 BaseSpecialist，仅保留 prompt + mock 规则。
"""

from __future__ import annotations

from cra.agents.specialists.base import BaseSpecialist
from cra.core.models import AgentContext, Category, Finding, Severity

# ============================================================
# System Prompt
# ============================================================

SYSTEM_PROMPT = """你是代码性能审查专家，专注于发现会导致性能问题的反模式。

## 核心原则

1. **证据原则**：必须有量级估算或明确反模式，不凭感觉报告性能问题。
2. **量化**：说明预期数据规模（如"循环可能 > 1000 次"）。
3. **可操作**：给出具体优化方案与替代代码。

## 检查清单（按优先级）

### Critical / High（明显性能 Bug）
- **N+1 查询**：循环内执行数据库/HTTP 查询
- **资源泄漏**：未关闭的连接/文件/锁
- **同步 IO 阻塞异步**：async 函数中调用同步 IO
- **大集合低效操作**：list 线性查找（应用 set）、多次遍历

### Medium（值得优化的反模式）
- **不必要的嵌套循环**：O(n²) 或更差，且 n 较大
- **循环内重复计算**：可提到循环外的常量
- **低效字符串拼接**：循环内 `+=`（应用 join）
- **缺少索引的数据库查询**：WHERE/JOIN 字段无索引（结合 schema）
- **未批处理**：可批量但逐个调用

### Low（微优化）
- **不必要的函数调用**：循环内的 lambda/属性查找
- **过大的全局变量**：模块加载时初始化大对象

## 输出规范

输出严格 JSON 数组：
```json
{
  "severity": "critical|high|medium|low|info",
  "category": "performance",
  "start_line": 123,
  "end_line": 125,
  "title": "一句话总结（含反模式名）",
  "description": "性能影响 + 数据规模估算",
  "suggestion": "优化代码（用对应语言代码块标签）",
  "evidence": "具体反模式位置 + 复杂度分析",
  "confidence": 0.0
}
```

无问题返回 `[]`。**绝对不要**报告无依据的微优化。
"""


# ============================================================
# Mock 规则匹配（无 API Key 时降级）
# ============================================================


def _run_mock_rules(code: str, original_start: int, file_path: str) -> list[Finding]:
    """Mock 模式：简单规则匹配。

    真实的性能问题需要上下文理解，mock 模式只能做模式匹配。
    """
    findings: list[Finding] = []
    lines = code.splitlines()

    # N+1：循环 + execute/query
    for i, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith(("for ", "while ")):
            # 检查循环体内是否有 DB 调用（看后续 5 行）
            for j in range(i, min(i + 5, len(lines) + 1)):
                inner = lines[j - 1] if j - 1 < len(lines) else ""
                if any(p in inner for p in (".execute(", ".query(", "fetchone", "fetchall")):
                    orig_line = original_start + j - 1
                    findings.append(
                        Finding(
                            agent="performance",
                            severity=Severity.HIGH,
                            category=Category.PERFORMANCE,
                            file_path=file_path,
                            start_line=orig_line,
                            end_line=orig_line,
                            title="疑似 N+1 查询（循环内 DB 调用）",
                            description=(
                                f"循环（L{original_start + i - 1}）内执行 DB 调用 "
                                f"(L{orig_line})，可能导致 N+1 查询。"
                                "如果循环次数可能 > 10，应改为批量查询。"
                            ),
                            evidence=f"循环 + DB 调用：\n  L{original_start + i - 1}: {lines[i - 1].strip()}\n  L{orig_line}: {inner.strip()}",
                            confidence=0.75,
                        )
                    )
                    break

    return findings


# ============================================================
# Agent 实现
# ============================================================


class PerformanceAgent(BaseSpecialist):
    """性能审查 Agent。"""

    name = "performance"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    default_category = Category.PERFORMANCE

    def build_user_msg(self, ctx: AgentContext, code_block: str) -> str:
        """定制：性能审查 prompt。"""
        return (
            f"文件：{ctx.file_path}\n"
            f"代码片段位于原文件第 {ctx.original_start_line}-"
            f"{ctx.original_end_line} 行。\n\n"
            f"{code_block}\n\n"
            f"进行性能审查。输出 JSON findings 数组。"
        )

    def _run_mock_rules(self, code: str, original_start: int, file_path: str) -> list[Finding]:
        return _run_mock_rules(code, original_start, file_path)
