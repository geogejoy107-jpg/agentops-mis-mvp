# Demo Video Script

## 0:00-0:30 Positioning

AgentOps MIS is not another agent builder. It is a local-first management information system for AI digital employees: identity, tasks, tools, async jobs, runs, approvals, memory, quality and audit.

## 0:30-1:25 Commander Console

Open `/workspace/agents`. Show:

- Demo readiness: a read-only canonical v1.5 recording checklist that ties together local readiness, security boundary, worker fleet lanes, async inbox, customer task loop and run ledger evidence.
- Local readiness: a read-only proof that the local workspace has Agent Gateway, worker, adapter route, approval, memory and evidence-chain coverage without starting live work.
- Commander project board / worker fleet view: current worker health, adapter readiness, pending/stuck work and recommended next CLI/API action.
- Async workflow jobs: long Hermes/OpenClaw work can be submitted, polled and recovered instead of held open in a brittle synchronous request.
- Async Integration Inbox: explain it as the commander review queue for returned worker results, slower lanes, stale jobs, blocked work and memory-review items.

Key point: the browser is for command, supervision, approval and review. Agents execute through Agent Gateway CLI/API.

## 1:25-2:15 Agent And Task Management

Open `/agents`, then one agent detail page. Show performance card. Open `/tasks` and explain task ownership, risk, status and acceptance criteria.

## 2:15-3:15 Run Ledger

Open `/runs`. Pick recent live proof runs:

- OpenClaw `run_gw_5f4a3320a4d3`
- Hermes `run_gw_f7fe3a78cadb`

Show status, linked task, tool calls, evaluations, audit evidence and delivery artifacts. Do not show raw prompts, raw model responses, credentials or private transcripts.

## 3:15-4:05 Human Approval And Memory

Open `/approvals` and `/memory`. Explain high-risk action governance, delivery acceptance and reviewed organizational memory. The same review loop is available through CLI: `agentops approval list/approve/reject` and `agentops memory list/approve/reject`.

## 4:05-5:15 Customer Worker Dispatch

From `/workspace/agents` or Pixel Office, submit a customer worker task through mock first, then explain confirmed Hermes/OpenClaw live mode:

- Mock is safe by default.
- Hermes/OpenClaw require explicit confirmation and adapter readiness.
- Long work uses async jobs plus `agentops workflow job-status --wait`.
- Results return as run/tool/evaluation/audit/artifact evidence, then move to human approval.
- Open the Customer Delivery Board in `/workspace/agents` or `/workspace/reports` to show the customer-facing readback: delivery artifact, linked task/run, approvals, evaluations, audit counts and next action.

Suggested narration:

> 这里的重点不是让 agent 点浏览器，而是让真实 Hermes / OpenClaw 通过 Agent Gateway CLI/API 接活、执行、写回证据。浏览器是 commander console：看 readiness、看 async job、审批交付、复盘 run ledger。

Recording steps:

```bash
./scripts/agentops demo readiness
./scripts/agentops local readiness
./scripts/agentops security production-readiness
./scripts/agentops worker fleet
./scripts/agentops commander inbox --bucket ready_for_review --limit 5
./scripts/agentops workflow customer-worker-task --adapter mock
./scripts/agentops review queue --limit 12
./scripts/agentops workflow delivery-board --limit 10
./scripts/agentops approval list --decision pending --limit 10
./scripts/agentops approval approve --approval-id <approval_id>
./scripts/agentops memory list --status candidate --limit 10
./scripts/agentops memory approve --memory-id <memory_id>
./scripts/agentops workflow customer-worker-task --adapter openclaw --confirm-run --async-job
./scripts/agentops workflow job-status --job-id <job_id> --wait
./scripts/agentops review queue --limit 12
./scripts/agentops workflow delivery-board --limit 10
```

Then return to:

- `/workspace/agents`: Human Review Queue / 人工审核队列 shows pending approvals, memory candidates, customer deliveries and recommended CLI actions in one operator queue. Approval and memory items can be approved/rejected inline; those decisions intentionally write audit/ledger evidence.
- `/workspace/reports`: customer delivery board and report links.
- `/workspace/approvals`: approval gate, or show the same decision through `agentops approval approve/reject`.
- `/memory`: memory candidate review, or show the same decision through `agentops memory approve/reject`.
- `/runs`: latest worker run.
- `/evaluations`: rule result.
- `/audit`: confirmed worker/audit trail.
- `/workspace/approvals`: delivery acceptance approval.

Key point: this is not just an API call. It enters the AgentOps MIS management ledger.

## 5:15-5:55 Integrations And Base Boundary

Open `/integrations`. Show OpenClaw/Hermes health, connector trust, Notion dry-run/export preview and base switching.

Use API or docs to show `/api/bases`, `/api/template-packages` and `/api/migration/preview`. Explain local base remains canonical while external bases are adapters.

Do not claim Dify live sync or Notion bidirectional sync in this demo. Do not claim hosted SaaS, billing or production multi-tenant fleet management.

## 5:55-6:35 Safety

Mention no credentials, private messages, full transcripts or raw prompts are stored. Summaries are redacted and hashed.

## 6:35-7:00 Close

This is a strong local MVP for classroom demonstration: commander readiness, async worker management, integration inbox, CLI/API-first execution and real Hermes/OpenClaw dogfood evidence. Next step is product alpha: adapter hardening, RBAC, ledger trust and connector registry.
