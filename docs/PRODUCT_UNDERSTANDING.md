# 产品理解

## 产品定位

AgentOps MIS / AI Workforce MIS 是面向一人公司、独立开发者、小型 AI 自动化团队的 **vendor-neutral Agent Management Control Plane**。

它不替代 Claude Code、Codex、OpenHands、CrewAI、LangGraph、OpenClaw、Hermes 等执行层 runtime；它位于这些工具之上，统一管理 AI Agent 的身份、任务、工具权限、运行账本、成本、组织记忆、审批、质量评价和审计。

## 要解决的问题

1. Agent 分散在多个工具中，没有统一目录。
2. Agent 做了什么不可见，缺少可追溯运行账本。
3. 任务、成本、质量、失败原因无法归因。
4. 团队记忆散落在聊天、邮件、Notion、GitHub issue、会议记录里。
5. 工具权限和审批边界不清晰。
6. 产出质量缺少质量门、评价指标和绩效看板。

## MVP 非目标

- 不训练大模型。
- 不做新的 agent builder。
- 不替代 LangGraph / CrewAI / OpenHands。
- 不接真实外部 API。
- 不实现完整 SaaS 多租户计费。

## MVP 目标

第一版目标是验证 MIS 闭环：

```text
Agent Registry -> Task Assignment -> Mock Run -> Tool Calls -> Approval -> Evaluation -> Memory Candidate -> Audit -> Dashboard
```

## 核心产品假设

真正缺口不是“会不会跑 agent”，而是“能不能管理 agent 的组合、风险、成本、质量与组织记忆”。因此本产品首先做管理对象模型，而不是 runtime。
