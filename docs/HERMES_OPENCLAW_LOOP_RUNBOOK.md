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
agentops operator loop-launch-packet --brief --adapter hermes --limit 8

agentops worker preflight --adapter openclaw
agentops operator loop-launch-packet --brief --adapter openclaw --limit 8
```

The brief is the preferred handoff payload when Codex wants Hermes or OpenClaw
to continue a supervised loop without reading the full launch packet. It keeps
only the adapter preflight command, current next/verify/receipt commands,
compact execution-chain state, bounded-runner policy id, confirmation and
prepared-action guidance, an explicit `agentops workflow run-task --adapter ...
--confirm-run` live command template, readback commands for task/run/manifest
evidence, and read-only/token-omission proof. The agent should copy commands
locally; the server never executes shell from the brief.

Bounded one-step advance:

```bash
agentops operator loop-control --limit 8
agentops operator advance-loop --fast-control --limit 8
agentops operator advance-loop --fast-control --limit 8 --confirm-advance
agentops operator action-receipts --limit 20
agentops operator loop-audit --limit 20
```

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
