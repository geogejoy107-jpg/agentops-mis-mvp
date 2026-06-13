# Reproducible Demo

## Fresh Local Demo

```bash
python3 server.py --reset
python3 scripts/demo_seed_openclaw_redacted.py --reset
python3 scripts/demo_acceptance.py --start-server
python3 server.py
```

Then open `http://127.0.0.1:8787/dashboard`.

## Expected Synthetic Counts

The redacted seed contributes:

- 10 agents
- 50 tasks
- 500 runs
- 800 tool calls
- 200 memory candidates
- 2000 audit logs

Your local DB may contain additional real local OpenClaw imports or previous dry-run events. The seed IDs all use `*_demo_*` prefixes so they can be reset deterministically.

## Privacy Boundary

The reproducible demo seed is synthetic. It does not read:

- `~/.openclaw`
- credentials
- private chats
- transcripts
- real prompts
- personal files

## Acceptance

`scripts/demo_acceptance.py` passes when:

- API server is reachable.
- Dashboard metrics return runtime health and agent performance.
- OpenClaw, Hermes and Notion status endpoints respond.
- Notion dry-run works without external writes.
- Agnesfallback CLI probe returns dry-run plan by default.
- Runtime/base/template/migration endpoints respond.
- Local DB contains audit/runtime/template/base records.
