# AgentOps MIS Presentation Brief

## Title

AgentOps MIS: AI Digital Employee Management Information System

## One-Sentence Positioning

AgentOps MIS is a management information system for AI digital employees, designed to manage agent identity, tasks, tools, runs, approvals, memory, quality, audit and external work bases across runtimes such as OpenClaw, Hermes and Agnesfallback.

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
- OpenClaw import/probe for local runtime observability.
- Hermes/Agnesfallback connector for health, model discovery and fixed dry-run probes.
- Notion External Base for report, task and memory preview.
- Template + Base switching preview for product portability.

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
- OpenClaw cron/import and redacted scale demo are visible in the ledger.
- Hermes unavailable is recorded as a health result instead of crashing the system.
- Notion export is safe-by-default dry-run.
- Template/base switching shows how the product can connect Notion, W&B, Plane, Docmost and Mattermost later.

### 5. System Demo: 2 Minutes

Demo path:

1. Open `/dashboard`.
2. Show total agents, tasks, approvals and run ledger.
3. Open `/agents` and show mock agents plus OpenClaw agent.
4. Open `/tasks` and show task lifecycle.
5. Open a recent run and show graph fields: parent run, delegation id, child/sibling runs.
6. Show tool calls, evaluation and audit.
7. Open `/memory` and show candidate review.
8. Open `/integrations` and show OpenClaw, Hermes/Agnesfallback and Notion dry-run.
9. Show `/api/migration/preview` as the base-switching story.

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
