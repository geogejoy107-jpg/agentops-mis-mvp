# Live Demo Runbook

v1.2.1 keeps safe reproducible demo mode as the default. This runbook is only for local video recording when you want to show one explicit confirmed Agnesfallback real probe entering the MIS ledger.

Do not commit local DB changes, tokens, credentials, full prompts, raw responses or transcripts.

## A. CLI Live Probe Path

1. Set live-mode environment variables before starting the server:

```bash
export HERMES_RUNTIME_MODE=cli_probe
export HERMES_ALLOW_REAL_RUN=true
export HERMES_REQUIRE_CONFIRM_RUN=true
export AGNESFALLBACK_BIN="$HOME/.local/bin/agnesfallback"
```

2. Start AgentOps MIS:

```bash
python3 server.py
```

3. Record the before counts in another terminal:

```bash
python3 scripts/live_demo_verify.py before
```

4. First show the safe dry-run plan:

```bash
curl -s -X POST http://127.0.0.1:8787/api/integrations/hermes/cli-probe \
  -H "Content-Type: application/json" \
  -d '{}' | jq .
```

5. Then run the explicit confirmed probe:

```bash
curl -s -X POST http://127.0.0.1:8787/api/integrations/hermes/cli-probe \
  -H "Content-Type: application/json" \
  -d '{"confirm_run": true}' | jq .
```

6. Record the after counts:

```bash
python3 scripts/live_demo_verify.py after
```

Expected result:

- Response shows `dry_run:false`.
- `ok` is `true` when Agnesfallback returns the fixed expected text.
- `output_summary` says the CLI returned `AGNESFALLBACK_OK`, or clearly states the probe result.
- `runs` increases.
- `runtime_events` increases.
- `evaluations` increases.
- `audit_logs` increases.

Open these pages for the recording:

- `/runs`: latest Agnesfallback CLI run.
- `/evaluations`: latest rule evaluation for that run.
- `/audit`: latest Agnesfallback runtime audit records.

## B. OpenAI-Compatible Gateway Live Probe Path

1. Manually start the Agnesfallback gateway on `127.0.0.1:8643`.

Do not make AgentOps MIS auto-start the gateway. For recording, keep the gateway in a separate terminal so it is obvious this is a local runtime dependency.

2. Set live-mode environment variables before starting the server:

```bash
export HERMES_RUNTIME_MODE=openai_compatible
export HERMES_ALLOW_REAL_RUN=true
export HERMES_REQUIRE_CONFIRM_RUN=true
export AGNESFALLBACK_GATEWAY_URL="http://127.0.0.1:8643"
```

3. Start AgentOps MIS:

```bash
python3 server.py
```

4. Record the before counts:

```bash
python3 scripts/live_demo_verify.py before
```

5. Show model discovery:

```bash
curl -s http://127.0.0.1:8787/api/integrations/hermes/models | jq .
```

6. Run the explicit confirmed OpenAI-compatible probe:

```bash
curl -s -X POST http://127.0.0.1:8787/api/integrations/hermes/chat-completion-probe \
  -H "Content-Type: application/json" \
  -d '{"confirm_run": true}' | jq .
```

7. Record the after counts:

```bash
python3 scripts/live_demo_verify.py after
```

Expected result:

- Response shows `dry_run:false`.
- `ok` is `true` when the gateway returns the fixed expected text.
- `output_summary` says the API returned `HERMES_AGNES_API_OK`, or clearly states the probe result.
- `runs` increases.
- `runtime_events` increases.
- `evaluations` increases.
- `audit_logs` increases.

## Safety Wrap-Up

After recording:

```bash
unset HERMES_ALLOW_REAL_RUN
unset HERMES_RUNTIME_MODE
unset AGNESFALLBACK_GATEWAY_URL
```

Then:

- Stop `python3 server.py`.
- Stop the temporary Agnesfallback gateway if you used the gateway path.
- Confirm `.env.example` still keeps `HERMES_ALLOW_REAL_RUN=false`.
- Confirm no token or local DB is staged:

```bash
git status --short --ignored
```

`agentops_mis.db` may appear as ignored local runtime state. It must not be committed.
