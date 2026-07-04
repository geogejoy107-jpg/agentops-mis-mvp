# OpenClaw Local Harness Dogfood - 2026-07-04

## Purpose

Record a fresh local dogfood attempt using the merged local task harness:

```bash
python3 scripts/local_task_harness.py \
  --adapter openclaw \
  --execute \
  --confirm-run \
  --base-url http://127.0.0.1:58992 \
  --workspace-id dogfood-openclaw
```

This is not a CI/mock claim. It uses an isolated local AgentOps MIS server and
the real local OpenClaw adapter path when gates allow it.

## Environment

- Source baseline: `origin/main` at `15cdb31`
- MIS server: isolated local server on `127.0.0.1:58992`
- SQLite DB: `/tmp/agentops_openclaw_harness_dogfood.db`
- OpenClaw binary: `/opt/homebrew/bin/openclaw`
- OpenClaw version: `OpenClaw 2026.5.4 (325df3e)`
- Default committed DB/env/cache/artifacts: not touched

## Preflight

OpenClaw worker preflight passed:

```text
binary_executable: true
binary_exists: true
version_ok: true
gateway_preflight.ok: true
token_omitted: true
live_execution_performed: false
```

## Gate Discovery

Initial confirmed OpenClaw harness attempts did not enter `runs/start`.
AgentOps MIS correctly blocked the run before live execution because the
service-managed OpenClaw loop needed local service receipt/readback evidence:

```text
reason: loop_supervision_blocked
status: record_first
run_start_attempted: false
live_execution_performed: false
recommended_next: record service-control receipt / control readback
```

Recorded safe service evidence in the isolated ledger:

```text
receipt_id: oar_5c4a811b4ff0
readback_id: ocr_d1494f9d7f0a
service_check_ok: true
service_file_exists: true
service_loaded: true
confirmed_os_mutation: false
live_execution_performed: false
```

## Final Attempt

After recording service receipt/readback evidence and running in the
`dogfood-openclaw` workspace, the confirmed harness run succeeded:

```text
task_id: tsk_628230eed2c3
run_id: run_gw_504b871b8f62
artifact_id: art_gw_9502be233d1eeda0
run_status: completed
task_status: completed
worker_exit_code: 0
worker_processed: 1
secret_leaked: false
live_execution_performed: true
```

Run readback:

```text
runtime_type: openclaw
tool_calls: 1
evaluations: 1
artifacts: 1
approvals: 0
token_omitted: true
```

Work delivery evidence graph:

```text
graph_hash: a2702abdceb1c4412ce7a58bfe9b01f2a9e5139425c6ed6e4c30887a7f5fa933
nodes: 13
edges: 10
tool_calls: 1
evaluations: 1
runtime_events: 8
audit_logs: 7
artifacts: 1
memories: 1
plan_evidence_manifests: 1
raw_prompt_omitted: true
raw_response_omitted: true
```

## Product Finding

The dogfood run exposed and fixed a wrapper correctness bug: the first
gate-blocked OpenClaw attempts returned a payload with `ok:false`, but
`scripts/local_task_harness.py` initially treated a zero CLI return code as
wrapper success. The wrapper now treats `payload.ok == false` as failure, and
`scripts/local_task_harness_smoke.py` guards that behavior.

## Safety

- Raw prompts omitted.
- Raw model responses omitted.
- Tokens omitted.
- Private transcripts omitted.
- Default local DB not touched.
- Generated runtime artifacts not committed.
