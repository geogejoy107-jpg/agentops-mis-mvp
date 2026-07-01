# Commercial Receipt Plan Acceptance

## Scope

This slice adds a read-only commercial receipt plan packet. It defines the
human review receipt expected before risky commercial changes such as billing
provider calls, destructive cleanup, hosted customer data migration, Postgres
storage cutover, or live external side effects.

It does not record a receipt and does not execute any commercial action.

## Command

```bash
python3 scripts/commercial_receipt_plan_smoke.py
```

Strict current-head CI check:

```bash
python3 scripts/commercial_receipt_plan_smoke.py --require-current-ci
```

## Expected Behavior

- The default command passes when receipt-plan wiring and safety checks are
  valid.
- The packet emits `review_receipt_requirements` with reviewer role, required
  prepared-action fields, and the explicit rule that generic ledger approvals
  are not exact action resume.
- `execution_allowed_by_this_packet` remains `false`.
- `--require-current-ci` fails until the current branch is clean, not behind
  upstream, and exact-head CI is green.

## Safety Boundaries

- No server start.
- No DB read.
- No ledger mutation.
- No receipt recording.
- No billing, cleanup, hosted, Postgres, Hermes, OpenClaw, or live runtime call.
- No `.env`, credentials, raw logs, raw prompts, raw responses, private
  transcripts, or PR #22 contents.

## Verification

```bash
python3 scripts/commercial_receipt_plan_smoke.py
python3 scripts/commercial_promotion_packet_smoke.py
python3 scripts/commercial_promotion_preflight_smoke.py
python3 scripts/commercial_handoff_status_smoke.py
python3 scripts/commercial_evidence_packet_index_smoke.py
python3 scripts/release_branch_control_smoke.py
python3 -m py_compile scripts/commercial_receipt_plan_smoke.py scripts/release_evidence_packet_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/secret_scan_smoke.py
git diff --check
```

## Known Limits

- This is a plan packet only. It does not create approval rows or prepared
  actions.
- Receipt recording is the next separate packet.

## Next Slice

Add `commercial_receipt_recording_smoke.py` to prove a review receipt can be
recorded without executing billing, cleanup, hosted, Postgres, or live runtime
actions.
