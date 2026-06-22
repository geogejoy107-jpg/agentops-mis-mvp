# AgentOps MIS v1.5 Merge Readiness Checklist

> Frozen source: `8d1827e00629bdca4779794121ca4a31dfa3f1e1`  
> Current status: `NOT_READY`

## 1. Branch control

- [ ] Confirm the intended development branch HEAD.
- [ ] Freeze a release-candidate SHA.
- [ ] Pause unrelated feature work during hardening.
- [ ] Confirm no databases, runtime state, credentials, generated service files or logs are tracked.
- [ ] Preserve reviewable functional history; do not turn all 109 commits into one opaque change.

```bash
git fetch origin
git rev-parse codex/agent-gateway-kb-demo
git status --short
git diff --check main...codex/agent-gateway-kb-demo
```

## 2. Agent Plan integrity

- [x] Agent-created plans can only be `draft` or `submitted`.
- [x] Human/admin/policy identity alone can approve or reject a plan.
- [x] High/critical or approval-required plans create/reference a real approval object and cannot authorize `run_start` until approved.
- [x] Plan approve/reject transitions append audit/runtime evidence with actor and approval object references.
- [x] Plan has an immutable hash/version.
- [x] Verification result has a hash and timestamp.
- [x] Every referenced spec exists and is readable.
- [x] Every referenced base exists.
- [x] Every referenced memory exists, is visible and has an allowed review status.
- [x] Proposed files stay inside the allowed workspace/repository.
- [x] Real run links an `agent_plan_id`.
- [x] Run Agent/task/workspace match the plan.
- [x] Superseded, changed, or alternate plans cannot authorize/rebind execution.
- [x] Delivery gate compares execution evidence with the declared plan: `operator evidence-report` checks run `agent_plan_id`/`plan_hash`, plan verification, plan approval, verified `plan_evidence_manifest`, tool/evaluation/artifact/audit evidence, pending approvals, and read-only DB fingerprint stability.

Required checks:

```bash
python3 scripts/agent_plan_integrity_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/run_start_plan_gate_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/operator_evidence_report_smoke.py
```

Add new negative tests:

```text
Agent tries to create status=approved       rejected
fake memory/base/spec reference             verification fails
plan Agent differs from run Agent           execution rejected
plan changes after approval                 old approval invalid
run without verified plan                   rejected for governed workflow
execution touches undeclared file/tool      readiness gate fails
```

## 2.5 Approval Wall exact action resume

- [x] Prepared actions persist normalized arguments, policy version, checkpoint and idempotency key.
- [x] Prepared actions store and verify an immutable `action_hash`.
- [x] Approval authorizes a prepared action without performing the side effect.
- [x] Resume requires approved approval plus matching hash.
- [x] Resume writes provider side-effect evidence and `consumed_at`.
- [x] Replay after `consumed_at` is rejected.
- [x] CLI supports create/get/resume.
- [x] Customer-worker Hermes/OpenClaw external-write intent pauses before live runtime execution and creates a prepared action plus approval.
- [ ] All high-risk external connector/runtime tool paths use prepared actions before shared/commercial deployment.

Required check:

```bash
python3 scripts/prepared_action_approval_wall_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/customer_worker_external_write_gate_smoke.py
```

## 3. Knowledge safety and quality

- [x] Knowledge documents carry workspace/project/access metadata where required.
- [x] Repo-global doctrine is separated from customer-private knowledge.
- [x] Remote/scoped search enforces authorization.
- [x] Candidate/rejected memory is not treated as authority.
- [x] Index excludes credentials, databases, runtime logs, caches and raw customer files.
- [x] Redaction occurs before indexing.
- [x] Search returns source path, hash, scope and retrieval ID.
- [x] Add heading-aware chunks rather than only full-document rows.
- [x] Add a Chinese/English retrieval test set.
- [x] Record Recall@5, MRR and p95.
- [x] Reindex is incremental and no-op for unchanged documents.
- [x] Fallback search does not silently reduce to title/summary-only without reporting it.

