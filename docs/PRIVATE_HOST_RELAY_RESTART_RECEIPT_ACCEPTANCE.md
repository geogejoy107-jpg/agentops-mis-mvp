# Private Host Relay Restart Receipt Acceptance

Date: 2026-07-18

## Accepted Slice

The private restart receipt can durably coordinate one Relay transition across
the active Relay config and Host config without exposing either file to HTTP,
audit or UI. It binds an action, validated transition ref, persistent monotonic
transaction sequence and ordered state revision.

The receipt is a local crash/rollback primitive. It is not yet wired to the
Owner confirmation route or managed Host supervisor.

## Proven Boundaries

- receipt, sequence, archive, lock and target files require same-owner regular
  files in mode `0600` under non-symlink directories in mode `0700`;
- both original and target config pairs are size bounded and stored only in the
  private receipt;
- the transition ref is required on every state or config operation and omitted
  from public output;
- transaction sequence persists after receipt finalization and increases for a
  second transition;
- stale transaction sequence and stale state revision fail closed;
- a nonterminal receipt blocks replacement and finalization;
- a terminal receipt may be archived/finalized or explicitly replaced;
- second-file target write failure restores both originals;
- second-file restore failure reapplies both targets, preventing mixed config;
- public output omits config bytes, refs, paths and digests.

## Verification

```bash
python3 -m py_compile \
  agentops_mis_cli/relay_restart.py \
  scripts/private_host_relay_restart_receipt_smoke.py
python3 scripts/private_host_relay_restart_receipt_smoke.py
git diff --check
```

The smoke passed all permission, symlink, size, replay, ordering, two-file
failure-injection, terminal lifecycle and redaction checks. It uses no network,
subprocess, database, Tailscale or Worker access.

## Remaining Integration

- create and apply the receipt inside the exact confirmed Relay transaction;
- roll back from a broken Owner response before any restart request;
- send only transaction sequence/ref-bound restart requests to the exact Host
  parent;
- transition through validation, healthy, restore and rollback states from the
  supervisor;
- reconcile unfinished receipts on managed Host startup;
- surface only the bounded public state from `GET /api/host/relay`.
