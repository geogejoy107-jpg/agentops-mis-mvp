# 技术方案

## 沙盒参考实现

为了保证你拿到包后无需安装任何 npm/pip 依赖即可运行，本包使用：

- Python 3 标准库 `http.server`
- SQLite 标准库 `sqlite3`
- 原生 HTML/CSS/JavaScript
- Mock runtime

优点：可直接运行、可离线演示、可快速验证 MIS 数据模型。

## 目标产品实现

本地 Codex 后续应迁移为正式工程线，但迁移必须走阶段门，不做一次性大重写：

```text
Frontend: Next.js App Router + TypeScript in `ui/next-app`, with Vite/React retained as the current canonical UI until parity passes
Backend: Next.js API Routes / Server Actions
Database: SQLite first, then Postgres
ORM: Prisma 或 Drizzle
Auth: Auth.js / Clerk later
Runtime adapters: mock first, then Claude Code / Codex / OpenHands / CrewAI / LangGraph
Observability: Agent Run Ledger first, then Langfuse / OTel / OpenInference
```

商业迁移闭环见 `docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md`。当前决策是：

1. Python control plane 继续承载 Agent Gateway、worker、ledger、approval、audit 和本地部署路径，直到生产安全与 API parity 通过。
2. Vite/React 继续作为当前产品 UI；`ui/next-app` 已作为 Next.js 并行迁移轨道启动，先承接 workspace cockpit、tasks、runs、approvals 与 `/api/mis/*` API proxy，再逐页通过 parity gate 替换。
3. SQLite 继续作为 Free Local 默认账本，Postgres 只在 storage boundary gate 之后作为 Team/Enterprise/BYOC 适配器进入。
4. Prisma/Drizzle 不是当前 Python 线的前置条件；只有当 Next.js 后端接管相应 API 或 Postgres adapter 需要时再引入。
5. 每次迁移都必须保留可运行本地 demo、Agent Gateway CLI/API 执行路径和可复现 smoke 证据。

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
