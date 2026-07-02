# Commercial Rerun Bundle Preview Acceptance

## Scope

This slice adds a read-only rerun bundle preview to reproduce the commercial evidence packet chain.
It lists deterministic commands an operator can run on another machine to
reproduce the packet evidence from current source.

It does not execute the bundle, start a server, read a database, mutate a
ledger, call Hermes/OpenClaw, call billing providers, run cleanup, perform
hosted migration, cut over storage, or read PR #22 contents.

## Command

```bash
python3 scripts/commercial_rerun_bundle_preview_smoke.py
```

## Expected Behavior

- The command passes when rerun bundle docs, CI wiring and release manifest
  wiring are present.
- The output includes a preview-only command list for the commercial evidence
  packet chain.
- The command list covers packet index, current evidence status, handoff,
  promotion preflight, promotion packet, receipt plan, receipt recording, rerun
  bundle preview, branch control, release evidence, secret scan and diff check.
- Safety flags remain negative for server start, DB read, ledger mutation,
  billing, cleanup, hosted migration, Postgres cutover and live runtime.

## Safety Boundaries

- No server start.
- No DB read.
- No ledger mutation.
- No billing, cleanup, hosted, Postgres, Hermes, OpenClaw, or live runtime call.
- No `.env`, credentials, raw logs, raw prompts, raw responses, private
  transcripts, generated packet snapshots, or PR #22 contents.
- The packet is a reproducibility preview, not a commercial readiness claim.

## Verification

```bash
python3 scripts/commercial_rerun_bundle_preview_smoke.py
python3 scripts/commercial_receipt_recording_smoke.py
python3 scripts/commercial_handoff_status_smoke.py
python3 scripts/commercial_evidence_packet_index_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/secret_scan_smoke.py
python3 -m py_compile scripts/commercial_rerun_bundle_preview_smoke.py scripts/release_evidence_packet_smoke.py
git diff --check
```

## Known Limits

- This preview does not run the command bundle.
- It does not record operator receipts or execute risky commercial actions.
- Current-head green CI is still checked by promotion/release packet commands,
  not by this preview alone.

## Next Slice

After this packet lands, the commercial clean-room lane should move from
preview-only evidence packets toward the first operator-confirmed receipt write
that still uses the Approval Wall and exact prepared-action hash.
