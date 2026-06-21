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
- `--mis-ledger` records parent/child tasks, parent/child runs, tool calls, evaluations, audit logs, and a final artifact through Agent Gateway.
- Raw prompts, raw responses, credentials, and private transcripts are omitted.
- Logs live under `.agentops_runtime/loops/`, which is gitignored.
- Live runtime calls require `--confirm-live`.
- Live runtime calls and MIS ledger writeback are separate switches: dry-run can still be recorded to MIS for demo/proof without calling Hermes/OpenClaw.

## Commands

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

Expected MIS writeback:

- one parent task/run owned by the Codex loop supervisor
- one child task/run per Hermes/OpenClaw output
- one tool call and one rule evaluation per child run
- audit evidence for output recording and loop completion
- one final `loop_next_action` artifact linked to the parent run

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

The smoke test starts an isolated temporary SQLite-backed server, runs `--mis-ledger`, and verifies `tasks`, `runs`, `tool_calls`, `evaluations`, `audit_logs`, and `artifacts` without touching the default `agentops_mis.db`.

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
