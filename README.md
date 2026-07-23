# Code Review Agent

> 基于 LLM Agent 的企业级 AI 代码审查系统

[![Status](https://img.shields.io/badge/status-design-orange)]()
[![Python](https://img.shields.io/badge/python-3.11+-blue)]()
[![License](https://img.shields.io/badge/license-TBD-lightgrey)]()

## 项目简介

Code Review Agent 是一个基于多 Agent 协作的 AI 代码审查系统，定位为**企业内部研发平台**。通过自动分析 GitHub/GitLab 的 Pull Request / Merge Request，输出高质量、低噪音的代码审查意见，帮助研发团队：

- **缩短 PR 等待时间**：7×24 小时即时响应，无需人工排队
- **提升审查质量**：多专家 Agent 并行 + 验证层过滤，误报率 < 10%
- **沉淀审查知识**：从团队历史反馈中持续学习，适配内部规范
- **覆盖深度问题**：基于代码图与上下文引擎，发现跨文件、架构级缺陷

## 核心特性

- 🎯 **精确率优先**：只报高置信度问题，宁可漏报也不误报
- 🧠 **多 Agent 协作**：安全/性能/正确性/架构等专家 Agent 各司其职
- 🔍 **深度上下文**：Tree-sitter AST + 代码图 + 按需检索
- 🌐 **双平台支持**：GitHub + GitLab 统一抽象，体验一致
- 💸 **成本可控**：多模型路由，小模型预筛 + 大模型深审
- 🔒 **私有化友好**：支持本地 LLM（Ollama/vLLM），数据不出内网
- 🧩 **可扩展**：Agent、工具、规则均插件化设计

## 技术栈

| 维度 | 选型 |
|---|---|
| 语言 / 运行时 | Python 3.11+ |
| Web 框架 | FastAPI + Uvicorn |
| Agent 编排 | LangGraph |
| 多模型调用 | LiteLLM |
| 代码解析 | tree-sitter |
| 静态分析 | Semgrep |
| Git 操作 | GitPython / pygit2 |
| 异步队列 | Celery + Redis |
| 向量库 | Qdrant |
| 持久化 | PostgreSQL + SQLAlchemy + Alembic |
| 沙箱 | Docker SDK for Python |
| 部署 | Docker Compose → Kubernetes |

## 文档导航

| 文档 | 内容 | 适用读者 |
|---|---|---|
| [系统设计](docs/SYSTEM_DESIGN.md) | 总体架构、模块划分、端到端流程、关键技术决策 | 架构师、后端开发 |
| [数据模型与 API](docs/DATA_AND_API.md) | ER 设计、Schema 定义、REST API 规范 | 后端开发、前端开发 |
| [Prompt 与 Agent 设计](docs/PROMPT_DESIGN.md) | Agent 角色定义、System Prompt、工具集、输出 Schema | AI 工程师、Prompt 工程师 |
| [安全与部署](docs/SECURITY_AND_DEPLOYMENT.md) | 权限模型、密钥管理、沙箱隔离、部署架构、监控 | 运维、安全工程师 |
| [实施路线](docs/IMPLEMENTATION_ROADMAP.md) | 分阶段计划、交付物、风险应对 | 项目经理、技术负责人 |

## 快速开始

> ⚠️ 项目处于设计阶段，以下为占位说明，将在 MVP 阶段补全。

```bash
# 克隆仓库
git clone <repo-url> code-review-agent
cd code-review-agent

# 安装依赖（待实现）
poetry install

# 配置环境变量（待实现）
cp .env.example .env

# 启动服务（待实现）
docker compose up -d
```

## 项目状态

当前阶段：**设计阶段**（Design Phase）

已完成：
- ✅ 行业调研（主流产品、开源方案、技术路线）
- ✅ 技术选型（技术栈锁定）
- ✅ 系统设计文档

进行中：
- 🚧 详细设计评审

后续规划：
- 📋 Phase 1：MVP 原型（单 Agent + CLI + diff 解析）
- 📋 Phase 2：多 Agent + 双平台接入
- 📋 Phase 3：规模化与持续优化

## 设计原则

| 原则 | 在本项目中的体现 |
|---|---|
| **KISS** | 单 Agent 能解决的不上多 Agent；自研轻量组件优先于引入重型框架 |
| **YAGNI** | 仅实现当前阶段明确所需；拒绝为"未来可能用到"预留复杂接口 |
| **DRY** | SCM Provider、LLM Provider、工具集统一抽象，消除重复 |
| **SRP** | 每个 Agent 只负责一类问题；每个模块单一职责 |
| **OCP** | Agent、工具、规则通过注册机制扩展，不修改核心代码 |
| **DIP** | 核心逻辑依赖抽象接口（ScmProvider / LlmProvider / Tool），不依赖具体实现 |

## License

待定（企业内部项目）
