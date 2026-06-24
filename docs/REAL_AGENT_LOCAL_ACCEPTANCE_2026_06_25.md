# Real Agent Local Acceptance - 2026-06-25

This record captures a local, isolated, non-mock acceptance pass for the
AgentOps MIS worker loop. It is evidence for local dogfood/demo readiness, not
a hosted or production-security claim.

## Scope

- Branch/head tested: `main` at `da4224dbfbf585f069158bd99e4bef8c09f3b576`
- Server: `127.0.0.1:57951`
- Database: isolated temporary SQLite DB under `/tmp`
- Real adapters: `hermes`, `openclaw`
- Knowledge index: rebuilt locally before final acceptance
- Raw prompt, raw response, private transcript, credentials and tokens: omitted
- Repo DB/cache/generated artifacts: not committed

## Commands

```bash
AGENTOPS_DB_PATH=/tmp/agentops_real_agent_20260625025631.db python3 server.py --reset
AGENTOPS_DB_PATH=/tmp/agentops_real_agent_20260625025631.db \
  HERMES_ALLOW_REAL_RUN=true \
  HERMES_REQUIRE_CONFIRM_RUN=true \
  HERMES_RUNTIME_MODE=openai_compatible \
  AGNESFALLBACK_GATEWAY_URL=http://127.0.0.1:8642 \
  python3 server.py --host 127.0.0.1 --port 57951

AGENTOPS_BASE_URL=http://127.0.0.1:57951 \
  AGENTOPS_DB_PATH=/tmp/agentops_real_agent_20260625025631.db \
  ./scripts/agentops knowledge index --rebuild

AGENTOPS_BASE_URL=http://127.0.0.1:57951 \
  AGENTOPS_DB_PATH=/tmp/agentops_real_agent_20260625025631.db \
  ./scripts/agentops worker service-install --manager launchd \
  --adapter hermes --agent-id agt_worker_daemon_hermes \
  --confirm-run --confirm-install --overwrite

AGENTOPS_BASE_URL=http://127.0.0.1:57951 \
  AGENTOPS_DB_PATH=/tmp/agentops_real_agent_20260625025631.db \
  ./scripts/agentops worker service-install --manager launchd \
  --adapter openclaw --agent-id agt_worker_daemon_openclaw \
  --confirm-run --confirm-install --overwrite

AGENTOPS_BASE_URL=http://127.0.0.1:57951 \
  AGENTOPS_DB_PATH=/tmp/agentops_real_agent_20260625025631.db \
  ./scripts/agentops operator service-closure --adapter hermes \
  --fast --run-service-check --service-check-agent-id agt_worker_daemon_hermes \
  --confirm-record

AGENTOPS_BASE_URL=http://127.0.0.1:57951 \
  AGENTOPS_DB_PATH=/tmp/agentops_real_agent_20260625025631.db \
  ./scripts/agentops operator service-closure --adapter openclaw \
  --fast --run-service-check --service-check-agent-id agt_worker_daemon_openclaw \
  --confirm-record

python3 scripts/customer_worker_real_runtime_acceptance.py \
  --base-url http://127.0.0.1:57951 \
  --confirm-live \
  --adapter hermes \
  --adapter openclaw \
  --request-timeout 900 \
  --hermes-timeout 600 \
  --hermes-max-tokens 512

python3 scripts/v1_5_live_product_readiness_smoke.py \
  --base-url http://127.0.0.1:57951 \
  --require-adapter hermes \
  --require-adapter openclaw
```

## Result

`customer_worker_real_runtime_acceptance.py` returned:

```json
{
  "ok": true,
  "operation": "customer_worker_real_runtime_acceptance",
  "mock_supported": false,
  "adapters": ["hermes", "openclaw"],
  "failures": []
}
```

Hermes evidence:

- Task: `tsk_customer_worker_task_hermes_hermes_worker_20260625025851_20260624185851578291`
- Run: `run_gw_2a5561f0dfab`
- Artifact: `art_customer_worker_task_run_gw_2a5561f0dfab`
- Approval: `ap_customer_worker_delivery_run_gw_2a5561f0dfab`
- Agent Plan: `plan_5ec8a28e9beb7db4`
- Plan evidence manifest: `pem_35f98d39db850b7e`
- Evidence counts: tool calls `1`, evaluations `1`, runtime events `15`,
  audit logs `12`, artifacts `2`, memories `2`, approvals `1`,
  plan evidence manifests `1`

OpenClaw evidence:

- Task: `tsk_customer_worker_task_openclaw_openclaw_worker_20260625025919_20260624185919478527`
- Run: `run_gw_3b7f78202d0c`
- Artifact: `art_customer_worker_task_run_gw_3b7f78202d0c`
- Approval: `ap_customer_worker_delivery_run_gw_3b7f78202d0c`
- Agent Plan: `plan_bfa7dfb2415474b0`
- Plan evidence manifest: `pem_0b7b2a0b4b95506d`
- Evidence counts: tool calls `1`, evaluations `1`, runtime events `15`,
  audit logs `12`, artifacts `2`, memories `2`, approvals `1`,
  plan evidence manifests `1`

Read-only live readiness returned `product_readiness_proof: true` with both
required adapters fresh:

```json
{
  "ok": true,
  "operation": "v1_5_live_product_readiness",
  "live_acceptance_status": "ready",
  "product_readiness_proof": true,
  "required_adapters": ["hermes", "openclaw"]
}
```

## What Was Learned

The first confirmed live attempt did not execute Hermes/OpenClaw. AgentOps MIS
correctly blocked the run at `loop_supervision` because service-managed worker
receipt/readback evidence was missing. After installing local launchd worker
service files and recording adapter-specific service-check receipt/readback for
`agt_worker_daemon_hermes` and `agt_worker_daemon_openclaw`, the same acceptance
path completed with real adapter ledger evidence.

This proves the useful product behavior the demo needs:

- Browser/UI is not the agent runtime.
- The Agent Gateway and worker loop can dispatch real Hermes/OpenClaw work.
- Safety gates can block live execution before evidence is complete.
- Successful live work enters the MIS ledger as run, tool call, evaluation,
  runtime event, audit log, artifact, memory candidate, approval and plan
  evidence manifest rows.

## Remaining Gaps

- The final local readiness aggregate remained `attention` because Commander
  synthesis/delivery review was not run in this isolated DB.
- Customer delivery artifacts remain pending approval; approval was intentionally
  not auto-accepted.
- This record is local-loopback evidence only. It is not proof of hosted
  deployment, multi-tenant RBAC, billing, or external-customer operations.