Current retrieval-quality baseline: `scripts/knowledge_retrieval_quality_smoke.py`
starts an isolated SQLite-backed server, rebuilds the Markdown FTS index, runs a
five-query Chinese/English top-5 test set, and records Recall@5, MRR and local
p95 latency without printing snippets, tokens or raw content. Search now uses
heading-aware `knowledge_chunks` / `knowledge_chunk_fts` first, returns
`retrieval_granularity=heading_chunk`, and falls back to document FTS for legacy
or manually inserted private rows. Recent isolated local runs keep Recall@5
`1.0`, MRR `1.0`, and p95 under `20 ms` across 85+ indexed documents.

Required checks:

```bash
python3 scripts/agent_work_method_block_smoke.py
python3 scripts/agent_gateway_scoped_read_smoke.py
python3 scripts/knowledge_retrieval_quality_smoke.py
```

## 4. Redaction and secret safety

- [x] Replace worker marker substitution with value-aware redaction.
- [x] Share one redaction library across backend, CLI, worker and tests.
- [x] Redact before truncation.
- [x] Cover authorization headers, URL parameters, JSON fields, environment assignments and common provider formats.
- [x] Raw stdout, stderr and model responses remain outside the ledger by default.
- [x] Add mixed-case and unusual-separator regression tests.
- [ ] Add fuzz/property tests before shared/commercial deployment.

```bash
python3 scripts/redaction_policy_smoke.py
python3 scripts/security_production_readiness_smoke.py
python3 scripts/production_security_warning_ui_smoke.py
python3 scripts/pixel_office_visualizer_boundary_smoke.py
```

## 5. Authentication and deployment boundary

- [x] Loopback anonymous mode is explicitly local-development only.
- [x] Non-loopback binding requires explicit opt-in.
- [x] Non-loopback binding requires Agent Gateway authentication.
- [x] Non-loopback binding requires admin authentication.
- [x] Production/shared mode rejects `local_dev_no_token`.
- [x] Browser/local write APIs are protected in shared mode.
- [x] `security production-readiness` exposes `local_ui_write_guard`, `/workspace/agents` renders it in both Production Security and Pre-advance self-check, and operator health/action-plan/loop-self-check include it as a receipt-governed readiness signal.
- [x] `agentops doctor` blocks unsafe shared deployment.
- [x] README and runbook state the same rule.

Current v1.5 status: `startup_security_assessment` and
`scripts/startup_security_guard_smoke.py` fail closed for non-loopback or
production/shared mode without explicit opt-in plus Gateway/admin keys.
`agentops doctor` now returns exit code `2` for unsafe shared/production targets
without a Gateway token while still printing redacted JSON diagnostics.
`scripts/shared_mode_local_write_guard_smoke.py` verifies that shared/production
local UI POST/PATCH write APIs reject unauthenticated writes, accept admin-key
writes, and keep scoped Agent Gateway writes working.

Expected matrix:

```text
loopback + local development                allowed with warning
non-loopback + missing authentication       startup blocked
non-loopback + full auth + explicit opt-in  allowed
production + local_dev_no_token             blocked
```

## 6. Approval and runtime governance

### Approval

Choose one v1.5 contract.

#### Durable prepared-action contract

- [ ] Prepared action exists before approval.
- [ ] Approval binds normalized arguments, resource, policy version and action hash.
- [ ] Checkpoint exists before pause.
- [ ] Approve resumes the exact step rather than completing the run directly.
- [ ] Approval is one-time and expires.
- [ ] Duplicate decisions cannot duplicate side effects.
- [ ] Reject blocks the step and writes audit evidence.
- [ ] Non-idempotent providers use reconciliation or idempotency keys.

#### Restricted ledger/delivery contract

- [ ] Existing approval is described as ledger/delivery approval.
- [ ] UI/docs do not claim exact tool-action resume.
- [ ] Generic external side effects are denied.
- [ ] Live runtimes stay within documented capabilities and sandbox boundaries.

