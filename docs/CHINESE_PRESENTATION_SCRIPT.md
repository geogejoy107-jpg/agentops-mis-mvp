# 10 分钟中文汇报口播脚本

## 0:00-2:00 项目简介：背景和目标

各位老师同学好，我们小组的项目是 **AgentOps MIS：AI 数字员工管理信息系统**。

这个项目的背景是：现在很多个人开发者、小团队已经开始同时使用多个 AI Agent，比如 Research Agent 负责调研，Builder Agent 负责写代码，QA Agent 负责检查，Ops Agent 负责日常自动化。但这些 Agent 通常散落在聊天工具、脚本、自动化平台和本地日志里。它们做了什么、花了多少钱、有没有越权、产出质量怎么样、经验有没有沉淀，都很难统一管理。

所以我们不是再做一个聊天机器人，也不是再做一个 Agent Builder，而是把 AI Agent 当作“数字员工”，设计一套管理信息系统。系统要管理的对象包括 Agent、任务、运行记录、工具调用、审批、组织记忆、质量评价和审计日志。

我们的目标是做一个面向一人公司和小型 AI 团队的控制面板，让多个 AI Agent 的工作可以被记录、流转、监控、评价和复用。

## 2:00-5:00 系统规划、分析与设计

从 MIS 的角度，我们先做系统规划：系统服务的用户主要是团队负责人、Agent 操作者和审计/质量检查者。团队负责人关心任务进度和业务价值，Agent 操作者关心运行状态和工具权限，审计者关心高风险动作、审批和日志。

接着做系统分析。我们把业务流程抽象成一条管理闭环：

```text
创建 Agent -> 创建任务 -> 分派任务 -> 启动运行 -> 记录工具调用
-> 高风险动作进入审批 -> 完成后生成质量评价
-> 沉淀组织记忆 -> 写入审计日志 -> Dashboard 展示
```

所以系统的核心功能模块分成八个：

1. Agent Registry：管理数字员工档案、角色、运行时、预算和工具权限。
2. Task Management：管理任务目标、负责人、协作 Agent、状态和验收标准。
3. Run Ledger：记录每次 Agent 执行，包括模型、token、成本、trace id 和结果。
4. Tool Call Ledger：记录 Agent 调用了什么工具、作用对象、风险等级和结果。
5. Approval Workflow：高风险工具调用需要人工批准或拒绝。
6. Memory Governance：把决策、SOP、失败案例等沉淀成候选组织记忆，并支持人工审核。
7. Evaluation / Quality Gate：对运行结果打分，判断是否通过质量门。
8. Audit Log：记录关键操作的审计链，支持追责和复盘。

数据库设计上，我们对应建立了 `agents`、`tasks`、`runs`、`tool_calls`、`approvals`、`memories`、`evaluations`、`audit_logs` 等核心表。这样系统不是只展示聊天记录，而是把 Agent 的工作变成结构化管理数据。

技术架构上，目前采用本地 Web Dashboard + Python 标准库 API + SQLite 数据库。执行层先用 mock runtime 保证演示稳定，同时已经接入了 OpenClaw 的真实 live probe，把 OpenClaw 的运行结果作为 `runtime_type=openclaw` 写入 Run Ledger。Notion 连接器用于把汇报摘要和系统指标导出到知识库。

## 5:00-6:00 商业价值与商业模式

这个系统的商业价值可以概括为一句话：让 AI Agent 从“会干活的工具”变成“可管理的组织资源”。

对小团队来说，它能减少任务混乱、上下文丢失和重复沟通；对企业来说，它能降低 Agent 越权、成本失控、质量不可控和审计缺失的风险。

未来商业模式可以分为四层：个人免费版用于学习和小规模使用；Pro 版按 workspace 或 agent run 收费；Team 版提供权限、审批、成本和质量看板；Enterprise 版支持私有化部署、SSO、审计保留和安全策略。

## 6:00-7:00 项目亮点

这个项目有四个亮点。

第一，它是 MIS 思路，不是普通聊天 demo。我们把 Agent、任务、运行、工具、审批、记忆和审计都设计成管理对象。

第二，它内置风险治理。高风险工具调用不会默认执行，而是进入人工审批队列。

第三，它有组织记忆闭环。Agent 运行后可以产生候选记忆，由人审核后变成长期知识。

第四，它已经接入真实 OpenClaw 运行信号，不只是 mock 数据。系统记录了 OpenClaw 的模型、耗时、token usage 和 trace id。

## 7:00-9:00 前后台 Demo

演示分成前台和后台两部分。

前台先打开 `/dashboard`，展示 Agent 数量、任务完成数、待审批数、成本、失败率和最近 Run Ledger。

然后打开 `/agents`，展示数字员工档案，包括 mock agents 和 OpenClaw agent。

接着打开 `/tasks`，展示任务看板和任务状态流转。

再打开 `/runs`，从列表中选择最新的 OpenClaw run，而不是依赖固定链接。进入详情后展示 run metadata、tool calls 和 evaluation。

然后打开 `/approvals`，展示高风险动作如何进入审批队列。

再打开 `/memory`，展示候选组织记忆如何被批准或拒绝。

最后打开 `/integrations`，展示 Notion connector 状态和汇报预览。未配置 token 时系统只 dry-run，不会联网；配置后可以把项目汇报工作台导出到 Notion。

后台演示可以补充三点：

1. API：访问 `/api/dashboard/metrics` 查看结构化指标。
2. 数据库：SQLite 中有 `agents`、`tasks`、`runs`、`tool_calls` 等表。
3. 脚本：`scripts/openclaw_v1_experiment.py` 可以复跑 OpenClaw 观测实验。

## 9:00-10:00 总结与后续

总结一下，我们完成的是一个 AgentOps MIS 的 MVP：它验证了 AI 数字员工可以被结构化管理，包括任务、运行、工具、审批、记忆、评价和审计。

当前版本重点是管理逻辑和本地可运行 demo。后续可以继续做三件事：第一，导入更多 OpenClaw/Hermes 真实运行数据；第二，升级为 Next.js + Postgres 的正式工程；第三，补充 Figma UI、Notion 双向同步和企业级 RBAC。

我们的核心判断是：未来不缺会执行任务的 Agent，缺的是能把 Agent 管起来的 MIS。
