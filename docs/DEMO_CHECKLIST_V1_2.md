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

## Live Recording Checklist

- Confirm no token is written into the repo.
- Confirm `.env.example` still says `HERMES_ALLOW_REAL_RUN=false`.
- Confirm the current shell explicitly exports `HERMES_ALLOW_REAL_RUN=true`.
- Confirm `HERMES_REQUIRE_CONFIRM_RUN=true`.
- Run `python3 scripts/live_demo_verify.py before`.
- Execute the dry-run probe first:

```bash
curl -s -X POST http://127.0.0.1:8787/api/integrations/hermes/cli-probe \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
```

- Execute the confirmed real probe:

```bash
curl -s -X POST http://127.0.0.1:8787/api/integrations/hermes/cli-probe \
  -H "Content-Type: application/json" \
  -d '{"confirm_run": true}' | jq .
```

- Run `python3 scripts/live_demo_verify.py after`.
- Open `/runs` and find the latest Agnesfallback run.
- Open `/audit` and find the latest runtime connector audit.
- Open `/evaluations` and show the rule evaluation for the probe.
- After recording, run `unset HERMES_ALLOW_REAL_RUN`.
- Stop the temporary Agnesfallback gateway if you used the OpenAI-compatible path.
- Run `git status --short --ignored` and confirm `agentops_mis.db` is ignored, not staged.

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
