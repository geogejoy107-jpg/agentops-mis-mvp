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
Backend: Next.js API Routes / Server Actions, with Python retained only as a bounded migration rollback
Database: SQLite for Free Local; Postgres by default for commercial/BYOC control-plane routes
Data access: Node `pg` for the first transaction-critical slice; introduce Drizzle when the owned TypeScript schema surface widens
Auth: Auth.js / Clerk later
Runtime adapters: Agent Gateway with real OpenClaw/Hermes release gates; mock only for deterministic CI/offline fallback
Observability: Agent Run Ledger first, then Langfuse / OTel / OpenInference
```

商业迁移闭环见 `docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md`。当前决策是：

1. 生产安全与 Postgres storage boundary 已支持垂直接管；Agent Gateway task、run start/heartbeat 及 tool/evaluation/artifact evidence 精确路由已由 TypeScript 直接鉴权、事务写 Postgres、记录 runtime/audit，Python 不再是唯一后端。
2. Next.js 继续逐路由接管；尚未迁移的 `/api/mis/*` 暂时代理 Python，`AGENTOPS_TS_CONTROL_PLANE_MODE=proxy` 是迁移期回滚开关，不是商业目标架构。
3. SQLite 只保留为 Free Local 默认账本；商业生产与 BYOC 主控路径默认 Postgres，缺少 DSN 时 fail closed。
4. 第一条安全关键事务使用 Node `pg` 明确控制锁、鉴权和审计链；TypeScript 拥有的表面扩大后再引入 Drizzle schema，避免同时重写全部 ledger。
5. 每次迁移都必须保留可运行本地 demo、Agent Gateway CLI/API 执行路径和可复现 smoke 证据。
6. 商业 CI 不接受浮动执行输入：runner、GitHub Actions、Python、Node、Playwright CLI 和 Postgres 镜像均固定，更新时必须同时更新 `commercial_ci_supply_chain_pins_v1` 证据。

## 当前迁移状态

| 边界 | 当前所有者 | 允许的旧线 | 当前结论 |
| --- | --- | --- | --- |
| Task create/list | Next.js/TypeScript + Postgres | Free Local 或显式 `proxy` rollback | 已直接拥有，不以 Python 代理成功作为迁移证据 |
| Run start | Next.js/TypeScript + Postgres | Free Local 或显式 `proxy` rollback | 已直接拥有，包含鉴权、任务/运行绑定、幂等与审计事务 |
| Run heartbeat | Next.js/TypeScript + Postgres | Free Local 或显式 `proxy` rollback | 已直接拥有，终态单赢家且不能复活 |
| Agent Plan submit | Next.js/TypeScript + Postgres | Free Local 或显式 `proxy` rollback | 已直接拥有；non-mock run 缺少可验证 Plan 时 fail closed |
| Plan-evidence manifest create/verify | Next.js/TypeScript + Postgres | Free Local 或显式 `proxy` rollback | 已直接拥有；证据查询按 workspace 约束且 manifest 绑定不可改写 |
| 其他尚未通过 parity 的控制面路由 | 逐路由迁移中 | Python 仅作有界 rollback | 不能据此宣称商业后端迁移完成 |
| 商业账本 | Postgres | SQLite 仅 Free Local 和显式 rollback | 生产/BYOC 缺少 DSN 时 fail closed |

这表示后端迁移已经开始并形成了真实所有权，不表示 release complete。当前
精确 HEAD 仍必须完成真实 Agent Gateway、OpenClaw、Hermes 运行验收；mock
只能用于确定性 CI/offline fallback，不能替代产品发布证据。

## Promotion 信任边界

发布级 promotion 只信任固定仓库
`geogejoy107-jpg/agentops-mis-mvp`、workflow ID `301537454`、workflow path
`.github/workflows/commercial-migration-ci.yml`、`push` event、当前 branch/HEAD、
run ID 和正整数 `run_attempt`。它拒绝 Git replace objects、alternate object
directories 和 legacy grafts，并要求 aggregate artifact ZIP 只有一个规范文件；
JSON 的顶层键、GitHub run 键、scope 键、必需 jobs、hash、敏感信息省略标记和
`release_complete=false` 等状态都必须严格匹配 schema。

确认 promotion 时，真实 runtime 使用固定的系统 Python、固定参数、固定
`/usr/bin:/bin` PATH 和 loopback `NO_PROXY`；不继承代理变量、Git 重定向、
Python 启动覆盖或 `GITHUB_TOKEN`/`GH_TOKEN`。真实 Gateway/OpenClaw/Hermes
完成后，promoter 必须再次检查 Git HEAD，并重新从 GitHub API 验证同一个
workflow/run attempt、五个 jobs 和 aggregate artifact。只有二次验证仍与运行前
一致，才允许原子更新 release-grade receipts。

## 分层架构

```text
Channel / UI Layer
  Dashboard, Agent pages, Task board, Approval queue, Memory queue

Control Plane Layer
  Agent Registry, Task Ledger, Run Ledger, Tool Policy, Approvals, Evaluation

Memory Governance Layer
  Evidence, canonical memory, TTL, confidence, review status, ACL tags

Runtime Adapter Layer
  Agent Gateway; real OpenClaw/Hermes release gates; mock CI fallback; future additional adapters

Data Layer
  SQLite / Postgres tables: agents, tasks, runs, tool_calls, approvals, memories, evaluations, audit_logs
```

## 关键取舍

1. Mock runtime 只用于确定性 CI/offline fallback；发布级结论必须来自精确 HEAD 的真实 Agent Gateway、OpenClaw、Hermes 验收。
2. 先做追加式 ledger，是为了保留审计能力。
3. 组织记忆先做结构化记录，不做向量检索。
4. 高风险工具调用默认 fail closed。
