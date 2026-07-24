# Relay Activation Recovery Controller Acceptance

## Scope

This acceptance covers the private exact-confirmed non-systemd recovery writer
in `agentops_mis_cli.relay_activation_recovery_controller`.

It consumes an explicit `decision_sha256`, repeats the complete stable recovery
observation against the same store, and performs at most one of:

- append one already-observed journal revision;
- publish one forward success receipt;
- append one terminal revision for an existing exact receipt; or
- return an already-complete terminal state without writing.

It has no production opener, systemd mutation adapter, CLI, API, or browser
caller.

## Confirmation And Write Contract

Malformed confirmation hashes fail before reading the store. A canonical but
stale hash fails after a read-only preview and before any write. A blocked
decision and every `run_step` decision also fail with zero writes.

The snapshot loader is not injectable independently from the store. The same
store that supplies the two stable journal snapshots receives the selected
write, preventing a confirm-one/write-another split.

For each supported action:

- `record_observation` rebuilds the canonical observation from the confirmed
  prerequisite/systemd snapshot, requires its hash to match the decision, and
  appends exactly one `observed` revision;
- `publish_success_receipt` requires a forward verified observation and
  publishes exactly one `activation_succeeded` receipt;
- `publish_terminal_revision` binds an existing exact orphan receipt in exactly
  one terminal revision; and
- `complete` validates and projects the existing terminal state with no write.

A write-tracking wrapper switches the error boundary only immediately before
calling `publish_revision` or `publish_receipt`. A failure after that point
returns only `activation_recovery_required`; write-before-validation failures
retain their bounded zero-write error.

## Verification

Run:

```bash
python3 -m py_compile \
  agentops_mis_cli/relay_activation_recovery_controller.py \
  agentops_mis_cli/relay_activation_recovery_preview.py \
  scripts/relay_activation_recovery_controller_smoke.py
python3 scripts/relay_activation_recovery_controller_smoke.py
python3.11 scripts/relay_activation_recovery_controller_smoke.py
python3 scripts/relay_activation_recovery_preview_smoke.py
python3 scripts/relay_activation_recovery_decision_smoke.py
python3 scripts/relay_activation_journal_smoke.py
python3 scripts/relay_activation_scan_smoke.py
python3 scripts/relay_deploy_contract_smoke.py
git diff --check
```

Expected summary:

```json
{
  "blocked_action_zero_write": true,
  "cli_surface_exposed": false,
  "complete_zero_write": true,
  "confirmation_zero_write": true,
  "network_used": false,
  "observation_one_write": true,
  "ok": true,
  "post_write_failure_retained": true,
  "private_payload_omitted": true,
  "receipt_one_write": true,
  "systemd_action_zero_write": true,
  "systemd_mutation_performed": false,
  "terminal_one_write": true,
  "write_scope": "fixture_journal_only"
}
```

The smoke exercises invalid and stale confirmation, blocked rollback, an
unsupported forward mutation, observation completion after an interrupted
daemon reload, success-receipt publication, orphan-receipt terminalization,
idempotent complete, and a fault injected after a durable revision write.

## Truth Boundary

This slice does not execute `daemon-reload`, `enable`, `start`, `stop`, or
`disable`. It does not complete the rollback verification/receipt contract and
does not expose a recovery command. The next writer slice must bind the same
confirmed decision to exactly one scanner-bound systemd step, then separately
finish rollback verification and terminal receipt semantics before any CLI is
enabled.