```bash
python3 scripts/approval_decision_side_effect_smoke.py
python3 scripts/enrollment_approval_workflow_smoke.py
python3 scripts/enrollment_credential_ui_smoke.py
python3 scripts/review_queue_smoke.py
python3 scripts/agent_gateway_review_queue_smoke.py
```

### Runtime capabilities

- [ ] Runtime execution is not always recorded as low risk.
- [x] Each adapter declares filesystem, shell, network, Git and external-write capabilities through a runtime capability manifest.
- [ ] Live execution requires compatible trust and policy decisions.
- [x] Work directory and write boundaries are explicit in the manifest/readiness payload.
- [ ] Runtime tool events are ingested when available.
- [x] Shared/commercial mode is restricted when detailed tool events are unavailable.
- [ ] Secrets are consumed inside trusted tools rather than returned to model output.

Current v1.5 hardening status: `GET /api/workers/adapter-readiness` and
`agentops worker readiness` expose `runtime-capability-manifest-v1` for mock,
Hermes and OpenClaw. Worker tool-call risk now consumes the manifest:
Hermes/OpenClaw are recorded at a medium risk floor with
`ledger_summary_only`, `restricted_until_runtime_tool_events`, and
`requires_prepared_action_for_external_write` metadata. Confirmed
customer-worker Hermes/OpenClaw tasks with explicit or obvious external-write
intent now stop before runtime invocation and create task/run/tool/prepared
action/approval/audit evidence. This is a disclosed governance boundary and a
first enforced entry gate, not full internal runtime tracing or complete
coverage for every external side-effect path.

```bash
python3 scripts/runtime_connector_trust_smoke.py
python3 scripts/worker_live_confirm_gate_smoke.py
python3 scripts/worker_adapter_readiness_smoke.py
python3 scripts/worker_adapter_retry_smoke.py
```

## 7. Workspace and Agent isolation

- [x] Replace JSON-text `LIKE` collaborator authorization for Agent Gateway task/run/artifact/approval/memory list paths.
- [x] Use exact JSON-array comparison via `agentops_json_array_contains`; normalized collaborator rows remain a later storage refactor.
- [ ] Task, run, artifact, approval, memory and review queue use the same scope service.
- [x] Knowledge search applies its intended workspace/access policy.
- [x] Add similar-ID regression with `scripts/collaborator_exact_scope_smoke.py`.
- [x] Add special-character-ID regression with `scripts/agent_gateway_special_char_scope_smoke.py`.
- [x] Scoped review queue applies scope before limit.
- [x] Scoped totals are not distorted by global truncation.

Current v1.5 hardening status: `agent_gateway_review_queue` now calls
`human_review_queue` with the bound Agent Gateway identity, so pending
approvals, memory candidates, evaluation-case candidates, and failed
evaluation-case runs apply workspace/agent visibility in SQL before the
requested `limit`. Delivery and Commander synthesis lanes are safety-filtered
with the same task/run visibility helper before the combined queue is sorted.
`scripts/agent_gateway_review_queue_smoke.py` creates 60 hidden candidates in a
different workspace and requires the visible scoped item plus scoped totals to
survive `limit=1`.
`scripts/agent_gateway_special_char_scope_smoke.py` runs against an isolated
SQLite database and verifies URL-encoded task/run/approval path ids plus
workspace, agent, and task ids containing spaces, `+`, `%`, quotes, commas, and
an encoded slash. It requires exact collaborator visibility, workspace-spoof
rejection, scoped ledger list isolation, scoped review queue visibility, and no
token-like leakage.

```bash
python3 scripts/workspace_isolation_smoke.py
python3 scripts/collaborator_exact_scope_smoke.py
python3 scripts/agent_gateway_special_char_scope_smoke.py
python3 scripts/agent_gateway_scope_matrix_smoke.py
python3 scripts/agent_gateway_scoped_read_smoke.py
python3 scripts/agent_gateway_reviewable_lists_smoke.py
python3 scripts/agent_gateway_review_queue_smoke.py
```

