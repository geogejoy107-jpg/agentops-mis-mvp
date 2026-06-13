# 实现计划

## Phase 0：本沙盒原型

已完成：

- 零依赖本地服务
- SQLite schema
- Seed data
- Mock runtime
- 核心页面
- API endpoints
- Run / Memory JSON export

## Phase 1：本地 Codex 迁移为 Next.js

1. 初始化 Next.js + TypeScript + Tailwind。
2. 迁移 schema 到 Prisma/Drizzle。
3. 迁移 seed data。
4. 迁移 API endpoints。
5. 迁移 UI 页面。
6. 实现 mock runtime server action。
7. 增加 lint/test。
8. 生成 OpenAPI 文档。

## Phase 2：真实 Adapter

1. Claude Code adapter：先只记录命令和输出，不给写权限。
2. Codex adapter：记录 prompt、repo、diff、测试状态。
3. OpenHands adapter：接 run/session/status，不直接控制 Docker。
4. CrewAI adapter：接 crew/task/agent/run metadata。
5. LangGraph adapter：接 trace/checkpoint/node events。

## Phase 3：治理增强

1. RBAC / workspace / tenant。
2. Secret vault，不允许 agent 持有 broad token。
3. Policy engine：Mission / Identity / Scope。
4. OTel/OpenInference ingestion。
5. Langfuse or Helicone optional integration。
6. Export and retention policies。

## Phase 4：商业化

1. SaaS workspace 计费。
2. Self-host / BYOC。
3. Workflow templates。
4. Agent / skill marketplace。
5. Enterprise audit pack。
