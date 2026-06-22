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

- [ ] Agent-created plans can only be `draft` or `submitted`.
- [ ] Human/admin/policy identity alone can approve or reject a plan.
- [ ] High/critical plans create or reference a real approval object.
- [ ] Plan transitions are append-only and audited.
- [ ] Plan has an immutable hash/version.
- [ ] Verification result has a hash and timestamp.
- [ ] Every referenced spec exists and is readable.
- [ ] Every referenced base exists.
- [ ] Every referenced memory exists, is visible and has an allowed review status.
- [ ] Proposed files stay inside the allowed workspace/repository.
- [ ] Real run links an `agent_plan_id`.
- [ ] Run Agent/task/workspace match the plan.
- [ ] Superseded or changed plans cannot authorize execution.
- [ ] Delivery gate compares execution evidence with the declared plan.

Required checks:

```bash
python3 scripts/agent_work_method_block_smoke.py
python3 scripts/agentops_workflow_run_task_smoke.py
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
- [ ] Add heading-aware chunks rather than only full-document rows.
- [ ] Add a Chinese/English retrieval test set.
- [ ] Record Recall@5, MRR and p95.
- [x] Reindex is incremental and no-op for unchanged documents.
- [x] Fallback search does not silently reduce to title/summary-only without reporting it.

Required checks:

```bash
python3 scripts/agent_work_method_block_smoke.py
python3 scripts/agent_gateway_scoped_read_smoke.py
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
```

## 5. Authentication and deployment boundary

- [ ] Loopback anonymous mode is explicitly local-development only.
- [ ] Non-loopback binding requires explicit opt-in.
- [ ] Non-loopback binding requires Agent Gateway authentication.
- [ ] Non-loopback binding requires admin authentication.
- [ ] Production/shared mode rejects `local_dev_no_token`.
- [ ] Browser/local write APIs are protected in shared mode.
- [ ] `agentops doctor` blocks unsafe shared deployment.
- [ ] README and runbook state the same rule.

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
- [ ] Knowledge search applies its intended workspace/access policy.
- [x] Add similar-ID regression with `scripts/collaborator_exact_scope_smoke.py`.
- [ ] Add special-character-ID regression.
- [ ] Scoped review queue applies scope before limit.
- [ ] Scoped totals are not distorted by global truncation.

```bash
python3 scripts/workspace_isolation_smoke.py
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

- [ ] Measure AI Employees initial request count.
- [ ] Measure time to first useful panel.
- [ ] Do not fetch daemon logs before the panel is opened.
- [ ] Make panels independently loadable.
- [ ] Add a lightweight command-center read model or equivalent aggregation.
- [x] Operator Action Queue recovery items can record action receipts and show VERIFY commands in action-plan / loop-audit readback.
- [ ] Paginate large run, tool and audit lists.
- [ ] Briefly cache expensive aggregate read models.
- [ ] One optional endpoint failure must not block the whole page.

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
Gateway scope matrix, scoped reads, task-claim conflict, workspace isolation,
and v1.5 local product acceptance against a temporary SQLite DB.

ui-build: npm ci + npm run build under ui/start-building-app.
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
python3 scripts/agent_gateway_session_smoke.py
python3 scripts/workspace_isolation_smoke.py
python3 scripts/task_claim_conflict_smoke.py
python3 scripts/agent_gateway_scoped_read_smoke.py
python3 scripts/agent_gateway_reviewable_lists_smoke.py
python3 scripts/agent_gateway_review_queue_smoke.py
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

- [ ] AI Employees remains useful under partial endpoint failure.
- [ ] Review decisions refresh only needed data.
- [ ] Real-runtime controls show explicit confirmation.
- [ ] Production-security warnings are prominent.
- [ ] Issued credentials cannot be re-read.
- [ ] Pixel Office remains a visualizer.
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
