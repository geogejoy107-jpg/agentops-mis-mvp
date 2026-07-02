# Commercial Prepared Action Execution Receipt Acceptance

## Purpose

This slice proves that a commercial post-action receipt can require a consumed
Approval Wall prepared action before it is written to the MIS ledger. It extends
receipt binding from "same prepared action hash" to "same prepared action hash
was approved, resumed once, and carries provider side-effect readback."

## Build Command Used

```bash
python3 scripts/commercial_prepared_action_execution_receipt_smoke.py
```

## Acceptance Result

Expected local result:

- Starts an isolated local MIS server with a temporary SQLite database.
- Creates one task, one run, and one high-risk commercial prepared action.
- Attempts to record a receipt with `required_prepared_action_status=consumed`
  before approval/resume and verifies it fails closed with
  `prepared_action_status_required`.
- Approves the linked approval gate.
- Resumes the prepared action exactly once with a mock provider side-effect id.
- Records an operator receipt with:
  - `--prepared-action-id`
  - `--prepared-action-hash`
  - `--required-prepared-action-status consumed`
- Verifies the resulting receipt exposes:
  - `prepared_action_hash_match: true`
  - `prepared_action_status: consumed`
  - `prepared_action_consumed: true`
  - `prepared_action_approved: true`
  - `prepared_action_provider_side_effect_id`
- Verifies receipt runtime events, receipt audit logs, receipt evaluation and
  evaluation audit logs each grow by exactly one in the isolated database.

## Errors Fixed

- Operator receipts could bind to a prepared action hash but could not require a
  post-resume state before recording.
- Receipt readback did not expose prepared-action approval/consumption timestamps
  or provider side-effect id.
- CLI receipt recording did not expose a status requirement for prepared-action
  post-action receipts.

## Safety Boundaries

- No billing provider call is performed.
- No destructive cleanup is performed.
- No hosted migration or Postgres cutover is performed.
- No Hermes, OpenClaw or live runtime action is executed.
- The receipt CLI does not execute `action_command` or `verify_command`.
- The default local DB is not touched.
- No raw prompt, raw model response, token, `.env`, DB dump, cache or generated
  packet output is committed.

## Related Commands

```bash
python3 scripts/commercial_receipt_prepared_action_binding_smoke.py
python3 scripts/commercial_prepared_action_execution_receipt_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py scripts/commercial_prepared_action_execution_receipt_smoke.py scripts/release_evidence_packet_smoke.py
git diff --check
```

## Known Limitations

- The smoke resumes a mock prepared action through the existing Approval Wall
  exact-resume path; it does not call a real billing provider, cleanup tool,
  hosted migration, Postgres cutover, Hermes, or OpenClaw runtime.
- This is a local/isolated SQLite proof, not hosted or commercial deployment
  readiness.

## Next Recommended Slice

Use the same `required_prepared_action_status=consumed` receipt pattern in a
runtime connector adapter path, so OpenClaw/Hermes/Dify-style external actions
can write post-action receipts after exact Approval Wall resume.
