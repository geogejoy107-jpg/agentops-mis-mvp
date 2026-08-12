# Template Platform v1 defect ledger

Status: Candidate / Canonical=false  
Integration base: `df84e872f987edf07c8dabade6adac4613ca9182`  
Frozen contract: `1bce8f9e0312df9a29635a6988b62cd297b1ab14`

This is the release-blocking defect ledger required by the Final Production
4-Conversation Pack. A green test suite is supporting evidence, not a release
decision. Every implementation candidate must be reviewed at an exact commit
or staged-diff hash by someone who did not author that candidate. A fix always
invalidates the previous review and requires a new independent review.

## Open internal defects

| ID | Severity | Lane / reviewed object | Finding | Required closure evidence | State |
| --- | --- | --- | --- | --- | --- |
| C0-001 | P1 | C0 staged diff `996e37f6237c56173ef670c3485ca7aa833bdf55bc641c80aca9c497a6e8754f` | Lifecycle and migration receipts could be replayed after persisted binding fields were modified. | Canonical receipt verification and tamper tests for lifecycle, migration, restore, runtime and revision/order fields. | Fixed in frozen candidate; independent review pending |
| C0-002 | P1 | same | Runtime output, Core approval consumption, production signature/provider wiring, outbox recovery and governed UI actions were incomplete. | Atomic Core consumption, existing Artifact readback, leased outbox recovery, Ed25519 verifier, real provider wiring, full API/CLI/UI tests. | Fixed in frozen candidate; independent review pending |
| C0-003 | P1 | current dirty C0 fix | Shared tests exposed missing `re` import and post-upgrade migration-plan readback rejected `target == installed`. | Both Python versions pass the complete shared suite, including regression assertions. | Fixed in frozen candidate; independent review pending |
| C1-001 | P1 | C1 commit `b6fb216661215eb524c1ed3ff1c24453c474f46e` | Real C0 `TemplateSDK` rejects Core references registered as domain repositories, undeclared per-route API registrations and a memory policy without a namespaced ID. | Mount with the real C0 SDK; exact declaration counts; no MIS Core duplication; all entrypoints callable. | Reopened |
| C1-002 | P1 | same | Domain code holds an HMAC signing secret and can forge an `allow` Core receipt. | C0 public-key-only, revocable, purpose-scoped receipt verifier wired through the production composition root; signing helpers restricted to tests. | Reopened |
| C1-003 | P1 | same | SSH process launch occurs before a durable launch fence; a crash can relaunch the same attempt. Marker writes also lack file/directory fsync. | Fence-before-launch protocol, authoritative restart reconciliation and crash-injection tests at each persistence boundary. | Reopened |
| C2-001 | P1 | C2 commit `2eb0d6699aedb83ab8fb67658aebdbaf2ed3b422` | `OfficialCareerSimulatorAdapter` accepts caller-controlled module metadata booleans as proof of an official distribution; no public-key verifier is injected. | Use the C0 public-key-only verifier for the exact distribution/version/bridge contract and receipts; ordinary callers cannot construct an official composition root. | Independent review failed; fixing |
| C2-002 | P1 | same | The governed service has official report/export methods, but the manifest exporter is the public fail-closed exporter and no official report/export operation is registered in API, CLI or UI. | Exact Core-terminal-bound report and submission operations exposed through authenticated API/CLI/UI, with live handler and UI tests. | Independent review failed; fixing |
| C2-003 | P1 | same | The SDK mount test imports an uncommitted `sdk.py` from a mutable sibling C0 worktree; neither reviewed Git tree contains that object. | Mount against a frozen reviewed C0 commit/tree and record its exact hash. | Independent review failed; fixing |
| C2-004 | P1 | same | Migration SQL execution failure can commit partial `ALTER TABLE` changes while leaving the old schema version; only post-readback failure restores backup. | One transaction or authoritative backup restore for every execution exception; fault injection proves schema and version remain consistent. | Independent review failed; fixing |
| C2-005 | P1 | same | Manifest provenance points to intermediate `b7fefbee...`, not the exact reviewed implementation. | Governed packaging stamps and verifies the exact source commit; candidate documentation remains truthful before stamping. | Independent review failed; fixing |
| C2-006 | P2 | same | Scope test uses an intermediate base and handoff claims JSON Schema verification when the dependency was skipped. | Use frozen contract `1bce8f9e...` and run the schema test in the available `jsonschema` environment before updating handoff. | Independent review failed; fixing |
| C3-001 | P1 | C3 commit `8db69ea12293d40590323c26002865eca4ad94e3` | A Risk Officer evaluation can be reused to execute a different portfolio proposal. | Canonical proposal hash bound through RiskDecision, Core Evaluation, checkpoint, protocol, backtest, artifacts, report, audit and final receipt. | Fixing |
| C3-002 | P1 | same | RiskDecision is not durably stored/read back; database replacement can leave one proposal ID with divergent durable and returned content while restart completes. | Immutable persisted/read-back RiskDecision and approved proposal; body/hash replacement and restart attacks fail closed. | Fixing |
| C3-003 | P2 | same | The exact-approved-weights test and handoff claimed coverage that did not exercise post-approval replacement. | Correct adversarial tests and truthful handoff. | Fixing |
| C3-004 | P1 | C3 fix candidate `cd77b3ba2355c19fb8bf87e1fdf6ceaf99cc6d10` | Restart only compares project/run, so the same workflow/run can resume with a different request and Core action/PreparedAction/Approval tuple after `risk_passed`. | Persist and revalidate the exact request hash and complete Core authority tuple on every restart before any read or side effect. | Independent review failed |
| C3-005 | P1 | same | Rewriting Proposal, RiskDecision evaluation binding and checkpoint together can pass restart because the approved execution hash omits the evaluation binding and readback does not bind proposal hash metadata. | Immutable Core Evaluation binding to proposal hash and decision identity; checkpoint rewrite cannot substitute it; deterministic decision ID is recomputed. | Independent review failed |
| C3-006 | P2 | same | A copied RiskDecision with an arbitrary new ID is accepted after the checkpoint points at it. The line's SDK test also uses a conformance double rather than the real C0 class. | Recompute deterministic decision identity and run a subprocess against the real C0 `TemplateSDK`. | Independent review failed |

