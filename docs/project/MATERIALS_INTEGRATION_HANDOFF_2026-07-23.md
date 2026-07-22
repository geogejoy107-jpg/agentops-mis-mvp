# AgentOps MIS 项目材料对接基线与开发交接

> Date: 2026-07-23
> Canonical: false

## Purpose

整合 2026-06-21 至 2026-06-23 项目讨论材料，并与当前 GitHub/Notion 状态重新对齐。

## Authority

- GitHub: 代码、branch、commit、PR、CI 事实。
- AgentOps MIS: Run、Tool、Approval、Artifact、Evaluation、Audit 事实。
- Notion Project Ledger + docs/project: 审核后的项目状态和决策。
- Chat history: source material，不是 canonical。

## Product Position

AgentOps MIS 是 Agent Control Plane，不是 LLM runtime。
它管理 Codex、Hermes、OpenClaw 等执行者的项目目标、任务、计划、审批、证据和审计。

## Integrated Tracks

1. Governance / Keep Green
2. Local Product / Private Host
3. Governed Agent & Codex Dogfood
4. Spatial OS
5. Research Lab
6. Skill / Context Self-Evolution

## Boundaries

- Spatial OS 是 MIS 状态投影，不拥有 workspace/task/run/approval/artifact/evaluation/audit 真相。
- Codex workspace-write 必须经过 Agent Plan、Prepared Action、审批、managed worktree、验证和证据链。
- External Base、MLflow、Runtime 不替代 MIS authority objects。
- Candidate Skill/Memory 不自动进入 Canonical。

## Next Actions

1. 审核是否刷新 PROJECT_STATE/BACKLOG/HANDOFF。
2. 完成 Private Host PR #104 用户验收。
3. 用真实项目跑通 Goal → Plan → Approval → Run → Artifact → Evaluation → Audit 闭环。
