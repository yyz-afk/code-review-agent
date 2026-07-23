# 实施路线图

> 文档版本：v0.1（设计阶段）
> 最后更新：2026-07-22
> 状态：待评审

## 目录

- [1. 总体路线](#1-总体路线)
- [2. Phase 1：MVP 原型](#2-phase-1mvp-原型)
- [3. Phase 2：多 Agent + 双平台](#3-phase-2多-agent--双平台)
- [4. Phase 3：规模化与优化](#4-phase-3规模化与优化)
- [5. Phase 4：差异化与持续学习](#5-phase-4差异化与持续学习)
- [6. 风险与应对](#6-风险与应对)
- [7. 验收标准](#7-验收标准)

---

## 1. 总体路线

### 1.1 分阶段策略（YAGNI 驱动）

采用**垂直切片**方式：每个阶段交付一个**端到端可用**的版本，而非横向铺开所有模块。

```
Phase 1: MVP 原型       ── 单 Agent + CLI + diff 解析 → 控制台输出
Phase 2: 可用版本       ── 多 Agent + GitHub 接入 + PR 评论
Phase 3: 企业级         ── GitLab + 多模型路由 + 持久化 + 反馈闭环
Phase 4: 差异化         ── 学习能力 + 架构审查 + 本地 LLM
```

### 1.2 阶段概览

| 阶段 | 目标 | 核心交付 | 验证标准 |
|---|---|---|---|
| **Phase 1** | 验证技术链路 | 单 Agent CLI 工具 | 能发现真实 Bug |
| **Phase 2** | 可在团队试用 | GitHub 自动审查 | 误报率 < 20% |
| **Phase 3** | 企业内部推广 | 双平台 + 治理 | 误报率 < 10%，成本 < $5/PR |
| **Phase 4** | 建立护城河 | 学习能力 + 深度 | 精确率 > 90% |

---

## 2. Phase 1：MVP 原型

> **目标**：用最小代价跑通"diff 解析 → LLM 审查 → 输出 Finding"的核心链路。

### 2.1 范围

**In Scope**：
- ✅ CLI 工具（`code-review review --base main`）
- ✅ Git diff 解析（基于 GitPython）
- ✅ 单个 CorrectnessAgent（用 LangGraph 编排）
- ✅ LiteLLM 调用 Claude / DeepSeek
- ✅ JSON / Markdown 报告输出
- ✅ tree-sitter 基础 AST 解析（Python 单语言起步）

**Out of Scope（YAGNI）**：
- ❌ Web 服务 / API / Webhook
- ❌ 多 Agent 并行
- ❌ 数据库持久化
- ❌ 多 SCM 平台
- ❌ Critic 验证层
- ❌ 工具调用（无 find_usages 等）

### 2.2 任务分解（WBS）

```
Phase 1 ──┬── 1.0 兼容性处理（⚠️ Spike 发现）
          │    - Python 版本：3.12 推荐
          │    - litellm 锁定 >=1.50,<1.60
          │    - Python 3.13 时安装 legacy-cgi
          │    - Windows 设置 PYTHONUTF8=1
          │
          ├── 1.1 项目脚手架
          │    - Poetry 项目结构
          │    - 核心目录（core/context/agents/tools/cli）
          │    - lint/format/type-check 配置（ruff + mypy）
          │    - 单元测试框架（pytest）
          │
          ├── 1.2 Diff 解析器
          │    - GitPython 集成
          │    - unified diff 解析
          │    - FileChange / Hunk 数据结构
          │    - 基础测试（含真实 diff 样本）
          │
          ├── 1.3 AST 引擎（最小可用）
          │    - tree-sitter 集成（Spike 已验证 38万行/秒）
          │    - Python 语言支持
          │    - 符号定位（函数/类边界识别）
          │    - 基于 AST 的 hunk 切分
          │    - 符号级代码提取（节省 93% token）
          │
          ├── 1.4 LLM 调用层
          │    - LiteLLM 集成（mock 模式已验证）
          │    - Claude / DeepSeek Provider
          │    - 统一消息格式
          │    - 重试与超时
          │
          ├── 1.5 CorrectnessAgent
          │    - System Prompt 设计（参考 PROMPT_DESIGN.md）
          │    - JSON 输出校验（pydantic）
          │    - 与 LangGraph 集成（Spike 已验证并行可行）
          │
          ├── 1.6 CLI 入口
          │    - click / typer 实现
          │    - 参数：--base/--head/--format/--output
          │    - 错误处理与退出码
          │
          └── 1.7 端到端验证
               - 准备 5-10 个含已知 Bug 的 PR 样本
               - 跑通完整流程
               - 记录精确率与效果
```

> **📊 Spike 实测数据已更新预期**：
> - 单文件审查：< 1 秒（AST 解析毫秒级 + 1 次 LLM 调用）
> - 小 PR 审查：< 5 秒（多个 Agent 并行，提速 56%）
> - 单次审查成本：< $0.05（DeepSeek）/ < $0.50（Claude）

### 2.3 交付物

| 交付物 | 形式 |
|---|---|
| 可执行 CLI 工具 | `pip install -e .` 后可用 `code-review` 命令 |
| 示例报告 | `examples/reports/` 下若干样本输出 |
| 单元测试 | 覆盖率 > 70% |
| README | 安装、使用、配置说明 |

### 2.4 验收标准

| 标准 | 衡量方式 |
|---|---|
| **功能可用** | 能审查本地任意 Git 仓库的分支 diff |
| **发现真实 Bug** | 在 5 个样本 PR 中，至少发现 3 个已知 Bug |
| **输出结构化** | JSON 格式严格符合 Finding schema |
| **延迟可接受** | 单文件审查 < 30s |
| **成本可控** | 单次审查 < $0.50 |

---

## 3. Phase 2：多 Agent + 双平台

> **目标**：升级为可在 GitHub 上自动审查 PR 的服务，团队可开始试用。

### 3.1 范围

**In Scope**：
- ✅ Webhook Gateway（接收 GitHub Webhook）
- ✅ 异步队列（Celery + Redis）
- ✅ 多专家 Agent（Security / Correctness / Performance）
- ✅ Critic 验证层
- ✅ PR 评论发布（行内评论 + 摘要）
- ✅ PostgreSQL 持久化
- ✅ 基础工具集（search_code / find_usages）
- ✅ Triage 粗筛
- ✅ 多语言 AST（Java / TypeScript / Go）
- ✅ 基础可观测性（结构化日志 + Prometheus 指标）

**Out of Scope**：
- ❌ GitLab 支持（Phase 3）
- ❌ 多模型路由（Phase 3）
- ❌ 反馈学习（Phase 4）
- ❌ 沙箱执行（Phase 3）

### 3.2 任务分解

```
Phase 2 ──┬── 2.1 Web 服务
          │    - FastAPI 框架
          │    - Webhook 接收端点
          │    - HMAC 验签
          │    - REST API 基础（/reviews）
          │
          ├── 2.2 异步队列
          │    - Celery + Redis 集成
          │    - 任务序列化
          │    - 重试与死信队列
          │    - 幂等性去重
          │
          ├── 2.3 GitHub Provider
          │    - GitHub App 注册与配置
          │    - get_diff / get_file / post_comment
          │    - 权限模型（Installation Token）
          │
          ├── 2.4 持久化层
          │    - PostgreSQL Schema（reviews/findings/agent_runs）
          │    - SQLAlchemy 模型
          │    - Alembic 迁移
          │    - Repository 模式封装
          │
          ├── 2.5 多 Agent 编排
          │    - LangGraph 并行节点
          │    - Orchestrator 实现
          │    - 专家 Agent（Security/Correctness/Performance）
          │    - Agent 注册机制
          │
          ├── 2.6 Critic 验证层
          │    - 去重逻辑
          │    - 置信度过滤
          │    - 工具实证校验（可选）
          │
          ├── 2.7 工具集
          │    - search_code（基于 ripgrep）
          │    - find_usages（基于代码图）
          │    - get_file
          │    - run_semgrep
          │
          ├── 2.8 多语言 AST
          │    - 扩展 tree-sitter 语言：Java/TS/JS/Go
          │    - 代码图构建
          │    - 调用关系分析
          │
          ├── 2.9 PR 评论发布
          │    - 行内评论（Review Comment API）
          │    - 摘要评论
          │    - 严重度标签
          │    - 评论合并去重
          │
          └── 2.10 可观测性（基础）
               - structlog 日志
               - Prometheus 指标
               - 健康检查端点
```

### 3.3 验收标准

| 标准 | 目标 |
|---|---|
| **端到端可用** | GitHub PR 提交后自动触发审查并发布评论 |
| **响应时间** | Webhook 10s 内响应；审查 P95 < 10 min |
| **误报率** | < 20%（基于开发者反馈） |
| **采纳率** | > 50% 的 PR 收到至少一次有效反馈 |
| **稳定性** | 连续运行 7 天无重大故障 |

---

## 4. Phase 3：规模化与优化

> **目标**：扩展到 GitLab，引入多模型路由与企业级治理，支撑企业内部全面推广。

### 4.1 范围

- ✅ GitLab Provider
- ✅ 多模型路由（DeepSeek 预筛 + Claude/GPT 深审）
- ✅ 沙箱执行（Docker）
- ✅ 反馈记录与展示
- ✅ 完整 RBAC 权限
- ✅ 仓库配置（rules、excluded_paths、llm_profile）
- ✅ Prompt 缓存
- ✅ 大 PR Map-Reduce 处理
- ✅ 完整可观测性（OpenTelemetry 追踪）
- ✅ K8s 部署 + Helm Chart

### 4.2 任务分解（节选）

```
Phase 3 ──┬── 3.1 GitLab Provider
          ├── 3.2 多模型路由（LlmRouter）
          │    - 任务类型 → 模型映射
          │    - 失败降级链
          │    - 成本统计与预算控制
          ├── 3.3 沙箱集成
          │    - Docker SDK 集成
          │    - run_tests 工具
          │    - 镜像构建与管理
          ├── 3.4 反馈闭环
          │    - 评论事件监听
          │    - Feedback 记录
          │    - 精确率指标自动计算
          ├── 3.5 大 PR 处理
          │    - Map-Reduce 分块策略
          │    - 按文件/符号分发子 Agent
          │    - 跨块结果合并
          ├── 3.6 RBAC 与配置
          │    - JWT 认证
          │    - 权限矩阵实现
          │    - 仓库配置 CRUD
          ├── 3.7 K8s 部署
          │    - Helm Chart
          │    - HPA 自动伸缩
          │    - 私有化交付包
          └── 3.8 性能优化
               - Prompt 缓存
               - 向量检索预热
               - 增量审查
```

### 4.3 验收标准

| 标准 | 目标 |
|---|---|
| **双平台一致** | GitHub / GitLab 体验对齐 |
| **成本** | 单 PR 平均 < $5 |
| **精确率** | > 90%（基于反馈统计） |
| **大 PR** | 1000+ 行 PR 可在 15min 内完成 |
| **可用性** | 99.5% SLA |
| **私有化** | 可在客户内网部署 |

---

## 5. Phase 4：差异化与持续学习

> **目标**：建立护城河，通过学习能力与深度审查超越通用工具。

### 5.1 范围

- ✅ ML Comment Ranker（基于反馈训练）
- ✅ 团队规则学习（从历史 PR 提取模式）
- ✅ 架构审查 Agent（基于代码图的深度分析）
- ✅ TestQualityAgent（沙箱运行测试）
- ✅ 本地 LLM 支持（Ollama / vLLM）
- ✅ SARIF 输出（CI/SCC 集成）
- ✅ 语义检索（Qdrant RAG）
- ✅ 评估基准（内部 golden set）

### 5.2 关键任务

```
Phase 4 ──┬── 4.1 反馈学习
          │    - 反馈数据集构建
          │    - Comment Ranker 训练
          │    - 离线评估管道
          ├── 4.2 团队规则挖掘
          │    - 历史 PR 模式分析
          │    - 规则自动提取
          │    - 规则冲突检测
          ├── 4.3 架构深度审查
          │    - 代码图增强（包/模块级）
          │    - 循环依赖检测
          │    - 设计模式一致性
          ├── 4.4 本地 LLM 集成
          │    - Ollama / vLLM 适配
          │    - 路由策略（敏感仓库走本地）
          │    - 性能调优
          └── 4.5 评估体系
               - Golden set 构建
               - 精确率/召回率持续度量
               - A/B 测试框架
```

---

## 6. 风险与应对

### 6.1 技术风险

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| **LLM 误报率居高不下** | 高 | 高 | 渐进式优化：阈值调参 + Critic 强化 + 反馈学习 |
| **大 PR token 爆炸** | 高 | 中 | Map-Reduce + AST 精简 + Prompt 缓存 |
| **LangGraph 生产稳定性** | 中 | 高 | 监控 + 检查点 + 备用单 Agent 降级路径 |
| **tree-sitter 多语言维护成本** | 中 | 低 | 起步仅支持 3-4 种主流语言；其余降级为纯 diff |
| **LLM API 限流/不可用** | 中 | 高 | 多 Provider 路由 + 本地模型兜底 |
| **Prompt 注入攻击** | 低 | 高 | 严格隔离 + 输出校验 + 工具白名单 |

### 6.2 产品风险

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| **开发者不采纳** | 中 | 高 | 精确率优先；从单个团队试点；收集反馈快速迭代 |
| **与现有工具冲突**（如 SonarQube） | 中 | 中 | 明确分工：Agent 查逻辑问题，linter 查样式 |
| **成本超预算** | 中 | 中 | 模型路由 + 预算上限 + 月度成本报表 |
| **审查成为新瓶颈** | 低 | 中 | 并行化 + 增量审查 + 异步队列 |

### 6.3 工程风险

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| **进度延期** | 高 | 中 | 严格 YAGNI；每阶段独立可用；及时砍非核心 |
| **团队技术栈熟悉度** | 中 | 中 | 前期做 Spike；关键模块双人结对 |
| **依赖第三方服务变更**（API 变化） | 中 | 中 | 抽象层隔离；订阅变更通知 |

---

## 7. 验收标准

### 7.1 每阶段 Demo 标准

每个阶段结束前，必须能向团队演示**端到端可用的功能**：

| 阶段 | Demo 场景 |
|---|---|
| Phase 1 | 在本地仓库执行 CLI，输出结构化 Finding 报告 |
| Phase 2 | GitHub PR 提交后，自动出现审查评论 |
| Phase 3 | GitLab PR 同样可用；后台展示成本/精确率指标 |
| Phase 4 | 系统从反馈中学习，误报率持续下降 |

### 7.2 上线前检查清单

**功能**：
- [ ] 核心流程端到端通过
- [ ] 所有 Agent 单测覆盖 > 70%
- [ ] 集成测试覆盖关键路径
- [ ] 性能指标达标（延迟、成本）

**安全**：
- [ ] Webhook 验签
- [ ] RBAC 权限矩阵
- [ ] 敏感字段加密
- [ ] 审计日志完整

**运维**：
- [ ] 监控指标接入 Grafana
- [ ] 告警规则配置
- [ ] 备份策略落地
- [ ] runbook 文档完成

**文档**：
- [ ] 部署文档
- [ ] 用户使用指南
- [ ] API 文档（OpenAPI）
- [ ] 故障排查手册

---

## 附录

### A. 团队配置建议

| 阶段 | 建议人员配置 |
|---|---|
| Phase 1 | 1 名后端 + 0.5 名 AI 工程师 |
| Phase 2 | 2 名后端 + 1 名 AI 工程师 + 0.5 名运维 |
| Phase 3 | 3 名后端 + 1 名 AI + 1 名运维 + 0.5 名前端 |
| Phase 4 | 同 Phase 3，按需调整 |

### B. 工具链

| 用途 | 工具 |
|---|---|
| 依赖管理 | Poetry |
| 代码质量 | ruff + mypy + pre-commit |
| 测试 | pytest + pytest-asyncio + pytest-cov |
| CI/CD | GitHub Actions / GitLab CI |
| 容器化 | Docker + docker-compose |
| 编排 | Kubernetes + Helm |
| 监控 | Prometheus + Grafana + Loki |
| 追踪 | OpenTelemetry + Jaeger |

---

**结束语**：本路线图遵循 **YAGNI + 垂直切片** 原则，每阶段交付可验证的价值。建议在 Phase 1 完成后立即与真实用户（开发团队）沟通，根据反馈调整后续阶段的优先级。

设计阶段完成 → 进入 Phase 1 实施。
