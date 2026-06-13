# 用户输入 Prompt

用户要求构建一个面向一人公司 / 小团队的 AgentOps MIS / AI Workforce MIS。核心目标不是训练大模型，也不是做 agent builder，而是做 vendor-neutral 的 Agent Management Control Plane，统一管理：

- Agent 身份
- 任务
- 工具权限
- 运行日志
- 成本
- 组织记忆
- 审批
- 质量评价
- 审计

用户要求参考 AgentHub、Paperclip、OneManCompany、Mission Control、Rowboat、OpenHands、CrewAI issues、Dify/Langflow issues，并输出竞品矩阵、产品理解、技术方案、数据模型、页面信息架构、实现计划、风险和取舍。

用户还要求实现本地可运行 MVP。第一版只做 mock runtime，不调用真实 LLM，但数据模型和 API 要为未来接入 Claude Code / Codex / OpenHands / CrewAI / LangGraph 做准备。

必备模块：

1. Agent Registry
2. Task Management
3. Run Ledger
4. Tool Call Ledger
5. Approval Workflow
6. Organizational Memory
7. Evaluation / Quality Gate
8. Dashboard
9. Audit Log

必备页面：

/dashboard, /agents, /agents/[id], /tasks, /tasks/[id], /runs, /runs/[id], /tool-calls, /approvals, /memory, /evaluations, /audit, /settings

必备 API：

GET /api/agents, POST /api/agents, GET /api/tasks, POST /api/tasks, PATCH /api/tasks/:id/status, POST /api/mock-runs/start, POST /api/mock-runs/:id/complete, GET /api/runs, GET /api/tool-calls, approvals/memories/evaluations/dashboard/audit endpoints。

质量与安全要求：

- 不写真实 API key。
- 默认关闭外部调用。
- 高风险动作 fail closed。
- 所有关键写操作写审计日志。
- 不引入隐藏 telemetry。
- 可导出 runs 和 memories JSON。