## 8. SQLite reliability and performance

- [x] Centralize connection initialization through `server.db()`.
- [x] Enable foreign keys.
- [x] Enable WAL.
- [x] Set a busy timeout.
- [x] Use an appropriate local synchronous mode.
- [x] Keep the verified write path short in the SQLite reliability smoke.
- [ ] Audit every long-running workflow path for model/network/subprocess calls held inside a write transaction.
- [x] Each request/worker path opens its own connection through `server.db()` in the current local architecture.
- [x] Add a schema migration version table.

Recommended local settings:

```sql
PRAGMA foreign_keys=ON;
PRAGMA journal_mode=WAL;
PRAGMA busy_timeout=5000;
PRAGMA synchronous=NORMAL;
```

Concurrency acceptance:

```text
100 concurrent reads: pass via scripts/sqlite_reliability_smoke.py
20 concurrent short writes: pass via scripts/sqlite_reliability_smoke.py
heartbeat + knowledge search + queue + approval: pass
locked/busy failures: zero
```

Required checks:

```bash
python3 scripts/sqlite_pragmas_smoke.py
python3 scripts/sqlite_reliability_smoke.py
```

## 9. UI/API responsiveness

- [x] Measure AI Employees initial request count: `scripts/ai_employees_responsiveness_smoke.py` models the `/workspace/agents` initial loader and currently measures 28 API reads split into 8 core command-center reads, 15 deferred governance reads, 4 loop-scoped deferred reads, and 1 deferred `/api/agents` read; the budget is <=32 and daemon log prefetch stays absent.
- [x] Measure time to first useful panel: `scripts/ai_employees_responsiveness_smoke.py` measures core command-center readiness as the first useful panel against a <1.5s budget, critical command-center endpoint latency against a <1s budget, and background panel completion against a <2s budget on an isolated local DB; recent runs stayed below budget, with no ledger mutation and no token leakage.
- [x] Do not fetch daemon logs before the panel is opened: AI Employees removes the initial `loadWorkerDaemonLogs` fan-out, loads only the selected adapter after the log panel is opened, and UI smoke forbids the old prefetch marker.
- [x] Make panels independently loadable: AI Employees now uses `AI_EMPLOYEES_CORE_PANEL_LOADERS`, `AI_EMPLOYEES_DEFERRED_PANEL_LOADERS`, and `AI_EMPLOYEES_SCOPED_PANEL_LOADERS` with `Promise.allSettled` plus `panelLoadState`; core command-center panels render first, deferred governance/scoped panels merge later, and one panel endpoint can become unavailable without failing the whole `/workspace/agents` page loader. Key panel headers render ready/unavailable/loading badges, local refresh controls, retry/error evidence (`attempts`, `updated_at`, `last_error`), copyable redacted panel diagnostics, and `ui.panel_diagnostics` Action Queue receipt recording so panel failures enter loop-audit/handoff evidence; repeated failed panel diagnostic receipts feed the same receipt-failure memory candidate/work-order lane as other failed recovery receipts. `scripts/ai_employees_responsiveness_smoke.py` forbids the old page-level `useLiveData` and monolithic destructured loaders, and `scripts/operator_panel_diagnostics_receipt_smoke.py` verifies the receipt plus repeated-failure memory path end to end.
- [x] Add a lightweight command-center read model or equivalent aggregation: `operator evidence-report` aggregates Agent Plan, approval, plan_evidence_manifest and ledger evidence by run.
- [x] Add run-level evidence to operator handoff: `operator handoff` now includes an `evidence_report` source and read-only work order so Hermes/OpenClaw/Codex can inherit delivery evidence gaps and commands.
- [x] Bounded advance consumes handoff evidence work: unscoped `agentops operator advance-loop` prioritizes the read-only `evidence_report` work order for blocked/attention run evidence, verifies through handoff, records action receipt/evaluation proof, feeds that receipt back into handoff/UI, skips the same evidence work order after it is verified, and then continues into the first read-only `evidence_remediation` preview while preserving the `handoff.evidence_remediation` receipt source; scoped `--loop-id` still advances that loop's gate.
- [x] Evidence remediation chain is explicit in handoff: each non-ready evidence-report run has preview, create, plan-evidence, close-gap, verify, and receipt commands; preview can be consumed by bounded advance, while create/close/confirm mutating steps remain explicit operator actions and are never auto-run by handoff/advance-loop.
- [x] Evidence remediation handoff items expose stage-level workflow state: `workflow_steps` covers preview, create task, dispatch package, plan evidence, synthesis, and close-gap, with only preview marked auto-advanceable and mutating stages marked receipt-gated explicit work. Each command-bearing stage has its own receipt readback, generated record/verify receipt commands, blocked/ready reason, prerequisite step, next safe command kind, and receipt-next command. Handoff and loop-self-check both expose `evidence_remediation_workflow` gates, while `/workspace/agents` shows ready/blocked counts plus a copy-only remediation workflow table for the leading runs.
- [x] Action Queue projects the current remediation workflow stage: `operator action-plan` now exposes `evidence_remediation_workflow` source/summary/items, including step id, mutating/confirm flags, next-safe command kind, receipt source, and verify command. `/workspace/agents` labels these stage actions so operators can continue from preview into explicit package, plan-evidence, synthesis, or close-gap work without reading raw JSON.
- [x] Operator Action Queue recovery items can record action receipts and show VERIFY commands in action-plan / loop-audit readback.
- [x] Paginate large run, tool and audit lists: `/api/runs`, `/api/tool-calls`, and `/api/audit` accept `limit`/`offset`; `include_page=true` returns an envelope with page metadata while legacy array responses remain compatible. UI ledger loaders use bounded limits by default, and `scripts/ledger_pagination_smoke.py` verifies array compatibility plus paginated metadata.
- [x] Briefly cache expensive aggregate read models: dashboard metrics plus operator action-plan, evidence-report, health, handoff, and loop-self-check use a 2s in-process read-model cache keyed by query and auth/workspace profile; responses include `read_model_cache` miss/hit/bypass proof, `refresh_cache=true` bypasses cache, Action Queue receipt/memory writes invalidate cached operator readbacks, and `scripts/read_model_cache_smoke.py` plus `scripts/operator_advance_loop_smoke.py` verify scoped-token separation, read-only ledger behavior, and write-after-receipt freshness.
- [x] One optional endpoint failure must not block the whole page: UI optional loaders return explicit `unavailable` fallback payloads, and AI Employees renders the operator evidence matrix without blocking the rest of the console.

