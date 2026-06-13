# Demo Video Script

## 0:00-0:30 Positioning

AgentOps MIS is not another agent builder. It is a management information system for AI digital employees: identity, tasks, tools, runs, approvals, memory, quality and audit.

## 0:30-1:20 Dashboard

Open `/dashboard`. Show total agents, task states, runtime health, OpenClaw import summary, recent runs and agent performance.

## 1:20-2:10 Agent And Task Management

Open `/agents`, then one agent detail page. Show performance card. Open `/tasks` and explain task ownership, risk, status and acceptance criteria.

## 2:10-3:10 Run Ledger

Open `/runs`. Pick a recent run. Show parent run, delegation id, child/sibling graph, tool calls and evaluations.

## 3:10-4:00 Human Approval And Memory

Open `/approvals` and `/memory`. Explain high-risk action governance and reviewed organizational memory.

## 4:00-5:20 Integrations

Open `/integrations`. Show:

- OpenClaw status/import/probe.
- Hermes unavailable as a recorded health state, not a crash.
- Agnesfallback dry-run fixed probe.
- Notion preview and dry-run export.

## 5:20-6:10 Base Switching

Use API or docs to show `/api/bases`, `/api/template-packages` and `/api/migration/preview`. Explain local base remains canonical while external bases are adapters.

## 6:10-6:40 Safety

Mention no credentials, private messages, full transcripts or raw prompts are stored. Summaries are redacted and hashed.

## 6:40-7:00 Close

This is a strong local MVP for classroom demonstration. Next step is product alpha: adapter hardening, RBAC, ledger trust and connector registry.
