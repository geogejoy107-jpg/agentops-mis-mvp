# Codex / Pro Handoff Prompt: Next.js 正式工程版

你是资深产品架构师 + 全栈工程师。请把本包中的 Python/SQLite/HTML 参考实现迁移成正式的 Next.js + TypeScript + Tailwind + SQLite + Prisma/Drizzle 工程。

## 目标

构建一个本地可运行的 AgentOps MIS / AI Workforce MIS。它不是 agent runtime，也不是 builder，而是 vendor-neutral Agent Management Control Plane。

保留并实现以下管理对象：

- Agent Registry
- Task Ledger
- Run Ledger
- Tool Call Ledger
- Approval Workflow
- Organizational Memory
- Evaluation / Quality Gate
- Audit Log
- Dashboard

## 输入文件

请先阅读：

1. `docs/PRODUCT_UNDERSTANDING.md`
2. `docs/TECHNICAL_SOLUTION.md`
3. `docs/ARCHITECTURE.md`
4. `docs/DATABASE_SCHEMA.md`
5. `docs/API_SPEC.md`
6. `docs/PAGE_INFORMATION_ARCHITECTURE.md`
7. `docs/COMPETITOR_MATRIX.md`
8. `docs/RISK_REGISTER.md`
9. `server.py` 中 mock runtime 行为
10. `static/app.js` 中页面交互

## 技术栈

优先：

```text
Next.js App Router
TypeScript
Tailwind
SQLite
Prisma 或 Drizzle
Recharts
Zod
Vitest
Playwright optional
```

如果选择 Prisma：

- 用 `schema.prisma` 建模所有表。
- 提供 `prisma/seed.ts`。
- 提供 `npm run db:reset`。

如果选择 Drizzle：

- 用 `drizzle/schema.ts`。
- 提供 migration。
- 提供 seed script。

## 页面

必须实现：

```text
/dashboard
/agents
/agents/[id]
/tasks
/tasks/[id]
/runs
/runs/[id]
/tool-calls
/approvals
/memory
/evaluations
/audit
/settings
```

## API

必须实现与 `docs/API_SPEC.md` 一致的 endpoints。可以用 Route Handlers 或 Server Actions，但外部接口语义必须一致。

## Mock Runtime

实现流程：

1. 用户启动 mock run。
2. 创建 run。
3. 随机生成 2-5 个 tool calls。
4. high/critical risk tool call 生成 approval，run 进入 waiting_approval。
5. 批准后继续完成。
6. 拒绝后 run blocked。
7. 完成后生成 evaluation、artifact、memory candidate。
8. 全流程写 audit log。

## 高风险工具

默认 high-risk：

- shell.exec
- github.push
- email.send
- file.delete
- database.write
- mcp.invoke

## Seed Data

至少包含：

- 5 agents: CoS, Research, Builder, QA, Ops
- 10 tasks
- 30 runs
- 30 tool calls
- 10 memory candidates
- 8 approvals
- 10 evaluations
- 50 audit logs

## 文档

生成并维护：

- README.md
- ARCHITECTURE.md
- DATABASE_SCHEMA.md
- API_SPEC.md
- SEED_DATA.md
- TEST_PLAN.md
- SECURITY.md

## 安全要求

- 不写真实 API key。
- `.env.example` 只放占位符。
- 真实外部调用默认关闭。
- 不引入隐藏 telemetry。
- 所有关键写操作写 audit log。
- 高风险动作 fail closed。
- 未来接入真实 runtime 时，adapter 必须输出统一 envelope：`run_id`, `task_id`, `agent_id`, `trace_id`, `tool_calls`, `cost`, `error`, `side_effects`, `approvals`。

## 验收标准

本地运行后可以完成：

1. 打开 `/dashboard`。
2. 创建 Agent。
3. 创建 Task。
4. 分派给 Research Agent。
5. 启动 mock run。
6. 查看 run ledger 和 tool call ledger。
7. 处理 approval。
8. 自动生成 evaluation。
9. 自动生成 memory candidate。
10. 批准 memory。
11. 查看 audit log。
12. 导出 runs 和 memories JSON。

## 实现顺序

1. 初始化工程和 schema。
2. Seed data。
3. API route handlers。
4. Dashboard 页面。
5. Agent / Task 页面。
6. Mock runtime。
7. Approval / Memory / Evaluation / Audit 页面。
8. Export JSON。
9. Tests。
10. README 和文档。

先输出你的计划和默认假设，再开始改代码。
