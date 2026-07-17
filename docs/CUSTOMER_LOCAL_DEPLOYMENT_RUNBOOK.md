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
agentops audit retention-policy
agentops audit retention-controls
agentops worker status
agentops security production-readiness
```

`agentops audit retention-policy` is a read-only preview. It reports retention
days, cutoff, and eligible audit-row counts, but cleanup/delete parameters fail
closed and `rows_deleted` must remain `0`.
`agentops audit retention-controls` is also read-only. It reports whether
cleanup approval and legal-hold checks are required and confirms cleanup
endpoints remain closed. When no legal-hold registry is configured, it reports
that it cannot assert no holds instead of claiming zero holds.
To preview a configured metadata-only registry fixture:

```bash
AGENTOPS_RETENTION_CONTROLS_PATH=config/retention-controls.example.json agentops audit retention-controls
```

This fixture is readiness evidence, not a legal system of record.

## Security Baseline

For local demos, `local_dev_no_token` is allowed only while the service remains
bound to `127.0.0.1`.

Before shared or hosted deployment:

```bash
export AGENTOPS_API_KEY="<local gateway key>"
export AGENTOPS_WORKSPACE_ADMIN_KEYS_JSON='{"local-demo":"<workspace admin key>"}'
export AGENTOPS_DEPLOYMENT_MODE=production
agentops security production-readiness
```

Rules:

- Never commit `.env`, `agentops_mis.db`, `.agentops_runtime`, service files
  with real tokens, or worker logs.
- Shared/production deployments require `AGENTOPS_WORKSPACE_ADMIN_KEYS_JSON` as
  a JSON object mapping each workspace id to a distinct admin key of at least 24
  characters. Keys must be strings and cannot be reused across workspaces; a key
  cannot administer another workspace, and invalid configuration fails closed.
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

## SQLite Backup And Restore

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

## Postgres BYOC Backup And Restore

Postgres deployments use `postgres_backup_restore_v1` with a required
`postgres_backup_manifest_v1` sidecar. Prefer environment variables so database
credentials do not enter shell history:

```bash
export AGENTOPS_POSTGRES_DSN="<customer-managed-source-dsn>"
python3 scripts/agentops_postgres_backup.py create \
  --backup-dir .agentops_runtime/postgres_backups

python3 scripts/agentops_postgres_backup.py verify \
  --backup .agentops_runtime/postgres_backups/agentops-postgres-YYYYMMDDTHHMMSSZ-ID.dump
```

Restore requires explicit write confirmation and a target-state acknowledgement:

```bash
export AGENTOPS_POSTGRES_TARGET_DSN="<customer-managed-empty-target-dsn>"
python3 scripts/agentops_postgres_backup.py restore \
  --backup .agentops_runtime/postgres_backups/agentops-postgres-YYYYMMDDTHHMMSSZ-ID.dump \
  --confirm-restore \
  --target-empty-confirmed
```

An overwrite additionally requires `--overwrite`; the utility first creates a
guarded Postgres pre-restore archive. The manifest, archive hash, and
`pg_restore --list` table of contents must verify before restore. Output omits
DSNs, credential values, raw rows, prompts, responses, transcripts, and tokens.

Installed utility and smoke files prove availability only. Gate 5 recovery
acceptance requires this Docker-backed command to pass with `skipped=false`
and be recorded against the current commit:

```bash
python3 scripts/agentops_postgres_backup_smoke.py
```

Packaged deployments without a `.git` directory must set
`AGENTOPS_BUILD_SHA` to the immutable 40-character commit SHA used to build the
image; stale or missing build identity keeps Postgres recovery blocked.

`--skip-if-unavailable` is diagnostic only while Docker is unavailable. Its
`skipped=true` result must never be recorded as BYOC handoff evidence.

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
python3 scripts/audit_retention_policy_smoke.py --isolated-fixture
python3 scripts/audit_retention_controls_smoke.py --configured-fixture
python3 scripts/deployment_readiness_smoke.py --configured-retention-fixture --configured-enterprise-fixture
python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture
python3 scripts/agentops_local_backup_smoke.py
python3 scripts/agentops_postgres_backup_smoke.py
python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture
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
- Postgres recovery acceptance reports `postgres_backup_restore_v1`,
  `postgres_backup_manifest_v1`, matching source/restored fixture counts, and
  `skipped=false`; installed files alone do not satisfy this evidence.
- BYOC deployment smoke verifies restore confirmation, overwrite safety copy,
  signed audit export, tamper detection, and the Postgres runtime write gate in
  isolated temp stores only.
- Handoff Postgres readiness shows `storage.runtime_write_gate=active`,
  `experimental_write_http`, OpenClaw/Hermes/row-gated approval routes,
  exact-resume proof, non-fixed write blocking, no SQLite fallback, and
  unchanged ledger counts.
- UI `/workspace/agents` shows readiness, customer dispatch, fleet hygiene,
  daemon restart, enrollment policy, and remote agent controls.
