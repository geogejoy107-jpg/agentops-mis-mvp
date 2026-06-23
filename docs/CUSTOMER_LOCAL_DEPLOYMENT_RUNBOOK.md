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
agentops deployment readiness
agentops worker status
agentops security production-readiness
```

## Security Baseline

For local demos, `local_dev_no_token` is allowed only while the service remains
bound to `127.0.0.1`.

Before shared or hosted deployment:

```bash
export AGENTOPS_API_KEY="<local gateway key>"
export AGENTOPS_ADMIN_KEY="<admin enrollment key>"
export AGENTOPS_DEPLOYMENT_MODE=production
agentops security production-readiness
```

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

## Signed Audit Export

Enterprise/BYOC audit export requires a customer-controlled signing key. Missing
key fails closed and does not write an export:

```bash
export AGENTOPS_AUDIT_EXPORT_KEY="<customer-controlled-signing-key>"
python3 scripts/agentops_signed_audit_export.py export \
  --output .agentops_runtime/audit_exports/agentops-audit.signed.json
```

Verify an export before handing it to a customer auditor:

```bash
python3 scripts/agentops_signed_audit_export.py verify \
  --export .agentops_runtime/audit_exports/agentops-audit.signed.json
```

The export signs a manifest plus hash-only audit rows. It omits raw
`metadata_json`, prompts, responses, token values, and the signing key. Tampering
with the row payload must fail verification.

## Acceptance Before Handoff

```bash
python3 -m py_compile server.py scripts/*.py agentops_mis_cli/*.py
python3 scripts/deployment_readiness_smoke.py
python3 scripts/agentops_local_backup_smoke.py
python3 scripts/byoc_deployment_acceptance_smoke.py
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
- BYOC deployment smoke verifies restore confirmation, overwrite safety copy,
  signed audit export, and tamper detection in an isolated temp DB only.
- UI `/workspace/agents` shows readiness, customer dispatch, fleet hygiene,
  daemon restart, enrollment policy, and remote agent controls.
