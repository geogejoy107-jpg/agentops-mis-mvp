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
- Agnesfallback fixed probe dry-run plan first, to show the default safety posture.
- Local live recording mode: enable `HERMES_ALLOW_REAL_RUN=true`, call `confirm_run:true`, then show the real fixed probe result.
- Notion preview and dry-run export.

Suggested narration:

> 这里不是说 Hermes 做不到，而是 default Hermes gateway 没开 8642 API server，所以 MIS 记录 unavailable health state。Agnesfallback profile 已经可以真实运行。现在我显式开启 live-demo 模式，并用 `confirm_run:true` 触发一次 fixed probe。运行成功后，它不会只停留在命令行，而是进入 Run Ledger、Runtime Event、Evaluation 和 Audit Log。

Recording steps:

```bash
python3 scripts/live_demo_verify.py before
curl -s -X POST http://127.0.0.1:8787/api/integrations/hermes/cli-probe \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
curl -s -X POST http://127.0.0.1:8787/api/integrations/hermes/cli-probe \
  -H "Content-Type: application/json" \
  -d '{"confirm_run": true}' | jq .
python3 scripts/live_demo_verify.py after
```

Then return to:

- `/runs`: latest Agnesfallback run.
- `/api/runtime-events` or audit page: runtime event for the fixed probe.
- `/evaluations`: rule result.
- `/audit`: confirmed runtime probe audit.

Key point: this is not just an API call. It enters the AgentOps MIS management ledger.

## 5:20-6:10 Base Switching

Use API or docs to show `/api/bases`, `/api/template-packages` and `/api/migration/preview`. Explain local base remains canonical while external bases are adapters.

## 6:10-6:40 Safety

Mention no credentials, private messages, full transcripts or raw prompts are stored. Summaries are redacted and hashed.

## 6:40-7:00 Close

This is a strong local MVP for classroom demonstration. Next step is product alpha: adapter hardening, RBAC, ledger trust and connector registry.
