# Research Lab operator guide

## Configuration and secrets

SSH credentials are references such as `vault://...`, `keychain://...` or
`mis-secret://...`; plaintext credentials are rejected. Known-host files are
required and strict host verification cannot be disabled. Dataset, code and
environment inputs must be pinned before protocol freeze.

## Health and alerts

Use template health/readiness, runtime health and queue health through the
shared platform. `unavailable`, `degraded`, stale heartbeat,
`remote_unknown`, preemption and checkpoint incompatibility are explicit
states. Alerts should fire for stale heartbeat, budget exhaustion, DLQ events,
remote uncertainty, corrupt checkpoints and failed Artifact verification.

## Recovery

1. Pause new attempts for the affected Trial.
2. Reconcile the existing PID, remote wrapper marker or scheduler job ID.
3. Read logs using the retained cursor and verify transferred Artifact hashes.
4. Discover the latest compatible checkpoint by protocol hash and code commit.
5. Prepare a resume action and obtain Core Approval when policy requires it.
6. Execute once, read back the running attempt and retain its receipt.

Never retry a remote-unknown attempt automatically; it could duplicate GPU
work. Corrupt and legacy-pickle checkpoints fail closed. Legacy pickle
conversion requires a separately approved sandbox workflow.

## Upgrade, rollback and archive

Run migration dry-run, create a shared backup receipt, approve the exact action
hash, migrate once and compare source/target identities. Rollback archives new
v1 records and restores the shared backup; it does not silently delete
history. Uninstall also archives records so old Research Receipts remain
readable.
