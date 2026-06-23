# Customer Local Deployment Runbook

This is the product-facing v1.5 runbook for running AgentOps MIS as a local
customer control plane. It keeps the same boundary as the demo build: local
first, explicit live execution, scoped remote agent enrollment, and no Dify or
Notion live sync.

## Deployment Shape

- Backend: Python + SQLite, bound to `127.0.0.1:8787` by default.
- Frontend: Vite UI at `127.0.0.1:19001` for the beta workspace/admin
  experience.
- Agent execution: workers use Agent Gateway CLI/API, not browser clicks.
- Local ledger: `agentops_mis.db` unless `AGENTOPS_DB_PATH` points elsewhere.
- Runtime adapters: `mock`, `hermes`, and `openclaw`; Hermes/OpenClaw live runs
  require explicit confirmation.

Do not expose the local backend beyond loopback until authenticated production
mode is configured.

## First Start

```bash
cd /path/to/agentops-mis-mvp
python3 -m pip install .
python3 scripts/run_local_stack.py --install-ui
```

Open:

```text
http://127.0.0.1:19001/workspace/agents
http://127.0.0.1:8787/dashboard
```

Run read-only readiness:

```bash
agentops doctor
agentops status
agentops local readiness
agentops worker status
agentops security production-readiness
```

`agentops local readiness` also returns a `local_run_path`: a copy-only sequence
for booting MIS, selecting a worker adapter, starting the worker, dispatching a
customer task, and verifying ledger evidence. These are operator commands; the
server reports them but does not execute shell commands.

`agentops doctor` is fail-closed for unsafe shared/production targets: it exits
with code `2` when `AGENTOPS_DEPLOYMENT_MODE=production|shared|hosted` or the
target is non-loopback and no Gateway token is configured. It still prints
redacted JSON so the operator can see the missing setup step.

## Security Baseline

For local demos, `local_dev_no_token` is allowed only while the service remains
bound to `127.0.0.1`.

Before shared or hosted deployment:

```bash
export AGENTOPS_API_KEY="<local gateway key>"
export AGENTOPS_ADMIN_KEY="<admin enrollment key>"
export AGENTOPS_DEPLOYMENT_MODE=production
agentops doctor
agentops security production-readiness
```

Non-loopback binding is fail-closed. To bind beyond loopback for a controlled
single-customer deployment, set all three controls before starting the server:

```bash
export AGENTOPS_ALLOW_NON_LOOPBACK=true
export AGENTOPS_API_KEY="<local gateway key>"
export AGENTOPS_ADMIN_KEY="<admin enrollment key>"
python3 server.py --host 0.0.0.0 --port 8787
```

Without the explicit opt-in and both keys, `server.py` exits before binding.
Loopback local demos remain unchanged.

Rules:

- Never commit `.env`, `agentops_mis.db`, `.agentops_runtime`, service files
  with real tokens, or worker logs.
- Enrollment tokens are shown once; MIS stores hashes only.
- Use `agentops enrollment policy-preview` before issuing a token.
- Prefer approval-gated enrollment for Hermes/OpenClaw or worker write scopes.
- Use short-lived sessions for long-running workers.

## Local Worker Operations

```bash
agentops worker preflight --adapter mock
agentops worker start --adapter mock --poll-interval 5 --max-tasks 0
agentops worker status
agentops worker logs --adapter mock
agentops worker restart --adapter mock
agentops worker stop --adapter mock
```

Hermes/OpenClaw require explicit live confirmation:

```bash
agentops worker preflight --adapter openclaw
agentops worker start --adapter openclaw --confirm-run --poll-interval 5 --max-tasks 0
agentops worker restart --adapter openclaw --confirm-run
agentops worker stop --adapter openclaw
```

Recovery:

```bash
agentops worker stuck
agentops worker hygiene
agentops worker hygiene --apply --confirm-cleanup
```

## Remote Agent Enrollment

Preview scope policy first:

```bash
agentops enrollment policy-preview \
  --runtime mock \
  --scopes agents:heartbeat,tasks:read,audit:write
```

Create a low-risk local token or request approval:

```bash
agentops enrollment create \
  --agent-id agt_customer_worker \
  --name "Customer Worker" \
  --runtime mock \
  --scopes agents:heartbeat,tasks:read,audit:write
```

```bash
agentops enrollment request \
  --agent-id agt_customer_openclaw \
  --name "Customer OpenClaw Worker" \
  --runtime openclaw
```

On the remote machine:

```bash
python3 -m pip install .
export AGENTOPS_BASE_URL="http://<mis-host>:8787"
export AGENTOPS_WORKSPACE_ID="local-demo"
export AGENTOPS_AGENT_ID="agt_customer_worker"
export AGENTOPS_API_KEY="<paste one-time token here>"
agentops doctor
agentops agent heartbeat --status idle --summary "remote worker ready"
agentops-worker --once --adapter mock --use-session --session-ttl-sec 900
```

## Backup And Restore

Create a local SQLite backup:

```bash
python3 scripts/agentops_local_backup.py create
```

Verify the latest backup:

```bash
python3 scripts/agentops_local_backup.py verify
```

Restore requires explicit confirmation and refuses to overwrite by default:

```bash
python3 scripts/agentops_local_backup.py restore \
  --backup .agentops_runtime/backups/agentops-mis-YYYYMMDDTHHMMSSZ.sqlite \
  --target /safe/path/agentops_mis_restored.db \
  --confirm-restore
```

If overwriting a target, pass `--overwrite`; the tool creates a
`.pre-restore-*` safety copy first.

The backup utility prints counts, hashes, and integrity status only. It does not
print table rows, prompts, raw responses, or token material.

## Acceptance Before Handoff

```bash
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
python3 scripts/agentops_local_backup_smoke.py
python3 scripts/enrollment_policy_preview_smoke.py
python3 scripts/agentops_worker_restart_smoke.py
python3 scripts/v1_5_demo_readiness_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/v1_5_local_product_acceptance.py --base-url http://127.0.0.1:8787
cd ui/start-building-app && npm run build
```

Expected state:

- `demo_ready=true`.
- Local product acceptance passes without live execution.
- Backup smoke creates and restores an isolated temp DB only.
- UI `/workspace/agents` shows readiness, customer dispatch, fleet hygiene,
  daemon restart, enrollment policy, and remote agent controls.
