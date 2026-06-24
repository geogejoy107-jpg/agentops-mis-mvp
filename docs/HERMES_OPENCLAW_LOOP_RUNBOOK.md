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
agentops operator agent-loop-handoff --limit 8
agentops operator loop-supervision --limit 8

agentops operator start-check --adapter hermes --limit 8
agentops worker preflight --adapter hermes
agentops operator live-acceptance --limit 8
agentops operator loop-launch-packet --brief --adapter hermes --limit 8

agentops operator start-check --adapter openclaw --limit 8
agentops worker preflight --adapter openclaw
agentops operator live-acceptance --limit 8
agentops operator loop-launch-packet --brief --adapter openclaw --limit 8
```

`agent-loop-handoff` is the preferred first machine read when Hermes,
OpenClaw, and Codex need the same loop state. It composes current-code proof,
fresh live ledger proof, per-adapter start-check decisions, compact launch
briefs, Method Block `phase_commands`, method gate ids, and Codex supervisor
commands into one read-only matrix. It may return `attention` when review or
memory pressure remains, but `ready_for_handoff:true` means the consumer has the
copyable commands and safety proofs needed to continue without guessing or
bypassing Agent Plan, retrieval, base comparison, verification, receipt, or
memory-review gates. It never executes shell on the server, starts live
runtimes, mutates ledgers, approves reviews, or exposes raw prompts/responses/
tokens.

`loop-supervision` is the preferred second machine read before copying any
bounded `loop-driver --confirm-loop` command. It reuses the handoff/start-check
state and returns per-adapter `can_preview_loop`, `can_confirm_bounded_loop`,
`should_record_before_execute`, review/memory pressure, gate status, layered
safe read/preview/confirm-required commands, and no-server-shell proof. It is
read-only: it does not run loop-driver, workers, Hermes/OpenClaw, approvals,
shell commands, or ledger writes.

Confirmed Hermes/OpenClaw customer-worker and installable worker paths now read
the same gate before live runtime invocation. A blocked supervision gate stops
before the adapter call and records compact audit/evidence metadata; RECORD
pressure remains visible through `should_record_before_execute` and
`recommended_next`.

Agent Gateway `runs/start` is also supervised for governed live runtimes. When
an agent starts a `hermes`, `openclaw`, or `codex` run, MIS reads
`loop-supervision` after the Agent Plan gate and before inserting the run. If
bounded confirm or no-server-shell safety is not proven, run-start returns
`run_start_loop_supervision_blocked` with `live_execution_performed:false`; if
allowed, the response includes `loop_supervision_gate.supervision_hash` so the
run's first evidence packet shows which Method Block supervision state was
crossed.

The local `/workspace/agents` console mirrors this boundary: the Loop
Supervision panel shows the read-only `run_start_admission` projection before a
run exists, and the latest worker dispatch result shows the actual
`loop_supervision_gate` consumed or blocked by the worker/Gateway path. Display
is compact by design: status, short hash, recommended command, no-run-on-block,
no-server-shell, no-live-execution, and token omission only.

`start-check` is the preferred first read for a local loop. The CLI reads
`GET /api/operator/start-check`, so Hermes/OpenClaw/Codex can use either the
CLI or the local MIS HTTP API. It merges local readiness, worker readiness,
runtime doctor, live product proof, compact launch brief, `local_run_path`, and
service-control preview into one copy-only packet. Its `acceptance_packet`
field is the machine-readable loop intake decision: `can_preview_loop`,
`can_confirm_bounded_loop`, `live_dispatch_requires_confirm_run`, review
pressure, required ledgers, receipt/readback requirements, and the exact
copyable commands for start-check, runtime doctor, loop-driver preview/confirm,
execution-mode confirmation, live-product readiness, and receipt readback. It
may return `attention` while binaries, credentials, reviews, or live proof are
missing, but it still gives the next safe command without running shell on the
server or mutating ledgers.

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
agentops operator loop-supervision --adapter hermes --adapter openclaw --limit 8 --work-packet
curl 'http://127.0.0.1:8787/api/operator/loop-supervision?adapter=hermes&adapter=openclaw&limit=8&work_packet=1'

agentops operator loop-bootstrap --adapter hermes --limit 8
agentops operator loop-bootstrap --adapter hermes --limit 8 --run-service-check
agentops operator loop-driver --adapter hermes --max-steps 3 --limit 8
agentops operator loop-driver --adapter hermes --max-steps 3 --limit 8 --confirm-loop --auto-service-closure

agentops operator loop-bootstrap --adapter openclaw --limit 8
agentops operator loop-bootstrap --adapter openclaw --limit 8 --run-service-check
agentops operator loop-driver --adapter openclaw --max-steps 3 --limit 8
agentops operator loop-driver --adapter openclaw --max-steps 3 --limit 8 --confirm-loop --auto-service-closure
```

