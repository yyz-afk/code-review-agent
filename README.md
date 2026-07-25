# Code Review Agent

> 基于 LLM 多 Agent 的 AI 代码审查工具。一行命令审查 diff，一行配置接入 GitHub Action。

[![CI](https://github.com/xuxiaxuan/code-review-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/xuxiaxuan/code-review-agent/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11+-blue)]()
[![Status](https://img.shields.io/badge/status-v0.8-green)]()

## 项目简介

Code Review Agent 是一个基于多 Agent 协作的 AI 代码审查工具，通过分析 Git diff 自动发现代码缺陷。支持 GitHub Action 一键接入、CLI 本地运行、项目级配置。

**核心能力：**

- 🎯 **精确率优先**：多 Agent 并行 + 独立 Critic 验证层，误报率 < 10%
- 🧠 **四类专家 Agent**：正确性 / 安全 / 性能 / 架构
- 🌍 **多语言 AST**：Python / JavaScript / TypeScript / Java / Go（tree-sitter）
- 🔌 **多模型路由**：DeepSeek / Claude / GLM / OpenAI / Ollama（LiteLLM）
- 📤 **SARIF 标准**：原生接入 GitHub Code Scanning
- ⚙️ **项目级配置**：`.cra.toml` 统一团队审查策略

## 快速开始

### 1. 安装

```bash
pip install "git+https://github.com/xuxiaxuan/code-review-agent.git@main"
```

### 2. 配置 LLM Key

```bash
# 以 DeepSeek 为例（性价比最高）
export DEEPSEEK_API_KEY="sk-..."
```

### 3. 审查 diff

```bash
# 审查最近一次提交
code-review review --base HEAD~1

# 审查分支差异
code-review review --base main --head feature/your-branch
```

### 4. GitHub Action 一键接入

在目标仓库 `.github/workflows/code-review.yml`：

```yaml
name: AI Code Review
on:
  pull_request:
    branches: [main]
permissions:
  contents: read
  security-events: write
jobs:
  review:
    runs-on: ubuntu-latest
    steps:
      - uses: xuxiaxuan/code-review-agent@main
        with:
          api_key: ${{ secrets.CRA_API_KEY }}
```

详细接入步骤见 **[接入指南](docs/INTEGRATION.md)**。

## Agent 能力矩阵

| Agent | 检测内容 | 示例 |
|---|---|---|
| **correctness** | 逻辑错误、资源泄漏、异常吞没、边界缺失 | 数据库连接未关闭、`except: pass`、除零、索引越界 |
| **security** | SQL 注入、命令注入、硬编码密钥、不安全反序列化 | `cursor.execute(f"...{user}")`、`shell=True`、`pickle.loads` |
| **performance** | N+1 查询、低效循环、不必要的数据拷贝 | 循环内执行 SQL、`O(n²)` 嵌套 |
| **architecture** | SRP/DRY/KISS/YAGNI 违反、God Object、过度封装 | 50+ 行函数、纯透传函数、重复抽象 |

所有 Agent 并行执行，结果交由独立 **CriticAgent** 去重 + 置信度过滤。

## 配置

### CLI 参数

```
code-review review --help

Options:
  -b, --base TEXT         Base ref（分支/commit/tag）
  --head TEXT             Head ref，默认 HEAD
  -r, --repo PATH         Git 仓库路径，默认当前目录
      --diff PATH         从 diff 文件读取（替代 git diff）
  -f, --format [text|markdown|json|sarif]
                          输出格式，默认 text
  -o, --output PATH       输出到文件
      --confidence FLOAT  置信度阈值（默认 0.5）
      --agents TEXT       启用 Agent（逗号分隔）
  -q, --quiet             静默模式
```

### 项目级配置 `.cra.toml`

```toml
[review]
enabled_agents = ["correctness", "security", "performance", "architecture"]
confidence_threshold = 0.5
max_findings_per_file = 5

[review.excluded_paths]
patterns = ["vendor/**", "**/*.generated.*", "tests/fixtures/**"]

[llm]
model = "deepseek/deepseek-chat"
```

完整字段说明见 **[接入指南 - 项目级配置](docs/INTEGRATION.md#4-项目级配置-cratoml)**。

## 支持的 LLM Provider

| Provider | 模型示例 | 环境变量 |
|---|---|---|
| DeepSeek（推荐） | `deepseek/deepseek-chat` | `DEEPSEEK_API_KEY` |
| Anthropic Claude | `anthropic/claude-3-5-sonnet-20241022` | `ANTHROPIC_API_KEY` |
| 智谱 GLM | `anthropic/glm-5.2` | `ANTHROPIC_API_KEY` + `ANTHROPIC_API_BASE` |
| OpenAI | `openai/gpt-4o-mini` | `OPENAI_API_KEY` |
| Ollama（本地） | `ollama/llama3` | 无需 Key |

## 输出格式

| 格式 | 用途 | 命令 |
|---|---|---|
| `text` | 控制台彩色输出（默认） | `--format text` |
| `markdown` | PR 评论 / 文档 | `--format markdown -o review.md` |
| `json` | 程序化处理 | `--format json -o review.json` |
| `sarif` | **GitHub Code Scanning** | `--format sarif -o cra-results.sarif` |

## 技术栈

| 维度 | 选型 |
|---|---|
| 语言 / 运行时 | Python 3.11+ |
| CLI | typer + rich |
| Agent 编排 | asyncio.gather + Semaphore（并行） |
| 多模型调用 | LiteLLM |
| 代码解析 | tree-sitter（5 语言） |
| LLM 重试 | tenacity（指数退避） |
| 数据模型 | pydantic v2 |

## 文档导航

| 文档 | 内容 |
|---|---|
| **[接入指南](docs/INTEGRATION.md)** | CLI / GitHub Action / GitLab CI 用法、配置、FAQ |
| [系统设计](docs/SYSTEM_DESIGN.md) | 总体架构、模块划分、端到端流程 |
| [数据模型与 API](docs/DATA_AND_API.md) | 数据 Schema、REST API 规范 |
| [Prompt 与 Agent 设计](docs/PROMPT_DESIGN.md) | Agent 角色定义、System Prompt |
| [安全与部署](docs/SECURITY_AND_DEPLOYMENT.md) | 权限模型、密钥管理、部署架构 |
| [实施路线](docs/IMPLEMENTATION_ROADMAP.md) | 分阶段计划 |

## 开发

```bash
# 克隆 + 开发模式安装
git clone https://github.com/xuxiaxuan/code-review-agent.git
cd code-review-agent
pip install -e ".[dev]"

# 运行测试
pytest tests/ -v --cov=cra

# 代码检查
ruff check src/ tests/
mypy src/cra/
```

## 项目状态

- ✅ v0.1-v0.4：MVP（单 Agent + 多语言 AST + Hunk 行号映射）
- ✅ v0.5：SecurityAgent + LLM 重试 + 并行文件审查
- ✅ v0.6：PerformanceAgent + ArchitectureAgent
- ✅ v0.7：独立 CriticAgent + GitHub CI
- ✅ v0.8：SARIF 输出 + GitHub Action + `.cra.toml` 项目级配置
- 🚧 v0.9：GitLab MR 支持 + PR inline 评论
- 📋 v1.0：Web Dashboard + 团队反馈学习

## 设计原则

| 原则 | 在本项目中的体现 |
|---|---|
| **KISS** | 单文件能解决的不上 LangGraph；asyncio 原生编排 |
| **YAGNI** | 不为"未来可能用到"预留复杂接口；Mock 模式让没 Key 也能跑 |
| **DRY** | `specialists/base.py` 抽象 Agent 公共逻辑；统一 `render()` 入口 |
| **SRP** | 每个 Agent 只负责一类问题；CriticAgent 独立负责验证 |
| **OCP** | 通过 `AGENT_REGISTRY` 注册新 Agent，不修改 Orchestrator |
| **DIP** | 核心逻辑依赖 `ReviewConfig` 抽象，不绑定具体 LLM Provider |

## License

待定（企业内部项目）
