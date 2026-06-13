# 系统规划、分析与设计

## 1. 系统规划

### 背景

AI Agent 正在从“对话助手”变成可以调用工具、读写文件、执行任务、访问外部系统的数字员工。个人开发者和小团队会同时使用多个 Agent，但缺少统一管理系统。

### 建设目标

建设一个 AgentOps MIS，用于统一管理 AI 数字员工的身份、任务、运行、工具、审批、记忆、评价和审计。

### 用户角色

| 角色 | 关注点 |
|---|---|
| Founder / Team Owner | 任务进度、业务结果、成本、风险 |
| Agent Operator | Agent 状态、工具权限、运行日志 |
| Reviewer / Approver | 高风险动作审批、质量检查 |
| Auditor | 审计链、责任归因、数据留痕 |

### 系统边界

MVP 做管理控制面，不做新的大模型、不替代 OpenClaw/Hermes/CrewAI/LangGraph 等 runtime。

## 2. 系统分析

### 核心业务问题

1. Agent 分散，缺少统一目录。
2. 任务在聊天中流转，缺少结构化任务表。
3. Agent 做了什么不可追踪，缺少 run ledger。
4. 工具权限不清晰，高风险动作缺少审批。
5. 产出质量缺少评价和质量门。
6. 经验散落在对话和日志中，无法形成组织记忆。
7. 成本、失败和风险无法归因。

### 业务流程

```text
创建 Agent
-> 创建任务
-> 分派 Agent
-> 启动 Run
-> 记录 Tool Calls
-> 判断风险
-> 人工审批或自动完成
-> 生成 Evaluation
-> 生成 Memory Candidate
-> 写入 Audit Log
-> Dashboard 决策支持
```

### 功能需求

| 模块 | 主要功能 |
|---|---|
| Agent Registry | Agent 档案、角色、runtime、预算、工具权限 |
| Task Management | 任务创建、分派、状态、验收标准 |
| Run Ledger | 运行记录、模型、token、成本、trace、错误 |
| Tool Call Ledger | 工具调用、参数摘要、目标资源、风险等级 |
| Approval Workflow | 高风险动作审批、批准/拒绝、阻断 |
| Memory Governance | 候选记忆、scope、source、confidence、TTL、审核 |
| Evaluation | 质量门、score、pass/fail、rubric |
| Audit Log | 关键操作、before/after hash、tamper chain placeholder |
| Integrations | OpenClaw probe、Notion export、未来 Hermes/Figma/GitHub |

### 非功能需求

- 本地可运行。
- 零依赖优先。
- 默认不调用外部 API。
- 高风险动作 fail closed。
- 不隐藏 telemetry。
- 不存 credentials、私聊正文、完整 session transcript。

## 3. 系统设计

### 总体架构

```text
Web Dashboard
    ↓
Local Control Plane API
    ↓
AgentOps MIS Core Modules
    ↓
SQLite Database
    ↓
Mock Runtime / OpenClaw Probe / Notion Export
```

### 数据模型

| 表 | 说明 |
|---|---|
| `agents` | 数字员工档案 |
| `tasks` | 任务与验收标准 |
| `runs` | Agent 执行账本 |
| `tool_calls` | 工具调用账本 |
| `approvals` | 人工审批记录 |
| `memories` | 组织记忆候选和长期知识 |
| `evaluations` | 质量门与绩效评价 |
| `audit_logs` | 审计记录 |
| `artifacts` | 产出物引用 |

### 设计理由

- 使用结构化表而不是只保存聊天记录，体现 MIS 的管理对象和业务流程。
- 先用 mock runtime 保证课堂 demo 稳定，再用 OpenClaw probe 证明可以接入真实运行层。
- 用 approval 和 audit 处理风险，而不是依赖模型自觉。
- 用 memory candidate + human review 处理组织记忆，避免 Agent 乱记、错记。
- 用 Notion export 连接知识库和汇报工作流，为后续协作平台接入做准备。

## 4. 当前实现状态

已完成：

- 本地 Web Dashboard。
- REST API。
- SQLite schema。
- mock runtime。
- high-risk tool approval。
- memory candidate review。
- evaluation records。
- audit logs。
- OpenClaw v1 live probe。
- Notion export preview/dry-run/配置式导出。

未完成但已规划：

- Hermes probe。
- OpenClaw cron/subagent run metadata import。
- Next.js + Postgres 正式工程。
- RBAC / 多 workspace。
- Figma UI 设计。
- 双向 Notion sync。
