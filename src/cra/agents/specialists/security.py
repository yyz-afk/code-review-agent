"""Security Agent：专项安全审查。

v0.8.2：继承 BaseSpecialist，仅保留 prompt + mock 规则。
"""

from __future__ import annotations

from cra.agents.specialists.base import BaseSpecialist
from cra.core.models import Category, Finding, Severity

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


def _run_mock_rules(code: str, original_start: int, file_path: str) -> list[Finding]:
    """Mock 模式：基于规则匹配安全漏洞。"""
    findings: list[Finding] = []
    lines = code.splitlines()
    for i, line in enumerate(lines, start=1):
        for pattern, sev, title, desc, conf in _MOCK_PATTERNS:
            if pattern in line:
                orig_line = original_start + i - 1
                findings.append(
                    Finding(
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
                    )
                )
    return findings


# ============================================================
# Agent 实现
# ============================================================


class SecurityAgent(BaseSpecialist):
    """安全审查 Agent。"""

    name = "security"
    SYSTEM_PROMPT = SYSTEM_PROMPT
    default_category = Category.SECURITY

    def _run_mock_rules(self, code: str, original_start: int, file_path: str) -> list[Finding]:
        return _run_mock_rules(code, original_start, file_path)
