# Local Task Harness Acceptance

## Purpose

This slice adds a small, repo-local harness entrypoint for running a customer or
dogfood task through the existing AgentOps MIS worker path.

It does not create a second execution engine. It wraps:

- `agentops workflow run-task`
- Agent Plan and plan-evidence readback
- task/run/tool/evaluation/artifact/audit ledger evidence
- Hermes/OpenClaw `--confirm-run` live gates

## Entrypoints

Plan-only, no server required:

```bash
python3 scripts/local_task_harness.py --adapter mock
python3 scripts/local_task_harness.py --adapter hermes
python3 scripts/local_task_harness.py --adapter openclaw --confirm-run
```

Execute against a running local MIS server:

```bash
python3 scripts/local_task_harness.py \
  --adapter mock \
  --execute \
  --title "Improve the AgentOps MIS customer workspace" \
  --description "Use the MIS worker loop to produce a safe task summary." \
  --acceptance "Return run, plan, tool, evaluation, artifact and audit evidence."
```

Confirmed real-runtime dogfood, only when the local runtime is available and
explicitly authorized:

```bash
python3 scripts/local_task_harness.py \
  --adapter openclaw \
  --execute \
  --confirm-run \
  --request-timeout 720 \
  --title "Use OpenClaw to review the local AgentOps MIS task harness" \
  --description "Run through Agent Gateway CLI/API and record safe evidence."
```

## Safety

- Default mode is plan-only.
- CI smoke does not start a server, read a database, mutate ledgers or run live
  Hermes/OpenClaw.
- Hermes/OpenClaw live execution requires `--execute --confirm-run`.
- Raw prompts, raw responses, credentials, private messages and full
  transcripts are not stored by this harness.
- Local SQLite DBs, `.env`, caches, `dist`, `node_modules` and generated runtime
  artifacts are not committed.

## Verification

Run:

```bash
python3 scripts/local_task_harness_smoke.py
python3 -m py_compile scripts/local_task_harness.py scripts/local_task_harness_smoke.py
python3 scripts/secret_scan_smoke.py
git diff --check
```

Isolated mock execute dogfood:

```text
db: /tmp/agentops_local_task_harness_test.db
base_url: http://127.0.0.1:58991
command: python3 scripts/local_task_harness.py --adapter mock --execute
task_id: tsk_eba57936ec0e
run_id: run_gw_f79dc3a5d3df
run_status: completed
live_execution_performed: false
secret_leaked: false
```

Server log evidence showed the wrapper used existing Agent Gateway surfaces:
register, task create/pull/claim, knowledge evidence packet, Agent Plan,
runs/start, runtime event, tool call, evaluation, artifact, memory proposal,
audit, heartbeat and plan-evidence manifest verification.

## Product Claim

This slice proves a reusable local task harness packet and command surface.
Plan-only and mock evidence are CI/offline fallback. Product-readiness claims
still require a fresh confirmed Hermes/OpenClaw run id plus ledger readback.
