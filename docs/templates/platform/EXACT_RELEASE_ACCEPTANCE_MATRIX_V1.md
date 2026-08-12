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
| C0 Shared Runtime | failed corrective candidate `7691d4a38613e23f42f9a433ddc2cffe188ba365`; replacement required | Author reports Python 3.11/3.14 99, isolated npm build/audit 0 vulnerabilities, HTTP/secret/compile/diff PASS and exact external SBOM | FAIL: concurrent retry finalizes via reconcile, then late original provider return overwrites authoritative state with `UNCERTAIN` | DENIED; intent ownership/CAS convergence fix and fresh review required |
| C1 Research | `a9fa0f02deeab9b3f0f0c90ea4edcd314e644bd0` | Author reports Python 3.11/3.14 90/90, schema 3/3, secret/compile/scope PASS; esbuild host watchdog timed out | replacement fresh review QUEUED | DENIED until exact non-author PASS and frontend build disposition |
| C2 Career | failed candidate `80b2a2dac8299590baab3aff76e3bf099f009d02`; replacement pending | Prior candidate: Python 3.11/3.14 73/73; shared schema 26/26 | FAIL: caller-forgeable Core boolean callbacks can promote official output | DENIED; concrete C0 cryptographic receipt verification and fresh review required |
| C3 Quant | failed candidate `b3828a2e0eb933d5211737a53f4b8cfca3e750d5`; replacement in progress | Exact C0 archive/security gates and Python 3.11/3.14 63/63 independently passed | FAIL: P0=0, P1=1, P2=1 | DENIED; Core trust-envelope/handoff replacement and fresh review required |

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
| Research | real openJiuwen flow, real repository/data, governed GPU SSH target, long task, disconnect/preemption, worker restart, checkpoint/resume, metric/artifact transfer and Claim Gate | BLOCKED_EXTERNALLY | Exact openJiuwen local TeamRuntime smoke passed, but no governed provider/MIS gateway receipt, GPU/SSH/Slurm target or long-run receipt exists |
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
