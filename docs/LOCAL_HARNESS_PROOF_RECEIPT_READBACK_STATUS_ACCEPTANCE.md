# Local Harness Proof Receipt Readback Status Acceptance

## Scope

This slice closes the stale next-step loop after governed harness launch
receipts landed. It does not add a new runtime, execute Hermes/OpenClaw, write
the ledger, or make the browser run shell commands.

## Change

- `GET /api/operator/local-harness-proof` and
  `agentops operator local-harness-proof` now expose per-adapter
  `governed_launch.receipt_status`.
- The top-level `governed_launch_packet` now exposes `receipt_summary`.
- `receipt readback/status aggregation` distinguishes:
  - current receipt matching the latest launch `action_signature`;
  - stale receipt for the same launch `action_id` but older/different
    signature;
  - missing receipt.
- `receipt presence separate from live runtime`: the receipt proves that the
  launch packet was recorded/read back, not that Hermes/OpenClaw completed the
  run.
- Each adapter now exposes a scoped receipt readback command:
  `agentops operator action-receipts --limit 20 --source local_harness_proof.governed_launch --action-id local_harness_proof:openclaw --action-signature <signature>`.
  The adapter changes the `action-id`; the filter trio is the contract.
- `local_harness_proof_readback_smoke.py` now seeds fixture coverage for all
  three receipt states: OpenClaw current, Hermes stale and mock missing.
- The filtered readback is read-only and must not be used as runtime-success
  proof by itself.

## Verification

```bash
python3 -m py_compile server.py scripts/local_harness_proof_readback_smoke.py
python3 scripts/local_harness_proof_readback_smoke.py
git diff --check
python3 scripts/secret_scan_smoke.py
```

Current local verification:

```text
local_harness_proof_readback_smoke: ok
workspace_id: harness-proof-smoke
safety: read_only=true, ledger_mutated=false, live_execution_performed=false
```

## Next Slice

Surface the same receipt status in the Worker Console so operators can see
current/stale/missing launch receipts before copying the next governed command.
