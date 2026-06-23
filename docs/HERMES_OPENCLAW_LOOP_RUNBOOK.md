# Hermes/OpenClaw Loop Runbook

This runbook describes the local supervised loop harness for coordinating Hermes and OpenClaw under Codex supervision.

## Purpose

The loop harness lets Codex ask Hermes and OpenClaw for alternating proposals, critiques, and next actions while keeping project files clean. By default it writes only gitignored local runtime files. With `--mis-ledger`, it also records the collaboration as first-class AgentOps MIS evidence.

## Contract

- Codex is the supervisor and decides whether to continue, stop, or implement.
- Hermes and OpenClaw are reviewers or proposal agents by default.
- Agents must not edit files through this loop.
- The loop stores only redacted summaries, prompt hashes, statuses, and timestamps.
- Every agent output receives a rule-based evaluation score.
- Every loop writes audit JSONL events for start, agent output, next-action artifact, and completion.
- Every loop writes a next-action artifact for Codex review.
- `--mis-ledger` records parent/child tasks, parent/child runs, agent plans, tool calls, evaluations, artifacts, audit logs, and plan evidence manifests through Agent Gateway.
- Parent and child lanes each follow the Agent Work Method Block: READ, PLAN, RETRIEVE, COMPARE, EXECUTE, VERIFY, RECORD.
- A loop lane is not considered delivery-ready until its `plan_evidence_manifest` verifies against tool, evaluation, artifact, and audit evidence.
- `--resume` can reuse existing JSONL outputs for a fixed `--loop-id` and continue missing iterations.
- `--max-agent-attempts` and `--retry-delay-sec` bound retry behavior; summaries store retry hashes, not raw prompts or raw responses.
- Raw prompts, raw responses, credentials, and private transcripts are omitted.
- Logs live under `.agentops_runtime/loops/`, which is gitignored.
- Live runtime calls require `--confirm-live`.
- Live runtime calls and MIS ledger writeback are separate switches: dry-run can still be recorded to MIS for demo/proof without calling Hermes/OpenClaw.

## Commands

Quick loop-control brief for a live local adapter:

```bash
agentops worker preflight --adapter hermes
agentops operator live-acceptance --limit 8
agentops operator loop-launch-packet --brief --adapter hermes --limit 8

agentops worker preflight --adapter openclaw
agentops operator live-acceptance --limit 8
agentops operator loop-launch-packet --brief --adapter openclaw --limit 8
```

The brief is the preferred handoff payload when Codex wants Hermes or OpenClaw
to continue a supervised loop without reading the full launch packet. It keeps
only the adapter preflight command, current next/verify/receipt commands,
compact execution-chain state, bounded-runner policy id, confirmation and
prepared-action guidance, an explicit `agentops workflow run-task --adapter ...
--confirm-run` live command template, readback commands for task/run/manifest
evidence, a compact `local_run_path` with boot/readiness/worker/service-control
preview/dispatch/ledger/live-acceptance commands, and read-only/token-omission
proof. `workflow run-task` readback now
also returns compact `agent_plan` and `plan_evidence` proof with verified flags
and evidence counts, so the next agent can distinguish a closed loop lane from
a model-only summary. The agent should copy commands locally; the server never
executes shell from the brief.

Before starting or advancing a local Hermes/OpenClaw lane, read the structured
adapter setup guide:

```bash
agentops worker readiness
```

Each adapter row now includes `remediation.primary_next_action`, missing local
checks, and ordered copy-only commands for inspect, preflight, runtime doctor,
confirmed worker start, confirmed live task template, and final ledger proof via
`agentops operator live-product-readiness`. The readiness endpoint does not run
those commands; it only tells Hermes/OpenClaw/Codex exactly which command to
copy next and which steps still require `--confirm-run`.

For real customer-worker acceptance, prefer the read-only freshness gate before
starting another live lane:

```bash
agentops operator live-acceptance --limit 8
python3 scripts/customer_worker_real_runtime_acceptance.py \
  --confirm-live \
  --adapter hermes \
  --request-timeout 720 \
  --hermes-timeout 600 \
  --hermes-max-tokens 512
```

`live-acceptance` exposes `active_attempt` for in-flight
`agt_customer_worker_*` runs so Codex/OpenClaw/Hermes do not accidentally launch
duplicate local work. Active attempts are scheduling evidence only; the adapter
is not `fresh` until the run completes and the plan/tool/evaluation/runtime/
audit/artifact/memory/approval evidence chain verifies.

Bounded one-step advance:

```bash
agentops operator loop-control --limit 8
agentops operator advance-loop --fast-control --limit 8
agentops operator advance-loop --fast-control --limit 8 --confirm-advance
agentops operator action-receipts --limit 20
agentops operator loop-audit --limit 20
```

Bounded local loop-driver for Hermes/OpenClaw:

```bash
agentops operator loop-driver --adapter hermes --max-steps 3 --limit 8
agentops operator loop-driver --adapter hermes --max-steps 3 --limit 8 --confirm-loop

agentops operator loop-driver --adapter openclaw --max-steps 3 --limit 8
agentops operator loop-driver --adapter openclaw --max-steps 3 --limit 8 --confirm-loop
```

