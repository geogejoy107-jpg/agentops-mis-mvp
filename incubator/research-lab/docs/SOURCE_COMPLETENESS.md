# Research Lab v0.3.1 source completeness

> Updated: 2026-06-24  
> Branch: `incubator/research-lab-ssh-v0-3`  
> PR: `#21`  
> Canonical: false

## Uploaded and reviewable

- standalone package metadata and module entrypoint;
- Experiment Protocol, Integrity Policy, and parameter-matrix contracts;
- frozen code/data/model/environment/resolved-configuration provenance;
- compact protected-field handling;
- local process executor contract;
- runtime metric/actual/artifact helper APIs;
- host/GPU resource fingerprint helper;
- non-secret SSH server profile registry;
- deterministic allowlisted staging and safe extraction;
- guarded SSH executor boundary;
- protocol deviation and Scientific Claim Gate logic;
- protocol and provenance contract tests;
- path-scoped GitHub Actions checks on Python 3.11, 3.12, and 3.13;
- architecture, async execution, SSH, open-source absorption, and Agent Plan documents.

## Not yet uploaded as a complete runnable remote package

- standalone SQLite ledger and migrations;
- full orchestrator and retry/recovery persistence;
- CLI commands;
- report and read-only local website;
- full local and loopback-SSH test suite;
- the complete example training package;
- durable detached SSH polling, cancellation, and reconciliation.

The independently runnable local artifact remains the broader implementation evidence. GitHub PR #21 currently proves only the uploaded contract slice and its path-scoped checks. Do not treat local 25-test evidence as a remote PR CI result.

## Real-infrastructure boundary

No authorized Linux/GPU server has been exercised from this environment. The default OpenSSH path therefore fails closed as `remote_unknown` rather than claiming successful remote execution. Real-server evidence must cover enrollment, host verification, staging, execution, collection, interruption, cancellation, orphan reconciliation, and artifact readback.

## Next source slice

1. Upload the SQLite ledger and compact orchestrator.
2. Upload CLI and example training workload.
3. Add local end-to-end tests and claim-gate negative tests.
4. Expand CI from contract checks to the full standalone suite.
5. Rebase or refresh the Draft PR against the latest `main` before review.
