# 技术方案

## 沙盒参考实现

为了保证你拿到包后无需安装任何 npm/pip 依赖即可运行，本包使用：

- Python 3 标准库 `http.server`
- SQLite 标准库 `sqlite3`
- 原生 HTML/CSS/JavaScript
- Mock runtime

优点：可直接运行、可离线演示、可快速验证 MIS 数据模型。

## 目标产品实现

本地 Codex 后续应迁移为：

```text
Frontend: Next.js + TypeScript + Tailwind + Recharts
Backend: Next.js API Routes / Server Actions
Database: SQLite first, then Postgres
ORM: Prisma 或 Drizzle
Auth: Auth.js / Clerk later
Runtime adapters: mock first, then Claude Code / Codex / OpenHands / CrewAI / LangGraph
Observability: Agent Run Ledger first, then Langfuse / OTel / OpenInference
```

## 分层架构

```text
Channel / UI Layer
  Dashboard, Agent pages, Task board, Approval queue, Memory queue

Control Plane Layer
  Agent Registry, Task Ledger, Run Ledger, Tool Policy, Approvals, Evaluation

Memory Governance Layer
  Evidence, canonical memory, TTL, confidence, review status, ACL tags

Runtime Adapter Layer
  mock adapter now; future: Claude Code, Codex, OpenHands, CrewAI, LangGraph, OpenClaw, Hermes

Data Layer
  SQLite / Postgres tables: agents, tasks, runs, tool_calls, approvals, memories, evaluations, audit_logs
```

## 关键取舍

1. 先用 mock runtime，是为了避免被 Docker、OAuth、CLI、API key、插件市场依赖拖住。
2. 先做追加式 ledger，是为了保留审计能力。
3. 组织记忆先做结构化记录，不做向量检索。
4. 高风险工具调用默认 fail closed。
