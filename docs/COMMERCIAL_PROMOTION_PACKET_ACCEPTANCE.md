# Commercial Promotion Packet Acceptance

## Scope

This slice adds a read-only commercial promotion packet generator. It bundles
current source evidence references for promotion review: exact HEAD, current
CI state, promotion preflight, strict release evidence, the commercial packet
index, and the release command manifest.

It is not a hosted, billing, cleanup, Postgres, or live-runtime readiness claim.

## Command

```bash
python3 scripts/commercial_promotion_packet_smoke.py
```

Strict local ready check:

```bash
python3 scripts/commercial_promotion_packet_smoke.py --require-ready
```

## Expected Behavior

- The default command passes when packet wiring and safety checks are valid.
- `promotion_packet_ready` remains `false` while exact-head CI is missing,
  pending, failed, or not matched to the current HEAD.
- `promotion_packet_ready` is only `true` when the working tree is clean, the
  branch is not behind upstream, exact-head CI is completed successfully, and
  no safety failures are present.
- `--require-ready` fails until the same strict conditions are true.

## Safety Boundaries

- No server start.
- No DB read.
- No ledger mutation.
- No billing, cleanup, hosted, Postgres, Hermes, OpenClaw, or live runtime call.
- No `.env`, credentials, raw logs, raw prompts, raw responses, private
  transcripts, or PR #22 contents.
- The packet references current-source evidence commands and docs; it does not
  commit rendered packet snapshots as authority.

## Verification

```bash
python3 scripts/commercial_promotion_packet_smoke.py
python3 scripts/commercial_promotion_preflight_smoke.py
python3 scripts/commercial_handoff_status_smoke.py
python3 scripts/commercial_current_evidence_status_smoke.py
python3 scripts/commercial_evidence_packet_index_smoke.py
python3 scripts/release_branch_control_smoke.py
python3 -m py_compile scripts/commercial_promotion_packet_smoke.py scripts/release_evidence_packet_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/secret_scan_smoke.py
git diff --check
```

## Known Limits

- This packet is still a review packet, not commercial product readiness.
- Manual live Hermes/OpenClaw product evidence remains separately confirmed and
  intentionally excluded from CI.

## Next Slice

Add `commercial_receipt_plan_smoke.py` to define the human receipt expected
before risky commercial changes.
