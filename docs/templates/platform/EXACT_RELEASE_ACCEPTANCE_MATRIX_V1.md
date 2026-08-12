# Template Platform v1 exact release acceptance matrix

Status: Candidate / Canonical=false  
Source pack SHA-256: `f0b39687e21157b01d93c22c9820728c9a8a450d94f8ee22ffbc485decdd813b`  
Frozen contract: `1bce8f9e0312df9a29635a6988b62cd297b1ab14`  
Integration base: `df84e872f987edf07c8dabade6adac4613ca9182`

This matrix is the executable gate map for the Final Production
4-Conversation Pack. A row may move to `PASS` only when its receipt is bound to
the exact candidate or exact integration commit named in the evidence column.
Fixtures, conformance doubles and historical runs are never real-integration
receipts.

## Candidate admission

| Lane | Current exact object | Author tests | Independent decision | Integration admission |
| --- | --- | --- | --- | --- |
| C0 Shared Runtime | staged diff `f822b554a4783817d4fde7eb00c7a194df6bb3cdd7764f8d5cfc7fae223fd0d4`, index tree `79cb60f39b0edb6d3a6ab2cffa985640eed4459d` | Schema-enabled Python 3.11 94/94; Python 3.14 93 pass plus expected missing-`jsonschema` skip; UI build running after provenance correction | PENDING | DENIED until exact non-author PASS |
| C1 Research | `343cae665e2634d5a990920e8cffa9595cbac152` | Python 3.11/3.14 87/87 reported by author | RUNNING | DENIED until exact non-author PASS |
| C2 Career | failed candidate `2eb0d6699aedb83ab8fb67658aebdbaf2ed3b422`; replacement in progress | PENDING on replacement | prior exact review FAIL | DENIED |
| C3 Quant | `3361ed4063208e0044cdf621db45884a017e9e38` | Python 3.11/3.14 63/63 and shared schema 26/26 reported by author | RUNNING | DENIED until exact non-author PASS |

No implementation candidate is currently eligible to merge into integration.

## Exact integration gates

These gates run only after all four exact candidates have independent PASS
decisions and are merged without conflict into a new exact integration head.

| Gate family | Required checks | Current state | Required evidence |
| --- | --- | --- | --- |
| Backend | lint, type, unit, repository/service, API contract, integration | NOT_RUN on combined head | command log and machine-readable report bound to integration SHA |
| Frontend | lint, type, production build, route/state and authenticated UI E2E | NOT_RUN on combined head | build log, browser receipts/screenshots and integration SHA |
| Lifecycle | install, upgrade, disable, uninstall, migration dry-run/up/down, backup/restore | NOT_RUN on combined head | signed/tamper-evident lifecycle and migration receipts plus readback |
| Runtime | provider wiring, restart/reconcile, replay, outbox lease/recovery/DLQ | NOT_RUN on combined head | exact runtime and durable-state receipts |
| Authority | permission, Approval/PreparedAction consumption, revocation, purpose/scope isolation | NOT_RUN on combined head | negative and positive test report with authority tuple hashes |
| Cross-template | install all three; route, permission, migration, event and memory isolation; independent disable/upgrade | NOT_RUN | combined-head E2E receipt and Core Run/Artifact/Audit readback |
| Recovery | process/worker restart, concurrent duplicate submission, idempotency and crash boundaries | NOT_RUN | fault-injection report and authoritative post-restart readback |
| Security | secret scan, dependency audit, SBOM, command/path/link validation, artifact integrity | NOT_RUN on combined head | scanner reports, SBOM and checksums |
| Performance | load, latency, queue/resource/cost limits and resilience | NOT_RUN | workload definition, thresholds and results |
| Packaging | clean install, upgrade, uninstall/archive, locks, migrations, checksums and rollback | NOT_RUN | installable artifact and clean-environment receipts |
| Docs | architecture, ADR, API/CLI, operator/user/developer/authoring guides, runbooks, release notes | NOT_RUN | link/config validation and exact docs inventory |

## Domain real-integration gates

| Lane | Required final acceptance | Current state | Boundary |
| --- | --- | --- | --- |
| Research | real openJiuwen flow, real repository/data, governed GPU SSH target, long task, disconnect/preemption, worker restart, checkpoint/resume, metric/artifact transfer and Claim Gate | BLOCKED_EXTERNALLY | No governed GPU/SSH/Slurm target or receipt; openJiuwen dependency is not installed/pinned |
| Career | official target simulator, complete 48-month episode, restart, persisted recovery, replay hash, multiseed, future leakage zero and independent score | BLOCKED_EXTERNALLY | Official simulator distribution/version is unavailable |
| Quant | approved real/competition data, hashed cutoff snapshot, full workflow, risk, real backtest, no-lookahead, out-of-sample/rolling validation and 100% report evidence binding | BLOCKED_EXTERNALLY | Designated licensed data source and entitlement receipt are unavailable |

Local reference and negative-path tests continue while these resources are
unavailable, but they cannot change the rows above to `PASS`.

## Release and external-write gates

| Step | Precondition | Current state |
| --- | --- | --- |
| Freeze exact integration head | all candidate reviews PASS and merge receipts read back | NOT_READY |
| Generate Release Candidate | all exact-integration gates PASS; global P0/P1/P2 = 0 | NOT_READY |
| Create final PR to `main` | RC evidence index and rollback point complete | NOT_READY |
| Branch protection checks | final PR exists | NOT_RUN |
| Merge/tag/release | protected checks plus governed authorization | NOT_AUTHORIZED |
| Deploy and readback | governed deploy action plus release/tag exact match | NOT_AUTHORIZED |
| Final release receipt | health/version/migration/deploy readback verified | NOT_READY |
| Canonical promotion | verified final receipt and MIS/project-memory updates | DENIED |

Every external write follows `prepare -> authorize -> execute once -> readback
-> receipt`. Until all rows pass, the truthful project state remains
`BLOCKED_EXTERNALLY` only after internal P0/P1/P2 are zero; while internal fixes
remain open, it remains a non-canonical Candidate.