Initial budgets:

```text
ordinary control-plane read p95     <150 ms
scoped queue/knowledge p95          <200 ms
workflow accepted latency           <300 ms
approval decision latency           <300 ms
useful command-center summary       <1 s
```

## 10. Automated CI

- [x] Add GitHub Actions.
- [ ] Require checks before merge.
- [x] Use clean temporary database/runtime directories.
- [x] Keep deterministic CI credential-free.
- [x] Keep live Hermes/OpenClaw as protected local/manual jobs.

Current automation:

```text
.github/workflows/ci.yml
backend-deterministic: py_compile, diff-check, redaction, SQLite pragmas,
startup security, production readiness, Agent Plan integrity, run-start plan
gate, exact collaborator scoping, operator task intake, operator action plan,
Gateway scope matrix, special-character scoped IDs, scoped reads,
task-claim conflict, workspace isolation, bounded operator loop advance, and
operator evidence report, and v1.5 local product acceptance against a temporary
SQLite DB.

ui-build: npm ci + npm run build under ui/start-building-app.
AI Employees optional endpoint fallback: `cd ui/start-building-app && npm run build`.
AI Employees lazy daemon logs: `python3 scripts/operator_action_queue_ui_smoke.py`.
AI Employees responsiveness baseline: `python3 scripts/ai_employees_responsiveness_smoke.py`.
Review decision local refresh: `python3 scripts/review_decision_local_refresh_smoke.py`.
Real-runtime UI confirmation: `python3 scripts/real_runtime_ui_confirm_smoke.py`.
```

