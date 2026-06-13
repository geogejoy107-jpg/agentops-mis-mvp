# 沙盒可完成 vs 本地 Codex 完成

## 已在沙盒完成

- 可运行本地 mock prototype。
- SQLite schema。
- Seed data：agents、tasks、runs、tool calls、approvals、memories、evaluations、audit logs。
- UI 页面：dashboard、agents、tasks、runs、tool calls、approvals、memory、evaluations、audit、settings。
- REST API。
- Mock runtime。
- 文档：产品理解、技术方案、架构、数据库、API、测试、风险、竞品矩阵、实现计划。
- 打包 zip。

## 必须本地 Codex 完成

- Next.js + TypeScript + Tailwind 正式工程。
- Prisma/Drizzle migration。
- npm install、lint、test、build。
- 真实 OAuth / Bot / webhook 配置。
- 真实 Claude Code / Codex / OpenHands / CrewAI / LangGraph adapter。
- 真实 API key 与 secret vault。
- Docker sandbox 和部署调试。
- CI/CD。
- 多用户登录和 RBAC。
- 企业级审计保留和加密。

## 为什么这么分工

沙盒最适合做研究、规格、图表、mock data 和可演示 prototype；本地 Codex 才适合真实依赖、真实 credentials、真实 runtime 和部署。
