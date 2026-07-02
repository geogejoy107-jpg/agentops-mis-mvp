# Commercial Receipt Prepared Action Binding Acceptance

## Purpose

This slice proves that a commercial operator receipt can be bound to an exact
`prepared_actions.action_hash` before it is written to the MIS ledger. It closes
the gap between "a human recorded a receipt" and "the receipt references the
same prepared action that entered the Approval Wall."

## Build Command Used

```bash
python3 scripts/commercial_receipt_prepared_action_binding_smoke.py
```

## Acceptance Result

Expected local result:

- Starts an isolated local MIS server with a temporary SQLite database.
- Creates one task, one run, and one high-risk commercial prepared action.
- Runs `agentops operator record-action-receipt` without `--confirm-record` and
  verifies the preview does not mutate receipt, runtime, evaluation or audit
  counts.
- Attempts to bind a receipt to a missing prepared action and verifies the API
  fails closed with `prepared_action_not_found`.
- Runs `agentops operator record-action-receipt --confirm-record` with
  `--prepared-action-id` and `--prepared-action-hash`.
- Verifies the resulting receipt exposes:
  - `prepared_action_id`
  - `prepared_action_hash`
  - `prepared_action_hash_match: true`
  - `prepared_action_approval_id`
- Verifies runtime events, receipt audit logs, receipt evaluation and evaluation
  audit logs each grow by exactly one in the isolated database.

## Errors Fixed

- Operator receipt recording previously accepted only free-form action command
  hashes. It now optionally validates a referenced prepared action before
  recording.
- CLI receipt recording now supports `--prepared-action-id` and
  `--prepared-action-hash`.
- Receipt public projection now returns prepared-action binding metadata.

## Safety Boundaries

- No billing provider call is performed.
- No destructive cleanup is performed.
- No hosted migration or Postgres cutover is performed.
- No Hermes, OpenClaw or live runtime action is executed.
- The default local DB is not touched.
- No raw prompt, raw model response, token, `.env`, DB dump, cache or generated
  packet output is committed.

## Related Commands

```bash
python3 scripts/commercial_confirmed_receipt_recording_smoke.py
python3 scripts/commercial_receipt_prepared_action_binding_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py scripts/commercial_receipt_prepared_action_binding_smoke.py scripts/release_evidence_packet_smoke.py
git diff --check
```

## Known Limitations

- The receipt still records operator evidence only; it does not resume or
  execute the prepared action.
- This is a local/isolated SQLite proof, not hosted or commercial deployment
  readiness.
- Prepared action approval status is recorded for readback but is not required
  by this receipt layer, because review receipts may be collected before a
  final approval decision.

## Next Recommended Slice

Add a prepared-action execution receipt that proves:

1. the action was approved,
2. the exact stored action hash was resumed once,
3. the provider side-effect id was written,
4. the post-action receipt references the same action hash.
