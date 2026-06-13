# Demo Checklist v1.2.1

## Prepare

```bash
python3 scripts/demo_seed_openclaw_redacted.py --reset
python3 scripts/demo_acceptance.py --start-server
python3 server.py
```

Open `http://127.0.0.1:8787/dashboard`.

## Must Show

- Dashboard runtime health.
- OpenClaw imported/demo agents and runs.
- Agent performance card.
- Run graph fields: parent run, delegation id, child/sibling runs.
- Memory review list.
- Approval queue or high-risk tool call statuses.
- Integrations page with OpenClaw, Hermes, Notion.
- Notion dry-run preview.
- Hermes unavailable displayed safely if local gateway is offline.

## API Backup

```bash
curl -fsS http://127.0.0.1:8787/api/dashboard/metrics | jq .
curl -fsS http://127.0.0.1:8787/api/runtime-connectors | jq .
curl -fsS http://127.0.0.1:8787/api/bases | jq .
curl -fsS http://127.0.0.1:8787/api/template-packages | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/migration/preview -d '{}' | jq .
```

## Do Not Show

- Real tokens.
- Private messages.
- Full transcripts.
- Personal local file contents.
- Raw prompts from real agent sessions.