The workflow intentionally keeps Hermes/OpenClaw live runtime work out of CI.
Those checks remain protected local/manual acceptance commands with explicit
confirmation and no default credentials.

Minimum jobs:

```text
backend-syntax
core-smoke
method-and-knowledge
agent-gateway-security
workspace-scope
review-queue
worker-package
ui-build
secret-scan
diff-check
```

Suggested deterministic suite:

```bash
python3 -m py_compile server.py agentops_mis_cli/*.py scripts/*.py
python3 scripts/demo_acceptance.py --start-server
python3 scripts/local_readiness_smoke.py
python3 scripts/agent_work_method_block_smoke.py
python3 scripts/agentops_cli_install_smoke.py
python3 scripts/agentops_pip_install_smoke.py
python3 scripts/agentops_status_smoke.py
python3 scripts/agentops_doctor_smoke.py
python3 scripts/agent_gateway_scope_matrix_smoke.py
python3 scripts/agent_gateway_special_char_scope_smoke.py
python3 scripts/agent_gateway_session_smoke.py
python3 scripts/workspace_isolation_smoke.py
python3 scripts/task_claim_conflict_smoke.py
python3 scripts/agent_gateway_scoped_read_smoke.py
python3 scripts/agent_gateway_reviewable_lists_smoke.py
python3 scripts/agent_gateway_review_queue_smoke.py
python3 scripts/operator_advance_loop_smoke.py
python3 scripts/redaction_policy_smoke.py
python3 scripts/security_production_readiness_smoke.py
python3 scripts/worker_adapter_retry_smoke.py
python3 scripts/worker_stuck_recovery_smoke.py
python3 scripts/workflow_job_stuck_recovery_smoke.py
python3 scripts/kb_bot_demo_smoke.py
python3 scripts/kb_bot_workflow_api_smoke.py
python3 scripts/v1_5_demo_readiness_smoke.py
python3 scripts/v1_5_local_product_acceptance.py
git diff --check
cd ui/start-building-app && npm ci && npm run build
```

Split tests into:

```text
CI-safe deterministic suite
local integration suite
live runtime suite
```

## 11. Functional release gates

### Agent Gateway

- [ ] Enrollment request/approval/issuance works.
- [ ] Raw credential is shown once.
- [ ] Database stores hashes only.
- [ ] Rotation invalidates old credential.
- [ ] Revocation cascades sessions.
- [ ] Expired credentials are rejected.
- [ ] Missing scope returns 403.
- [ ] Workspace/header/query spoofing returns 403.
- [ ] Task claim is atomic.
- [ ] Scoped lists and review queue are exact.

### Worker

- [ ] Mock one-shot and daemon pass.
- [ ] Retry/backoff pass.
- [ ] Session refresh passes.
- [ ] Stuck recovery passes.
- [ ] Adapter preflight is read-only.
- [ ] Hermes/OpenClaw require explicit confirmation.
- [ ] Blocked trust prevents live execution.
- [ ] Failure writes run/evaluation/audit evidence.
- [ ] Generic success produces a deliverable Artifact or explicitly declares none required.

### Method and knowledge

- [ ] A new Agent can find project spec, workflow and base notes.
- [ ] A plan can be created and verified.
- [ ] Plan approval is role-separated.
- [ ] Governed execution requires the verified plan.
- [ ] Retrieval references are real and visible.
- [ ] No secret values appear in indexed content.

### Customer workflow

- [ ] Synchronous and asynchronous submission work.
- [ ] Jobs can be listed and polled.
- [ ] Stuck jobs can be recovered.
- [ ] Delivery board links task/run/artifact/approval/evaluation/audit.
- [ ] Customer report excludes internal prompts and private transcripts.
- [ ] Delivery approval is not confused with tool-action execution approval.

### UI

