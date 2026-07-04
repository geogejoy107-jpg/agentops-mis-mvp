# Local Harness Proof Receipt Readback Status Acceptance

## Scope

This slice closes the stale next-step loop after governed harness launch
receipts landed. It does not add a new runtime, execute Hermes/OpenClaw, write
the ledger, or make the browser run shell commands.

## Change

- `LOCAL_HARNESS_PROOF_GOVERNED_LAUNCH_ACCEPTANCE.md` now documents
  `receipt_readback_command`.
- The next slice now points to receipt readback/status aggregation instead of
  the already-completed receipt-command work.
- `local_harness_proof_readback_smoke.py` checks every adapter exposes
  `agentops operator action-receipts --limit 20`.
- The same smoke fails if the governed launch acceptance doc regresses to the
  completed "add receipt command" next-step text.

## Verification

```bash
python3 scripts/local_harness_proof_readback_smoke.py
python3 -m py_compile scripts/local_harness_proof_readback_smoke.py
git diff --check
python3 scripts/secret_scan_smoke.py
```

## Next Slice

Add read-only receipt status aggregation to the local harness proof payload so
operators can see whether a copied launch packet has a matching recorded
operator receipt, while keeping receipt presence separate from live runtime
success.
