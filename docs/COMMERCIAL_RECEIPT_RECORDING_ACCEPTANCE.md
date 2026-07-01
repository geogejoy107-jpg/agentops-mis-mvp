# Commercial Receipt Recording Acceptance

## Scope

This slice adds a CI-safe commercial receipt recording packet. It materializes
review receipt requests for risky commercial changes, including action IDs,
normalized action arguments, immutable action hashes, review hashes,
checkpoints, and idempotency keys.

It does not write those receipts to the ledger and does not execute any
commercial action.

## Command

```bash
python3 scripts/commercial_receipt_recording_smoke.py
```

Strict current-head CI check:

```bash
python3 scripts/commercial_receipt_recording_smoke.py --require-current-ci
```

## Expected Behavior

- The default command passes when receipt-recording wiring and safety checks
  are valid.
- The packet emits one preview-only receipt request for each risky commercial
  boundary: billing provider call, destructive cleanup, hosted customer data
  migration, Postgres storage cutover, and live external side effect.
- Each request includes `normalized_action_arguments`, `action_hash`,
  `review_hash`, `checkpoint`, and `idempotency_key`.
- `recorded_to_ledger` remains `false`.
- `execution_allowed_by_this_packet` remains `false`.
- `--require-current-ci` fails until the current branch is clean, not behind
  upstream, and exact-head CI is green.

## Evidence Shape

The packet is a receipt-recording preview, not a committed receipt transaction.
It proves the exact metadata shape that a later operator-confirmed transaction
would record, while preserving the current release freeze and Approval Wall
boundaries.

## Safety Boundaries

- No server start.
- No DB read.
- No ledger mutation.
- No real receipt recording.
- No billing, cleanup, hosted, Postgres, Hermes, OpenClaw, or live runtime call.
- No `.env`, credentials, raw logs, raw prompts, raw responses, private
  transcripts, or PR #22 contents.

## Verification

```bash
python3 scripts/commercial_receipt_recording_smoke.py
python3 scripts/commercial_receipt_plan_smoke.py
python3 scripts/commercial_promotion_packet_smoke.py
python3 scripts/commercial_promotion_preflight_smoke.py
python3 scripts/commercial_handoff_status_smoke.py
python3 scripts/commercial_evidence_packet_index_smoke.py
python3 scripts/release_branch_control_smoke.py
python3 -m py_compile scripts/commercial_receipt_recording_smoke.py scripts/commercial_receipt_plan_smoke.py scripts/release_evidence_packet_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/secret_scan_smoke.py
git diff --check
```

## Known Limits

- This is a preview-only recording packet. It does not create
  `operator.action_queue_receipt` rows.
- It does not make billing, cleanup, hosted deployment, Postgres cutover, or
  live external side effects safe to execute.

## Next Slice

Add `commercial_rerun_bundle_preview_smoke.py` to list the deterministic
commands needed to reproduce the commercial evidence packet chain on another
machine without mutating receipts or running live systems.
