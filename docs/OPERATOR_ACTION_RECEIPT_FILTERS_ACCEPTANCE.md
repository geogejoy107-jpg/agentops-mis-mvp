# Operator Action Receipt Filters Acceptance

## Scope

This slice makes operator action receipt readback precise enough for local
harness proof and future agent/MCP work packets.

It does not execute shell commands, call Hermes/OpenClaw, mutate the ledger from
readback, add a schema migration, or make receipt presence equal runtime
success.

## Change

- `GET /api/operator/action-receipts` accepts exact read-only filters:
  `source`, `action_id`, and `action_signature`.
- `agentops operator action-receipts` exposes matching CLI flags:
  `--source`, `--action-id`, and `--action-signature`.
- Filtered responses echo `filters` and `filtering` so a worker can prove which
  receipt lookup was performed.
- Local harness governed launch packets now emit scoped receipt readback
  commands such as:

```bash
agentops operator action-receipts \
  --limit 20 \
  --source local_harness_proof.governed_launch \
  --action-id local_harness_proof:openclaw \
  --action-signature <signature>
```

## Verification

Run:

```bash
python3 -m py_compile server.py agentops_mis_cli/agentops.py scripts/operator_action_receipts_cli_smoke.py scripts/operator_action_receipt_smoke.py scripts/local_harness_proof_readback_smoke.py
python3 scripts/operator_action_receipts_cli_smoke.py
python3 scripts/operator_action_receipt_smoke.py
python3 scripts/local_harness_proof_readback_smoke.py
git diff --check
python3 scripts/secret_scan_smoke.py
```

## Acceptance

- API filtered GET returns the exact target receipt despite newer noise
  receipts.
- CLI filtered readback returns the same exact target receipt and remains
  read-only.
- Local harness proof packets include source, action id and action signature in
  receipt readback commands.
- Filtered readback reports `ledger_mutated=false` and
  `live_execution_performed=false`.
- Receipt presence remains separate from live runtime success.

## Known Limits

- The receipt ledger proves RECORD-stage operator evidence only.
- Product proof still requires completed run, tool-call, runtime-event,
  evaluation, audit, artifact and plan-evidence rows for the target run.