- [x] AI Employees remains useful under partial endpoint failure: optional loaders, panel `ready/running/unavailable` states, local panel refresh, and `Promise.allSettled` contracts are guarded by `scripts/operator_action_queue_ui_smoke.py` and `scripts/ai_employees_responsiveness_smoke.py`.
- [x] Review decisions refresh only needed data: Approvals Inbox, Workspace Home, Evaluation Room, AI Employees review queue, loop record review, and enrollment approval decisions use local state updates or targeted panel refreshes instead of whole-page `refresh()`; guarded by `scripts/review_decision_local_refresh_smoke.py`.
- [x] Real-runtime controls show explicit confirmation: AI Employees and Pixel Office customer dispatch show an explicit live Hermes/OpenClaw confirmation latch; live worker, daemon, async job, Commander package and customer real-run controls are disabled until confirmed, while mock remains the safe default. Guarded by `scripts/real_runtime_ui_confirm_smoke.py`.
- [x] Production-security warnings are prominent: `/workspace/agents` renders a top-level Production Security Boundary strip before operator controls, showing readiness, local write guard, deployment mode, startup security and the copyable next check command. Guarded by `scripts/production_security_warning_ui_smoke.py`, `scripts/security_production_readiness_smoke.py`, and `scripts/operator_action_queue_ui_smoke.py`.
- [x] Issued credentials cannot be re-read: Agent Gateway enrollment list payloads expose `token_omitted:true` and never include raw token/hash fields; `/workspace/agents` displays a fresh create/issue/rotate token only inside a one-time credential card, clears the raw token after copy, clears the card on ordinary refresh/panel refresh/revoke/session actions, and provides explicit copy/clear controls. Guarded by `scripts/enrollment_credential_ui_smoke.py`.
- [x] Pixel Office remains a visualizer: `/workspace/pixel-office` is a native React/CSS MIS operating map, Star-Office stays optional legacy link only, no third-party pixel assets are imported, and customer dispatch routes through MIS workflow APIs with ledger/approval/evidence readback. Guarded by `scripts/pixel_office_visualizer_boundary_smoke.py`.
- [ ] Customer delivery is separated from internal evidence.

## 12. License and provenance

- [ ] Add root license.
- [ ] Align package metadata.
- [ ] Add third-party notices.
- [ ] Record source repository/version/license/usage.
- [ ] Record UI/icon/art provenance.
- [ ] Exclude non-commercial Pixel Office assets from commercial build.
- [ ] Generate minimal SBOM.

## 13. Clean-machine RC

```bash
python3 -m pip install .
agentops --help
agentops-worker --help
python3 server.py --reset
cd ui/start-building-app && npm ci && npm run build
```

Then run a local mock closure using a submitted and verified Agent Plan, inspect the review queue and delivery board, and record only safe IDs, hashes, statuses and summaries.

Optional live runtime checks occur only after preflight and explicit human confirmation.

## 14. Release evidence packet

- [ ] Exact RC SHA.
- [ ] CI links and status.
- [ ] Test command list and summary.
- [ ] Performance and retrieval baseline.
- [ ] Migration and rollback result.
- [ ] Security readiness and secret scan.
- [ ] License/provenance/SBOM.
- [ ] Plan, task, run, artifact and review IDs for safe closure.
- [ ] Optional protected live-runtime IDs.
- [ ] Known limitations and public-claims checklist.

Never include raw credentials, private prompts, raw model responses, customer document bodies, local databases or unsafe runtime logs.

## 15. Final decision

Allowed states:

```text
NOT_READY
READY_FOR_RC
RC_FAILED
RC_PASSED
READY_TO_MERGE
MERGED
```

`READY_TO_MERGE` requires:

```text
[ ] all blocking security/correctness gates pass
[ ] CI is green on the exact HEAD
[ ] clean-machine RC passes
[ ] migration and rollback pass
[ ] public claims match tested behavior
[ ] license and provenance are resolved
```

Current state:

```text
NOT_READY
```