## Pending independent decisions

| Lane | Exact candidate | Required reviewer state |
| --- | --- | --- |
| C0 Shared Runtime | Staged diff `ad58468f5a529f163b0fe1bbd69f5103538f14971889cdbdff7590e55d2006ba`; index tree `d08bb6bc583bafd4b9f66ccd1a0ecfbb1792d58c` | A non-author must review this exact staged object; both Python versions have 94/94 passing when `jsonschema` is available, and the production UI build passes. |
| C1 Research | `b6fb216661215eb524c1ed3ff1c24453c474f46e` is failed/reopened | A new exact commit is required, then review by a non-author. |
| C2 Career | `2eb0d6699aedb83ab8fb67658aebdbaf2ed3b422` | Independent exact-commit review running. |
| C3 Quant | Failed fix candidate `cd77b3ba2355c19fb8bf87e1fdf6ceaf99cc6d10` | A new fix commit is in progress; then a new exact review by a non-author is required. |

## External gates (isolated; not internal defect waivers)

| Gate | Current evidence | State |
| --- | --- | --- |
| Research real GPU / SSH / Slurm | No governed target credentials or real scheduler allocation are available. Fixtures cannot satisfy the production gate. | `BLOCKED_EXTERNALLY` |
| Career official 48-month simulator | The official simulator distribution and exact version are not available. Reference runs remain non-official. | `BLOCKED_EXTERNALLY` |
| Quant official market data | No governed official data entitlement/receipt is available. Reference snapshots remain non-official. | `BLOCKED_EXTERNALLY` |
| Governed deployment | Deployment authentication and an approved release action are not available in this execution context. | `BLOCKED_EXTERNALLY` |

External gates do not stop safe implementation, review or integration work.
They do prevent `FINAL_STATE: COMPLETE`, canonical promotion, release claims and
production deployment until execution plus authoritative readback receipts exist.

## Release rule

Integration is allowed only for an exact candidate with no open P0/P1/P2 in its
independent review. Final release additionally requires zero global P0/P1/P2,
all exact-integration regression gates, MIS dogfood readback, branch protection,
governed external writes and a verified final release receipt.
