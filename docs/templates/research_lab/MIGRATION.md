# Research Lab v0 to v1 migration

Source schema: `research_lab_mis_evidence_v1`

Target schema: `research-lab-domain/v1`

The transformer maps legacy experiment, trial, attempt, metric and artifact
records to Research Lab namespaced records stored by the shared Core domain
repository. Every target keeps a source hash and `legacy_read_only=true`.

Required flow:

1. Export the bounded legacy rows through the current Core-controlled path.
2. Run `migration-dry-run`; duplicates and unmappable kinds block execution.
3. Create and verify a shared backup receipt.
4. Obtain Core approval for the migration checksum/action hash.
5. Transform and write records through `TemplateMigrationPort.apply_once`.
6. Verify exact source/target identity sets and historical readability.
7. Emit a migration readback receipt.

In-flight backup and apply receipts are also recorded in a local SQLite
coordination journal using WAL and `synchronous=FULL`, so a C1 process restart
does not initiate a second backup or apply. The journal is not authority:
entries are already signed by Core, replay is reconciled against Core, and a
missing local journal never overrides a persisted Core result. The final typed
LifecycleReceipt receives a separate signed document attestation.

Rollback restores the shared backup and archives v1 records. No silent data
loss or independent Research SQLite database is permitted.
