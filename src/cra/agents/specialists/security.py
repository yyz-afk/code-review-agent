"""Security Agent：专项安全审查。

聚焦于安全漏洞：SQL 注入、命令注入、硬编码密钥、XSS、CSRF 等。
与 CorrectnessAgent 分工：correctness 查"逻辑错误"，security 查"可被利用的漏洞"。

Phase 1 v0.5：作为第二个专项 Agent 加入 Orchestrator。
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

SYSTEM_PROMPT = """你是安全代码审查专家，专注于发现可被攻击者利用的安全漏洞。

## 核心原则

1. **克制原则**：只报告你有充分证据认为是真实漏洞的问题。
   - 不报告代码风格问题
   - 不报告"理论可能但无具体利用路径"的问题

2. **证据原则**：明确说明攻击路径（输入源 → 漏洞点 → 危害）。

3. **可操作原则**：给出具体的修复代码。

## 检查清单（按严重度）

### Critical（必须报）
- **SQL 注入**：用户输入直接拼接 SQL（f-string、字符串拼接、format）
- **命令注入**：用户输入拼接到 shell 命令（subprocess + shell=True、os.system）
- **路径遍历**：用户输入拼接到文件路径
- **反序列化**：pickle/yaml.load 处理不可信数据
- **硬编码凭据**：源码中的密钥/密码/Token（sk-*、password=、api_key=）

### High
- **XSS**：用户输入直接插入 HTML（innerHTML、document.write、服务端模板）
- **SSRF**：用户输入作为 URL 发起服务端请求
- **敏感信息泄露**：错误信息泄露堆栈、日志中的敏感数据
- **弱加密**：MD5/SHA1 用于密码、固定 IV、ECB 模式

### Medium
- **不安全的随机数**：密码学场景使用 random 而非 secrets
- **CSRF**：缺少 token 校验
- **权限校验缺失**：敏感操作未校验用户身份

## 输出规范

输出严格 JSON 数组：
```json
{
  "severity": "critical|high|medium|low|info",
  "category": "security",
  "start_line": 123,
  "end_line": 125,
  "title": "一句话总结（含漏洞类型）",
  "description": "攻击路径和危害",
  "suggestion": "修复代码（用对应语言的代码块标签）",
  "evidence": "证据（输入源、漏洞点）",
  "confidence": 0.0
}
```

无问题返回 `[]`。绝对不要输出 JSON 以外内容。
"""


# ============================================================
# Mock 规则匹配（无 API Key 时降级）
# ============================================================

_MOCK_PATTERNS: list[tuple[str, Severity, str, str, float]] = [
    # (pattern, severity, title, description, confidence)
    # SQL 注入
    (
        'execute(f"',
        Severity.CRITICAL,
        "SQL 注入风险（f-string 拼接）",
        "SQL 查询通过 f-string 拼接，存在 SQL 注入风险。",
        0.95,
    ),
    (
        "execute(f'",
        Severity.CRITICAL,
        "SQL 注入风险（f-string 拼接）",
        "SQL 查询通过 f-string 拼接，存在 SQL 注入风险。",
        0.95,
    ),
    # 命令注入
    (
        "shell=True",
        Severity.CRITICAL,
        "shell=True 配合用户输入可能命令注入",
        "subprocess + shell=True + 用户输入 → 命令注入。",
        0.85,
    ),
    # 硬编码密钥
    (
        'API_KEY = "',
        Severity.HIGH,
        "硬编码 API Key",
        "源码中硬编码 API Key，泄露后可被滥用。",
        0.9,
    ),
    (
        'API_SECRET = "',
        Severity.HIGH,
        "硬编码 Secret",
        "源码中硬编码 Secret。",
        0.9,
    ),
    (
        'password = "',
        Severity.HIGH,
        "硬编码密码",
        "源码中硬编码密码。",
        0.9,
    ),
    # pickle 反序列化
    (
        "pickle.loads(",
        Severity.HIGH,
        "pickle 反序列化不可信数据",
        "pickle.loads 处理不可信数据会导致任意代码执行。",
        0.85,
    ),
    # yaml unsafe load
    (
        "yaml.load(",
        Severity.HIGH,
        "yaml.load 未指定 SafeLoader",
        "yaml.load 不指定 Loader 会导致任意代码执行。",
        0.8,
    ),
]


def _run_mock_rules(
    code: str, original_start: int, file_path: str
) -> list[Finding]:
    """Mock 模式：基于规则匹配安全漏洞。"""
    findings: list[Finding] = []
    lines = code.splitlines()
    for i, line in enumerate(lines, start=1):
        for pattern, sev, title, desc, conf in _MOCK_PATTERNS:
            if pattern in line:
                orig_line = original_start + i - 1
                findings.append(Finding(
                    agent="security",
                    severity=sev,
                    category=Category.SECURITY,
                    file_path=file_path,
                    start_line=orig_line,
                    end_line=orig_line,
                    title=title,
                    description=desc,
                    evidence=f"L{orig_line}: {line.strip()}",
                    confidence=conf,
                ))
    return findings


# ============================================================
# Agent 实现
# ============================================================


class SecurityAgent:
    """安全审查 Agent。"""

    name = "security"

    def __init__(self, llm_client: "LlmClient") -> None:
        self.llm = llm_client

    async def review(self, ctx: AgentContext) -> list[Finding]:
        """审查给定的上下文。"""
        if self.llm.mock_mode:
            return _run_mock_rules(
                ctx.file_content, ctx.original_start_line, ctx.file_path
            )

        # 真实 LLM 调用
        from cra.agents.specialists.correctness import (  # noqa: PLC0415
            _format_with_line_numbers,
        )

        numbered_code = _format_with_line_numbers(
            ctx.file_content, ctx.original_start_line
        )

        # 语言识别用于代码块标签
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
            f"以下代码片段在原文件中位于第 {ctx.original_start_line}-"
            f"{ctx.original_end_line} 行。\n\n"
            f"{code_block}\n\n"
            f"进行安全审查。输出 JSON findings 数组。"
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]

        parsed, response = await self.llm.complete_json(messages)
        if not isinstance(parsed, list):
            logger.warning(
                "Security LLM returned non-array: %s",
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
        """解析 LLM 输出为 Finding。"""
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
                agent="security",
                severity=severity,
                category=Category.SECURITY,
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
            logger.warning("Failed to parse security finding %r: %s", item, e)
            return None
