# 接入指南

> 如何在你的项目中使用 Code Review Agent：CLI 本地使用、GitHub Action 一键接入、`.cra.toml` 项目级配置。

---

## 目录

- [1. 安装](#1-安装)
- [2. CLI 本地使用](#2-cli-本地使用)
- [3. GitHub Action 一键接入](#3-github-action-一键接入)
- [4. 项目级配置 `.cra.toml`](#4-项目级配置-cratoml)
- [5. LLM Provider 配置](#5-llm-provider-配置)
- [6. 输出格式](#6-输出格式)
- [7. 退出码](#7-退出码)
- [8. 常见问题](#8-常见问题)

---

## 1. 安装

### 从源码安装（推荐，当前最新）

```bash
pip install "git+https://github.com/xuxiaxuan/code-review-agent.git@main"
```

### 从本地源码安装（开发模式）

```bash
git clone https://github.com/xuxiaxuan/code-review-agent.git
cd code-review-agent
pip install -e .
```

### 验证安装

```bash
code-review version
code-review info
```

---

## 2. CLI 本地使用

### 审查最近一次提交

```bash
code-review review --base HEAD~1 --head HEAD
```

### 审查分支差异

```bash
code-review review --base main --head feature/your-branch
```

### 审查指定文件 diff

```bash
# 先生成 diff 文件
git diff main...HEAD > my-changes.diff

# 审查
code-review review --diff my-changes.diff
```

### 只启用部分 Agent

```bash
# 只跑 correctness 和 security（更快、更省 token）
code-review review --base main --agents correctness,security
```

**可选 Agent**：

| Agent | 职责 | 适用场景 |
|---|---|---|
| `correctness` | 逻辑错误、资源泄漏、异常处理 | 所有项目（推荐默认启用） |
| `security` | SQL 注入、命令注入、硬编码密钥、反序列化 | 涉及用户输入/数据库/鉴权的项目 |
| `performance` | N+1 查询、不必要的循环嵌套、低效数据结构 | 高并发/大数据量项目 |
| `architecture` | SRP/DRY/KISS/YAGNI 违反、God Object | 长期维护的中大型项目 |

### 输出到文件

```bash
# Markdown 报告
code-review review --base main --format markdown -o review.md

# SARIF（用于上传 GitHub Code Scanning）
code-review review --base main --format sarif -o cra-results.sarif

# JSON（便于程序化处理）
code-review review --base main --format json -o review.json
```

### 调整置信度阈值

```bash
# 只保留高置信度的问题（更少误报，可能漏报）
code-review review --base main --confidence 0.8
```

默认 `0.5`。推荐范围：
- `0.3`：宽松（适合快速过一遍）
- `0.5`：默认（平衡）
- `0.8`：严格（适合提交前自查）

---

## 3. GitHub Action 一键接入

### 最简接入（3 分钟）

在你的目标仓库 `.github/workflows/code-review.yml` 写入：

```yaml
name: AI Code Review

on:
  pull_request:
    branches: [main, master]

permissions:
  contents: read
  security-events: write   # 必需：用于上传 SARIF 到 Code Scanning

jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: xuxiaxuan/code-review-agent@main
        with:
          api_key: ${{ secrets.CRA_API_KEY }}
```

### 工作机制

1. PR 触发 → Action 自动 checkout + 安装 Agent
2. 自动识别 PR 的 base/head 分支
3. 调用 LLM 进行多 Agent 审查
4. 生成 SARIF 报告 → 自动上传到 GitHub **Security** 标签页
5. PR 中会在对应代码行下方显示审查意见（Code Scanning annotation）

### 完整可配置参数

```yaml
- uses: xuxiaxuan/code-review-agent@main
  with:
    # 必填
    api_key: ${{ secrets.CRA_API_KEY }}      # LLM API Key

    # 可选 - 模型配置
    model: "deepseek/deepseek-chat"           # 模型名（见第 5 节）
    api_base: ""                              # 自定义 API Base（兼容接口用）

    # 可选 - 审查范围
    base: ""                                  # 留空则自动用 PR base
    head: "HEAD"                              # 默认 HEAD
    agents: "correctness,security,performance,architecture"

    # 可选 - 行为开关
    fail_on_high: "false"                     # true: 有 critical/high 则失败
    upload_sarif: "true"                      # false: 不上传到 Code Scanning
```

### 配置 Secret

在目标仓库 **Settings → Secrets and variables → Actions → New repository secret**：

- Name: `CRA_API_KEY`
- Value: 你的 LLM API Key（如 DeepSeek / Anthropic / 智谱开放平台）

### 多平台权限说明

| GitHub 平台 | SARIF 上传支持 |
|---|---|
| GitHub.com（公开仓库） | ✅ 免费 |
| GitHub.com（私有仓库） | ✅ 需要 GitHub Advanced Security |
| GitHub Enterprise | ✅ 需要 GHAS 许可 |
| GitHub Free（私有仓库） | ⚠️ 不支持上传，但可保存为 artifact |

如果用不上 Code Scanning，可以关闭上传并使用 artifact 下载：

```yaml
- uses: xuxiaxuan/code-review-agent@main
  with:
    api_key: ${{ secrets.CRA_API_KEY }}
    upload_sarif: "false"   # 不上传
    # SARIF 仍会作为 artifact 保存为 ai-code-review-sarif
```

---

## 4. 项目级配置 `.cra.toml`

在仓库根目录放一个 `.cra.toml`，所有团队成员都会应用相同的审查策略。**命令行参数优先级高于配置文件**。

### 完整示例

```toml
# .cra.toml
# Code Review Agent 项目级配置

[review]
# 启用的 Agent（CLI --agents 会覆盖此值）
enabled_agents = ["correctness", "security", "performance", "architecture"]

# 置信度阈值（0.0-1.0）
confidence_threshold = 0.5

# 单文件最多保留的 finding 数（按严重度排序后截断）
max_findings_per_file = 5

# 排除审查的路径（支持 glob）
[review.excluded_paths]
patterns = [
    "vendor/**",
    "**/*.generated.*",
    "**/*.pb.go",
    "tests/fixtures/**",
    "**/__pycache__/**",
]

# 自定义规则（Phase 2 将集成到 LLM 审查，当前仅记录）
[[review.custom_rules]]
id = "no-print-in-prod"
severity = "low"
pattern = "^\\s*print\\("
message = "生产代码不应包含 print 语句"

[[review.custom_rules]]
id = "no-todo"
severity = "info"
pattern = "(?i)TODO|FIXME|XXX"
message = "发现 TODO/FIXME 注释，建议跟进或转为 Issue"

[llm]
# 模型配置
model = "deepseek/deepseek-chat"

# 可选：预定义的 LLM profile（多团队配置用）
# profile = "cost_optimized"   # 或 "balanced" / "powerful"
```

### 优先级（从高到低）

1. **命令行参数**：`--agents`, `--confidence`, ...
2. **`.cra.toml`**：项目级配置
3. **环境变量**：`CRA_DEFAULT_MODEL`, `DEEPSEEK_API_KEY`, ...
4. **默认值**

---

## 5. LLM Provider 配置

Code Review Agent 基于 LiteLLM，支持所有主流 Provider。通过环境变量配置 API Key。

### DeepSeek（推荐，性价比最高）

```bash
export DEEPSEEK_API_KEY="sk-..."
export CRA_DEFAULT_MODEL="deepseek/deepseek-chat"
```

- 成本：约 $0.001-0.01 / PR
- 质量：满足日常审查需求

### Anthropic Claude

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export CRA_DEFAULT_MODEL="anthropic/claude-3-5-sonnet-20241022"
```

- 成本：较高
- 质量：最佳

### 智谱 GLM（兼容 Anthropic API）

```bash
export ANTHROPIC_API_KEY="<your-zhipu-key>"
export ANTHROPIC_API_BASE="https://open.bigmodel.cn/api/anthropic"
export CRA_DEFAULT_MODEL="anthropic/glm-5.2"
```

- 国内部署速度最快
- 中文项目表现优秀

### OpenAI / Azure OpenAI

```bash
export OPENAI_API_KEY="sk-..."
export CRA_DEFAULT_MODEL="openai/gpt-4o-mini"
```

### 本地模型（Ollama）

```bash
export CRA_DEFAULT_MODEL="ollama/llama3"
# 无需 API Key，但需要本地运行 Ollama
```

---

## 6. 输出格式

| 格式 | 参数 | 用途 |
|---|---|---|
| `text` | `--format text`（默认） | 控制台彩色输出 |
| `markdown` | `--format markdown` | 文档、PR 评论 |
| `json` | `--format json` | 程序化处理、二次开发 |
| `sarif` | `--format sarif` | GitHub Code Scanning |

### SARIF 示例

```json
{
  "version": "2.1.0",
  "runs": [{
    "tool": {
      "driver": {
        "name": "Code Review Agent",
        "rules": [
          { "id": "cra-security", "name": "SECURITY" },
          { "id": "cra-correctness", "name": "CORRECTNESS" }
        ]
      }
    },
    "results": [
      {
        "ruleId": "cra-security",
        "level": "error",
        "message": { "text": "SQL 注入漏洞..." },
        "locations": [{
          "physicalLocation": {
            "artifactLocation": { "uri": "auth.py" },
            "region": { "startLine": 7, "endLine": 8 }
          }
        }],
        "properties": {
          "agent": "security",
          "severity": "critical",
          "confidence": 1.0,
          "suggestion": "..."
        }
      }
    ]
  }]
}
```

---

## 7. 退出码

| 退出码 | 含义 | CI 行为 |
|---|---|---|
| `0` | 审查完成，无 blocker | 通过 |
| `1` | 发现 critical/high 问题（blocker） | 按配置决定是否失败 |
| `2` | 参数错误 / 配置错误 | 失败 |
| `5` | 内部错误（LLM 超时、解析失败等） | 失败 |
| `130` | 用户 Ctrl+C 中断 | 失败 |

### CI 中"发现问题就失败"

```bash
code-review review --base main
# 退出码 1 会自然让 CI step 失败
```

### CI 中"只报告不阻断"

GitHub Action 中设置 `fail_on_high: "false"`（默认），或 CLI 中：

```bash
# 忽略退出码
code-review review --base main || true
```

---

## 8. 常见问题

### Q1: LLM 调用超时怎么办？

默认 30s 超时，内置 tenacity 自动重试 3 次（指数退避 4-16s）。若仍失败：

- 检查网络到 LLM Provider 的连通性
- 换用更快的模型（如 `deepseek/deepseek-chat` 而非 `gpt-4o`）
- 检查 API Key 配额

### Q2: 没有发现任何问题？

可能原因：

1. **置信度阈值过高** → 降到 `--confidence 0.3`
2. **diff 过小** → 确认 `git diff base...head` 有内容
3. **文件被排除** → 检查 `.cra.toml` 的 `excluded_paths`
4. **Mock 模式** → 没配置 API Key 时会进入 mock 模式，只发假数据

### Q3: 误报太多怎么办？

1. **提高置信度**：`--confidence 0.7`
2. **减少启用 Agent**：`--agents correctness`（只跑最准的）
3. **限制每文件 finding 数**：`.cra.toml` 设 `max_findings_per_file = 3`
4. **查看 evidence**：每个 finding 都附带了 LLM 的证据链，便于人工复核

### Q4: Windows 控制台乱码？

CLI 已内置 UTF-8 处理。如果仍有问题，PowerShell 执行：

```powershell
chcp 65001
$env:PYTHONUTF8 = "1"
```

### Q5: 私有仓库可以用 GitHub Action 吗？

可以。`uses: xuxiaxuan/code-review-agent@main` 在私有仓库同样有效。但 SARIF 上传到 Code Scanning 需要 GitHub Advanced Security 许可（私有仓库）。如果没有，设 `upload_sarif: "false"`，SARIF 仍会作为 artifact 可下载。

### Q6: 如何在 GitLab CI 中使用？

当前 Action 是 GitHub Composite Action，但 CLI 本身是平台无关的。在 `.gitlab-ci.yml`：

```yaml
code-review:
  image: python:3.12
  script:
    - pip install "git+https://github.com/xuxiaxuan/code-review-agent.git@main"
    - code-review review --base $CI_MERGE_REQUEST_TARGET_BRANCH_NAME --format markdown -o review.md
  artifacts:
    paths:
      - review.md
  only:
    - merge_requests
```

---

## 反馈与贡献

- Issue：[github.com/xuxiaxuan/code-review-agent/issues](https://github.com/xuxiaxuan/code-review-agent/issues)
- PR：欢迎补充更多语言的 Agent / 更好的 prompt