Start machine callers from the compact work-packet bundle. The CLI
`--work-packet` flag and the HTTP `work_packet=1` query return the same
`agent_work_packet_bundle_v1` shape with `agent_work_packet_v1` entries for
Hermes/OpenClaw, packet hashes, phase commands, primary next actions, service
closure/readback receipts, and no raw prompt/response/token content. HTTP
callers should use that compact bundle instead of scraping the larger
supervision payload.

`loop-bootstrap` is the first local deployment packet to hand to Hermes or
OpenClaw. It is read-only by default and returns the ordered current-code,
service-install preview/confirm, service-check, service-closure record,
service-activation confirm, and bounded loop-driver commands. With
`--run-service-check` it performs only the local read-only worker
`service-check` in the CLI process; it does not write receipts, load services,
execute server shell, or run a live adapter.

If Hermes/OpenClaw are pointed at an older local MIS process, the bootstrap
command fails closed as JSON instead of a bare 404. The blocked packet uses
`error_type=stale_server_or_missing_endpoint` and includes current-code,
restart, and retry commands so the agent can repair the local target before
continuing.
For large local ledgers, use `agentops operator loop-bootstrap --adapter
hermes|openclaw --fast` or `GET /api/operator/loop-bootstrap?fast=1` to get the
copy-only startup commands without waiting for heavy start-check or
loop-supervision. Fast bootstrap is not acceptance: it keeps bounded loop
confirmation blocked until current-code and deep supervision readback pass.
If a deep endpoint times out, the CLI returns
`error_type=local_mis_endpoint_timeout` with the same fast fallback packet plus a
longer-timeout retry command instead of a Python traceback.

The same packet is available inside the local MIS through
`GET /api/operator/loop-bootstrap?limit=8` and the AI Employees page. That API
surface is copy-only: it reads start-check plus loop-supervision, renders the
Hermes/OpenClaw startup sequence, and never runs service-check, service-control,
server shell, live adapters, or ledger writes.

`loop-driver` is the local copy-only wrapper for repeated loop progress. Without
`--confirm-loop` it returns a compact `acceptance_gate` from
`operator start-check`, an `agent_loop_packet` with the READ/PLAN/RETRIEVE/
COMPARE/PREFLIGHT/EXECUTE/VERIFY/RECORD command sequence, the compact launch brief,
proposed safe commands, a RECORD review snapshot, and an `adapter_readiness`
gate derived from
`agentops worker readiness`, including the exact `agentops worker preflight
--adapter ...` command, adapter trust/readiness state, checks, and
live-dispatch blockers. With `--confirm-loop`, it re-reads the start-check
acceptance gate before execution and before each step, then only calls
`advance-loop --fast-control --confirm-advance` when `can_confirm_bounded_loop`
is true and `server_executes_shell` is false. It records the control readback
and action receipt evidence, refreshes the review snapshot, returns initial and
final `agent_loop_packet` readbacks, and stops at the bounded `--max-steps`
cap. Acceptance/readiness/packet/review gates do not grant live runtime
execution, workflow dispatch, approvals, or server shell execution; Hermes/
OpenClaw still copy and run explicit local commands, and live worker dispatch
still requires `--confirm-run` plus any prepared-action approval required by the
task.

For machine callers, read `agent_loop_packet.method_gates` before copying an
execution command. The gates name the required Agent Work Method checkpoints:
`plan_agent_plan`, `retrieve_knowledge`, `compare_base_reference`,
`preflight_adapter`, `execute_bounded_loop`, `verify_loop`, and
`record_memory_candidate`. `phase_commands` maps each phase to the exact local
CLI command to copy.

The local MIS UI mirrors this packet in `/workspace/agents`: the loop-driver
panel reads Hermes and OpenClaw start-check packets, shows each adapter's
current phase, `ready_to_confirm_loop` state, `server_executes_shell` proof, and
copyable phase commands. Use that panel as the human supervision surface while
Hermes/OpenClaw run the local CLI loop.

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
