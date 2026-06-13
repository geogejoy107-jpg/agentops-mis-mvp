# Demo Checklist

## Before Class

Start the local service:

```bash
cd /Users/wuji/Documents/MIS/code/agentops-mis-mvp
python3 server.py
```

Open:

```text
http://127.0.0.1:8787/dashboard
```

Verify:

```bash
curl -fsS http://127.0.0.1:8787/api/dashboard/metrics
curl -fsS http://127.0.0.1:8787/api/integrations/openclaw/status
curl -fsS http://127.0.0.1:8787/api/integrations/hermes/status
curl -fsS http://127.0.0.1:8787/api/integrations/notion/status
curl -fsS http://127.0.0.1:8787/api/integrations/notion/export-preview
```

## Frontend Demo Path

1. `/dashboard`
   - Show total agents, runtime health, OpenClaw cron health, Agent performance summary, recent runs and cost.

2. `/agents`
   - Show digital employee registry.
   - Mention `runtime_type` can be `mock`, `openclaw`, `hermes`, etc.
   - Open an OpenClaw agent detail page and show the performance card.

3. `/tasks`
   - Show task table and kanban.
   - Explain task status flow.

4. `/runs`
   - Open the latest `runtime_type=openclaw` run if available.
   - Show parent run, delegation id, child runs and sibling runs.
   - Fallback: open any recent completed run.

5. `/tool-calls`
   - Show tool name, risk level, status and target resource.

6. `/approvals`
   - Show pending approval queue.
   - Explain high-risk actions fail into human review.

7. `/memory`
   - Show candidate memory review.
   - Explain organizational memory governance.

8. `/integrations`
   - Show OpenClaw status, import local data, and manual probe.
   - Show Hermes status and manual probe. If Hermes API is not listening, show `unavailable` as a recorded health result.
   - Show Notion status and report preview.
   - If Notion is not configured, explain dry-run privacy boundary.

## Backend Demo Path

Show API response:

```bash
curl -fsS http://127.0.0.1:8787/api/dashboard/metrics | jq .
```

Import OpenClaw local metadata twice and confirm deterministic IDs prevent duplicate growth:

```bash
curl -fsS -X POST http://127.0.0.1:8787/api/integrations/openclaw/import -d '{}' | jq '.created,.updated'
curl -fsS -X POST http://127.0.0.1:8787/api/integrations/openclaw/import -d '{}' | jq '.created,.updated'
```

Probe Hermes without blocking the demo:

```bash
curl -fsS -X POST http://127.0.0.1:8787/api/integrations/hermes/probe -d '{}' | jq .
```

Show OpenClaw run detail:

```bash
curl -fsS http://127.0.0.1:8787/api/runs | jq '.[] | select(.runtime_type=="openclaw") | {run_id,status,model_name,trace_id}' | head
```

Show database tables:

```bash
sqlite3 agentops_mis.db ".tables"
```

Show counts:

```bash
sqlite3 agentops_mis.db "SELECT 'agents', count(*) FROM agents UNION ALL SELECT 'runs', count(*) FROM runs UNION ALL SELECT 'tool_calls', count(*) FROM tool_calls UNION ALL SELECT 'audit_logs', count(*) FROM audit_logs;"
```

Verify OpenClaw summary safety:

```bash
sqlite3 agentops_mis.db "SELECT max(length(output_summary)) FROM runs WHERE run_id LIKE 'run_oc_cron_%';"
```

Show reproducible OpenClaw experiment:

```bash
python3 scripts/openclaw_v1_experiment.py --skip-live-probe
```

## Fallbacks

If the fixed OpenClaw run id is missing:

- Go to `/runs`.
- Pick the latest run with `runtime_type=openclaw`.
- If no OpenClaw run exists, run:

```bash
python3 scripts/openclaw_v1_experiment.py
```

If Notion token is not configured:

- Use `/integrations` preview.
- Explain that dry-run mode is intentional and privacy-safe.

If Notion token is configured:

- Dry-run remains the API default.
- Real export requires `dry_run:false` and `confirm_export:true`.

If browser demo fails:

- Use API responses and SQLite counts.
- Open docs:
  - `docs/PRESENTATION_BRIEF.md`
  - `docs/ARCHITECTURE.md`
  - `docs/CHINESE_PRESENTATION_SCRIPT.md`