`loop-driver` is the local copy-only wrapper for repeated loop progress. Without
`--confirm-loop` it only returns the compact launch brief and proposed safe
commands plus an `adapter_readiness` gate derived from `agentops worker
readiness`, including the exact `agentops worker preflight --adapter ...`
command, adapter trust/readiness state, checks, and live-dispatch blockers.
With `--confirm-loop`, it re-reads adapter readiness and the launch brief before
each step, calls `advance-loop --fast-control --confirm-advance`, records the
control readback and action receipt evidence, and stops at the bounded
`--max-steps` cap. Readiness gates do not grant live runtime execution,
workflow dispatch, approvals, or server shell execution; Hermes/OpenClaw still
copy and run explicit local commands, and live worker dispatch still requires
`--confirm-run` plus any prepared-action approval required by the task.

Workflow-job recovery from the shared Action Queue:

```bash
agentops operator action-plan --limit 20
agentops workflow stuck-jobs --threshold-sec 900 --limit 25
agentops workflow recover-job --job-id <job_id> --mode mark-failed
agentops workflow recover-job --job-id <job_id> --mode mark-failed \
  --reason "<reason>" \
  --confirm-recover \
  --record-receipt
agentops workflow job-status --job-id <job_id>
```

`operator action-plan` projects stuck or retryable workflow jobs into the
`workflow_job_recovery` lane with `command`, `verify_command`,
`receipt_record_command`, and `receipt_verify_record_command`. Hermes,
OpenClaw, and Codex should copy those generated commands instead of inventing
their own recovery syntax. The action-plan and stuck-job reads are read-only;
`agentops workflow recover-job` is the safer wrapper for the explicit action:
without `--confirm-recover` it previews the exact command, and with
`--record-receipt` it records the RECORD step after a confirmed recovery.
Live Hermes/OpenClaw retry commands still require explicit `--confirm-run`.

Dry-run two rounds:

```bash
python3 scripts/hermes_openclaw_loop.py \
  --topic "Design the next supervised loop guardrail." \
  --rounds 2
```

Dry-run with MIS ledger proof:

```bash
python3 scripts/hermes_openclaw_loop.py \
  --topic "Review the next AgentOps MIS worker-loop improvement." \
  --rounds 1 \
  --mis-ledger
```

Run through the MIS workflow API/CLI:

```bash
agentops workflow hermes-openclaw-loop \
  --topic "Review the next AgentOps MIS worker-loop improvement." \
  --rounds 1

agentops workflow hermes-openclaw-loop \
  --readback \
  --loop-id loop_...
```

The CLI maps to `POST /api/workflows/hermes-openclaw-loop` and
`GET /api/workflows/hermes-openclaw-loop?loop_id=...`.

Expected MIS writeback:

- one parent task/run owned by the Codex loop supervisor
- one child task/run per Hermes/OpenClaw output
- one `agent_plan` for the parent and one per child lane
- one tool call, one rule evaluation, and one loop output artifact per child run
- one `plan_evidence_manifest` per child lane and one parent manifest
- audit evidence for output recording and loop completion
- one final `loop_next_action` artifact linked to the parent run

Resume an interrupted dry-run loop:

```bash
python3 scripts/hermes_openclaw_loop.py \
  --topic "Review the next AgentOps MIS worker-loop improvement." \
  --rounds 2 \
  --loop-id loop_demo_review \
  --resume \
  --mis-ledger
```

Smoke-test a blocked lane without calling live runtimes:

```bash
python3 scripts/hermes_openclaw_loop.py \
  --topic "Verify blocked loop evidence is visible." \
  --rounds 1 \
  --simulate-failure-agent hermes \
  --mis-ledger
```

Live Hermes only:

```bash
python3 scripts/hermes_openclaw_loop.py \
  --topic "Review the loop harness contract." \
  --mode live-hermes \
  --confirm-live \
  --rounds 1
```

Live OpenClaw only:

```bash
python3 scripts/hermes_openclaw_loop.py \
  --topic "Review the loop harness contract." \
  --mode live-openclaw \
  --confirm-live \
  --rounds 1
```

Smoke test:

```bash
python3 scripts/hermes_openclaw_loop_smoke.py
```

The smoke test starts an isolated temporary SQLite-backed server, runs `--mis-ledger`, and verifies `tasks`, `runs`, `agent_plans`, `tool_calls`, `evaluations`, `audit_logs`, `artifacts`, `plan_evidence_manifests`, resume behavior, and blocked-lane visibility without touching the default `agentops_mis.db`.

Closed loop-audit RECORD smoke:

```bash
python3 scripts/operator_loop_audit_closed_loop_smoke.py
```

This smoke starts an isolated server, runs the Hermes/OpenClaw workflow lane,
checks that `agentops operator loop-audit --loop-id ...` keeps `RECORD` at
attention until a `loop_record` memory candidate is approved, then verifies the
scoped loop reaches 7/7 passing gates.

## Stop Conditions

- Any live mode without explicit confirmation.
- Any secret-like output in summaries or logs.
- Any request that asks Hermes/OpenClaw to edit files directly.
- More than eight rounds.
- Runtime timeout, unavailable gateway, or repeated failed summaries.
- MIS ledger mode cannot reach `AGENTOPS_BASE_URL` / `--base-url`.

## Cleanliness Check

Before and after loop work:

```bash
git status --short
git diff --check
find . -maxdepth 3 \( -name '__pycache__' -o -name '*.pyc' \) -print
```

## Runtime Files

For loop id `loop_...`, the harness writes:

- `.agentops_runtime/loops/loop_....jsonl`
- `.agentops_runtime/loops/loop_....audit.jsonl`
- `.agentops_runtime/loops/loop_....next_action.json`

All three are runtime artifacts and must remain untracked.
