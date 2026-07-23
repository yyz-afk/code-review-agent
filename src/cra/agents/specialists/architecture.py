"""Architecture Agent：架构与可维护性审查。

聚焦于设计质量：SRP 违反、God Object、循环依赖、DRY 违反、过度设计等。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cra.core.models import AgentContext, Category, Finding, Severity

if TYPE_CHECKING:
    from cra.agents.llm import LlmClient

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """你是软件架构审查专家，关注代码设计质量与可维护性。

## 核心原则

1. **克制**：架构问题通常不紧急，severity 不超过 medium（除非破坏关键约束）。
2. **证据**：基于具体代码指出违反的设计原则。
3. **可操作**：给出具体重构方向（不是"应该重构"这种空话）。

## 检查清单（SOLID + DRY + KISS + YAGNI）

### Single Responsibility（SRP）
- 函数/类承担过多职责（特征：多段不相关逻辑、参数过多、难以命名）
- 类同时处理业务逻辑 + 数据访问 + 日志

### Open-Closed（OCP）
- 新增类型需要修改现有 switch/if-else 链
- 缺少抽象导致扩展需要改源码

### Dependency Inversion（DIP）
- 高层模块直接依赖低层实现（应依赖抽象）
- 业务代码直接 import 具体数据库/HTTP 客户端

### DRY 违反
- 明显的代码复制粘贴（重复 > 5 行）
- 相同逻辑多处实现

### KISS / YAGNI 违反
- 为简单问题引入复杂抽象
- 预留"未来可能用到"的参数/接口
- 过度配置化（应硬编码）

### 其他
- **God Object**：类过大（> 500 行或 > 20 方法）
- **Shotgun Surgery**：一个改动需要分散修改多处
- **命名误导**：名字与实际行为不符

## 输出规范

输出严格 JSON 数组：
```json
{
  "severity": "critical|high|medium|low|info",
  "category": "architecture",
  "start_line": 123,
  "end_line": 125,
  "title": "一句话总结（含违反的原则）",
  "description": "为什么这是问题 + 影响范围",
  "suggestion": "具体重构方向或代码示例",
  "evidence": "具体代码位置",
  "confidence": 0.0
}
```

无问题返回 `[]`。架构问题请用 medium/low 为主。
"""


def _run_mock_rules(
    code: str, original_start: int, file_path: str
) -> list[Finding]:
    """Mock 模式：架构问题很难靠规则识别，只做最基础的。"""
    findings: list[Finding] = []
    lines = code.splitlines()

    LONG_FUNC_THRESHOLD = 50  # 行数阈值

    func_start: int | None = None
    func_name: str | None = None

    def _close(current_line_idx: int) -> None:
        """收尾当前函数：检查长度并产出 finding。"""
        nonlocal func_start, func_name
        if func_start is None or func_name is None:
            return
        length = current_line_idx - func_start
        if length > LONG_FUNC_THRESHOLD:
            orig_start = original_start + func_start - 1
            orig_end = original_start + current_line_idx - 2
            findings.append(Finding(
                agent="architecture",
                severity=Severity.MEDIUM,
                category=Category.ARCHITECTURE,
                file_path=file_path,
                start_line=orig_start,
                end_line=orig_end,
                title=f"函数过长：{func_name}（{length} 行）",
                description=(
                    f"函数 {func_name} 长度 {length} 行，"
                    f"超过 {LONG_FUNC_THRESHOLD} 行阈值，可能违反 SRP。"
                    "建议拆分为多个职责单一的子函数。"
                ),
                evidence=f"函数定义于 L{orig_start}，至 L{orig_end}（共 {length} 行）",
                confidence=0.6,
            ))
        func_start = None
        func_name = None

    for i, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith("def "):
            _close(i)  # 收尾上一个
            func_start = i
            func_name = stripped[4:].split("(", 1)[0]

    # 处理文件末尾的最后一个函数
    _close(len(lines) + 1)

    return findings


class ArchitectureAgent:
    """架构审查 Agent。"""

    name = "architecture"

    def __init__(self, llm_client: "LlmClient") -> None:
        self.llm = llm_client

    async def review(self, ctx: AgentContext) -> list[Finding]:
        """审查给定的上下文。"""
        if self.llm.mock_mode:
            return _run_mock_rules(
                ctx.file_content, ctx.original_start_line, ctx.file_path
            )

        from cra.agents.specialists.correctness import (  # noqa: PLC0415
            _format_with_line_numbers,
        )

        numbered_code = _format_with_line_numbers(
            ctx.file_content, ctx.original_start_line
        )

        ext = ctx.file_path.rsplit(".", 1)[-1].lower() if "." in ctx.file_path else ""
        lang_tag = {
            "py": "python", "js": "javascript", "ts": "typescript",
            "java": "java", "go": "go",
        }.get(ext, "")
        code_block = (
            f"```{lang_tag}\n{numbered_code}\n```"
            if lang_tag else f"```\n{numbered_code}\n```"
        )

        user_msg = (
            f"文件：{ctx.file_path}\n"
            f"代码片段位于原文件第 {ctx.original_start_line}-"
            f"{ctx.original_end_line} 行。\n\n"
            f"{code_block}\n\n"
            f"进行架构与可维护性审查。输出 JSON findings 数组。"
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        parsed, response = await self.llm.complete_json(messages)
        if not isinstance(parsed, list):
            logger.warning(
                "Architecture LLM returned non-array: %s",
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
        try:
            sev_str = str(item.get("severity", "info")).lower()
            severity = Severity(sev_str)
            start_line = int(item.get("start_line", ctx.original_start_line))
            end_line = int(item.get("end_line", start_line))
            start_line = max(start_line, ctx.original_start_line)
            end_line = min(end_line, ctx.original_end_line)
            if end_line < start_line:
                end_line = start_line
            return Finding(
                agent="architecture",
                severity=severity,
                category=Category.ARCHITECTURE,
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
            logger.warning("Failed to parse architecture finding %r: %s", item, e)
            return None
