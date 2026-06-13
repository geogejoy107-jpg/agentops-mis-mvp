# AgentOps MIS Presentation Brief

## Title

AgentOps MIS: AI Digital Employee Management Information System

## One-Sentence Positioning

AgentOps MIS is a management information system for AI digital employees, designed to manage agent identity, tasks, tools, runs, approvals, memory, quality and audit across runtimes such as OpenClaw and Hermes.

## 10-Minute Structure

### 1. Project Introduction: 2 Minutes

Problem:

- Teams are starting to use multiple AI agents, but their work is scattered across chats, scripts, tools and logs.
- Existing agent builders focus on creating agents, not managing them as organizational resources.
- Without a management layer, agent work becomes hard to audit, evaluate, approve, cost-control and reuse.

Goal:

- Build an AgentOps MIS control plane for one-person companies and small AI teams.
- Treat agents as digital employees with roles, permissions, tasks, performance and memory.

### 2. System Planning, Analysis and Design: 3 Minutes

Core management objects:

- Agent
- Task
- Run
- Tool Call
- Approval
- Memory
- Evaluation
- Audit Log

Core workflow:

```text
Agent Registry
-> Task Assignment
-> Run Ledger
-> Tool Call Ledger
-> Approval Workflow
-> Evaluation / Quality Gate
-> Organizational Memory
-> Audit Log
-> Dashboard
```

Architecture:

- Web dashboard for management views.
- Local API control plane for structured operations.
- SQLite as local MIS database.
- Mock runtime for deterministic demo.
- OpenClaw v1 probe for real runtime observability.
- Notion export connector for report and knowledge workflow.

Design principle:

- Do not replace agent runtimes.
- Sit above them as a vendor-neutral control plane.

### 3. Business Value and Model: 1 Minute

Business value:

- Makes AI agent work visible, auditable and controllable.
- Reduces repeated context loss by preserving organizational memory.
- Helps small teams coordinate multiple agents safely.
- Connects cost, quality and risk to actual tasks.

Commercial direction:

- SaaS/BYOC control plane.
- Free personal version, Pro workspace subscription, Team governance tier, Enterprise/self-host license.
- Future marketplace for agent workflows, skills and connectors.

### 4. Project Highlights: 1 Minute

Highlights:

- MIS object model is not a chat demo.
- High-risk tool calls enter approval.
- Runs record cost, token usage, errors and trace id.
- Memory candidates require review.
- Audit logs include before/after hashes and tamper-chain placeholder.
- OpenClaw live probe has already been recorded as a real `runtime_type=openclaw` run.
- Broad community research protocol is packaged as a Codex skill.

### 5. System Demo: 2 Minutes

Demo path:

1. Open `/dashboard`.
2. Show total agents, tasks, approvals and run ledger.
3. Open `/agents` and show mock agents plus OpenClaw agent.
4. Open `/tasks` and show task lifecycle.
5. Open `/runs/run_v1_openclaw_probe_20260613T122349Z`.
6. Show tool calls, evaluation and audit.
7. Open `/memory` and show candidate review.
8. Open `/integrations` and show Notion export preview/status.

## Recommended Slide Titles

1. Why Agent-MIS
2. Target Users and Use Cases
3. Management Object Model
4. System Workflow
5. Architecture
6. Data Model
7. OpenClaw Integration Demo
8. Notion/Knowledge Workflow
9. Business Value
10. Risks and Future Work

## Key Message

The project is not another agent builder. It is a management system that makes AI digital employees manageable, auditable, evaluable and reusable.
