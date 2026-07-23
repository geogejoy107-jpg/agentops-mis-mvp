# Relay Activation Journal Core Acceptance

## Scope

This acceptance covers the immutable, credential-free activation journal
primitives in `agentops_mis_cli.relay_activation_journal`. It is a private
foundation for a future confirmed Relay activation controller.

This slice does **not** unlock `--confirm-activate`, open the production
`/var/lib/agentops-relayctl` tree, invoke systemd mutations, acquire the
production lifecycle lock, or recover a real Linux service. The production
CLI remains fail-closed with `activation_mutation_unavailable`.

## Durable Contract

Each canonical ASCII JSON revision is at most 16 KiB and binds:

- the exact activation plan, release, version, and unit identities;
- the initial `enabled` or `disabled` state and `active` or `inactive` state;
- hashes of the initial enablement inventory and installed unit identity;
- a monotonic revision number and the previous revision hash;
- one strict prepared, intent, observed, or terminal phase;
- the intent and bounded observation labels;
- a step-specific observation evidence hash;
- whether this transaction owns an enable or start mutation;
- the immutable terminal receipt hash.

The observation evidence hash is reserved for the controller's canonical,
step-specific evidence. For enable ownership it must bind the exact
post-enable link inventory. For start ownership it must bind the exact
post-start InvocationID and unit identity. Raw systemd output is not retained.

The validator requires the exact forward sequence:

```text
prepared
-> daemon_reload intent/observed
-> optional enable intent/observed
-> optional start intent/observed
-> verify intent/observed
-> active receipt and terminal revision
```

The optional steps are derived from the bound pre-state. A rollback can begin
only after a durable observed step. It can stop only a start owned by this
transaction, disable only an enable owned by this transaction, must verify the
restored state, and can reach `service_state_rolled_back` only with both
ownership flags cleared.

## Storage Boundary

The private fixture store exercises the intended production algorithm:

- owner-only `0700` directories and `0600` regular files;
- descriptor-relative, no-follow opens and pre/open/post identity checks;
- a newly created plan directory for revision 1; an existing empty directory
  is recovery-required rather than silently reused;
- `O_EXCL` temporary files, full writes, file fsync, hard-link no-replace
  publication, parent fsync, temporary unlink, and a second parent fsync;
- immutable, contiguous hash chains with no gaps, forks, unknown names,
  ambiguous temporary files, or duplicate revision publication;
- one-to-one terminal revision and receipt binding;
- exact receipt replay returning `existing`;
- bounded plan, revision, receipt, and record counts;
- bounded public projections that omit paths, raw observations, credentials,
  and private journal bodies.

The production writer is intentionally absent. Before it can be added, the
installed-tree status/scanner must validate the exact journal namespace and a
controller must hold the existing lifecycle lock across final plan refresh,
all writes, mutation, verification, rollback, and terminal persistence.

## Verification

Run:

```bash
python3 -m py_compile \
  agentops_mis_cli/relay_activation_journal.py \
  scripts/relay_activation_journal_smoke.py
python3 scripts/relay_activation_journal_smoke.py
git diff --check
```

The deterministic smoke verifies:

- one complete active chain and one complete rollback chain;
- receipt-before-terminal recovery state and exact receipt idempotency;
- rejection of skipped steps, invalid ownership transitions, duplicate keys,
  unknown keys, noncanonical bytes, wrong hashes, booleans-as-integers, and
  hostile JSON value types;
- rejection of pre-existing empty plan directories, symlink roots, unsafe
  directory modes, path escapes, unknown temporary files, and receipt overflow;
- failure injection at write, file fsync, no-replace link, and temporary unlink;
- descriptor closure, zero network calls, zero subprocesses, and zero systemd
  calls.

Expected result:

```json
{
  "failure_injection_cases": 4,
  "ok": true,
  "operation": "relay_activation_journal_smoke",
  "production_mutation_exposed": false,
  "recovery_cases": 4,
  "schema_id": "agentops.relay.activation-journal.v0",
  "terminal_chains": 2
}
```

## Remaining Gates

This acceptance is not evidence of confirmed service activation. The remaining
sequence is:

1. extend read-only installed-state scanning to the exact journal namespace;
2. add the lifecycle-lock-bound production store opener;
3. implement the narrow systemd mutation adapter;
4. implement confirmed controller, crash recovery, and ownership-safe rollback;
5. pass real Linux systemd interruption tests;
6. pass public Relay and physical ordinary-browser acceptance.
