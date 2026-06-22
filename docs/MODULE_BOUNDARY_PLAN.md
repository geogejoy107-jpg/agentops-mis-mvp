# Module Boundary Plan

## Purpose

P1-05 is a strangler-style split of oversized horizontal modules. The goal is
not a big-bang rewrite. Each slice must move one coherent policy or service
boundary out of `server.py`, preserve existing API/CLI/UI behavior, and add a
smoke that prevents the boundary from collapsing back into the monolith.

## Rules

- Keep authority objects and state transitions first-party AgentOps MIS code.
- Prefer pure policy modules before moving write-heavy route logic.
- Do not move database writes until the current route-level behavior has
  isolated smoke coverage.
- Keep public endpoints, CLI output shape, and UI contracts compatible.
- Add a module-boundary smoke before marking a split as durable.

## Current Slices

### Slice 1: Runtime Capability Manifest and Registry

Status: implemented

Boundary:

- `agentops_mis_runtime/capabilities.py`
- `agentops_mis_runtime/connectors.py`

Moved out of `server.py`:

- runtime connector adapter classification
- `runtime-capability-manifest-v1` policy shapes
- adapter-to-runtime-connector mapping
- public connector manifest row projection
- environment-derived Hermes/Agnesfallback runtime config
- runtime connector registry row construction
- runtime connector registry upsert SQL helper

Still owned by `server.py`:

- HTTP routes
- runtime health probing
- trust update route and audit/runtime event writes

### Slice 2: Runtime Connector Trust State

Status: implemented

Boundary:

- `agentops_mis_runtime/trust.py`

Moved out of `server.py`:

- trust status normalization
- trust update request shaping
- runtime connector trust read helper
- runtime connector trust state update SQL helper

Still owned by `server.py`:

- HTTP trust route
- runtime connector refresh orchestration
- runtime events
- audit-log writes

### Slice 3: Read-Model Cache

Status: implemented

Boundary:

- `agentops_mis_core/read_model_cache.py`

Moved out of `server.py`:

- read-model cache key construction
- short-TTL in-memory hit/miss/bypass behavior
- cache pruning and max-size enforcement
- cache response metadata shaping

Still owned by `server.py`:

- endpoint selection
- auth and workspace policy checks before cached producer calls
- write-route cache invalidation points
- read-model producers backed by SQLite queries

### Slice 4: Worker Fleet Read Models

Status: implemented

Boundary:

- `agentops_mis_core/worker_fleet.py`

Moved out of `server.py`:

- worker fleet health gate aggregation
- `/api/workers/status` payload shaping after server-owned row collection
- `/api/workers/fleet` lane construction, counts, safety metadata and next-action hints
- token/session omission proof for normalized local daemon, remote worker and registered worker lanes

Still owned by `server.py`:

- HTTP routes
- SQLite reads for agents, tasks, runs, runtime events, enrollments and sessions
- local worker daemon process/status discovery
- stuck task and workflow job lookup
- runtime adapter readiness and Hermes/OpenClaw/OpenClaw-bin probing
- fleet hygiene mutations, task release, enrollment revoke, runtime events and audit writes

### Slice 5: Runtime Connector Refresh Projection

Status: implemented

Boundary:

- `agentops_mis_runtime/connectors.py`

Moved out of `server.py`:

- deterministic runtime connector health snapshot to row-status projection
- Hermes default gateway availability/error projection
- Agnesfallback CLI and OpenAI-compatible API availability/error projection
- refresh health timestamp assignment for connector rows

Still owned by `server.py`:

- collecting Hermes/Agnesfallback health snapshots
- HTTP runtime connector routes
- SQLite upsert orchestration
- trust update route, runtime events and audit writes
- worker adapter readiness and live runtime gates

### Slice 6: Commander Work-Package Read Models

Status: implemented

Boundary:

- `agentops_mis_core/commander_work_packages.py`

Moved out of `server.py`:

- Commander work-package status classification
- Commander work-package recommended-action selection
- work-package readback status/project/localization/coding-evidence summaries
- read-only safety metadata and next-action aggregation for package readback

Still owned by `server.py`:

- HTTP routes
- SQLite task/run/artifact/evidence queries
- task description parsing and safe text redaction
- work-package planning, dispatch, coding workspace, evidence recording and synthesis writes

### Slice 7: Commander Project-Board Gate Aggregation

Status: implemented

Boundary:

- `agentops_mis_core/commander_work_packages.py`

Moved out of `server.py`:

- Commander project-board integration gate construction
- board status aggregation from pass/warn/fail gates
- recommended next-action merging from integration gates and local readiness

Still owned by `server.py`:

- HTTP routes
- local readiness, worker, adapter, synthesis and SQLite count producers
- recent artifact/task/run queries
- final project-board payload assembly

### Slice 8: Approval Wall Prepared-Action Helpers

Status: implemented

Boundary:

- `agentops_mis_core/approval_wall.py`

Moved out of `server.py`:

- prepared-action hash payload construction
- prepared-action action-hash verification
- prepared-action public projection with raw prompt/response/token omission
- prepared-action get response shaping
- approval-wall recommended-action selection for inspect/readback

Still owned by `server.py`:

- HTTP routes
- Agent Gateway identity, auth and workspace checks
- SQLite reads and writes for approvals, prepared actions, runs, tasks and tool calls
- exact-once prepared-action resume state transition
- runtime events, audit logs and provider side-effect evidence recording

### Slice 9: Operator Command-Center Read Model Aggregation

Status: implemented

Boundary:

- `agentops_mis_core/operator_command_center.py`

Moved out of `server.py`:

- command-center Commander coding-evidence gap aggregation
- command-center project-row aggregation across Commander packages and customer deliveries
- stale worker/task/job references for command-center readback
- command-center status aggregation from blocked runs, action-plan summary, gaps, stale refs and pending approvals

Still owned by `server.py`:

- HTTP routes
- Agent Gateway auth/workspace header adaptation
- SQLite queries for runs, approvals, tasks, deliveries and Commander packages
- stable action id generation and final next-action receipt metadata
- final command-center payload assembly

### Slice 10: Approval Wall Resume-Gate Mismatch Helpers

Status: implemented

Boundary:

- `agentops_mis_core/approval_wall.py`

Moved out of `server.py`:

- prepared-action id extraction from resume requests
- prepared-action stored-args and checkpoint parsing helpers
- common resume-gate error shaping for missing action id, missing action row,
  unapproved approval, already-consumed action, action-hash mismatch and
  request/action-type mismatch
- comparable-field mismatch aggregation shared by runtime probes, Dify upload
  and Notion export resume gates

Still owned by `server.py`:

- HTTP routes
- SQLite reads for prepared action and approval rows
- Notion snapshot-path safety check
- provider-specific creation of waiting-approval prepared actions
- exact-once prepared-action resume writes, runtime events, audit logs and
  provider side-effect evidence recording

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/read_model_cache_smoke.py
python3 scripts/runtime_capability_manifest_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/worker_adapter_readiness_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/runtime_connector_trust_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/agentops_worker_status_smoke.py
python3 scripts/agentops_worker_fleet_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/prepared_action_approval_wall_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/commander_work_package_plan_smoke.py
python3 scripts/commander_work_package_dispatch_smoke.py
python3 scripts/operator_command_center_smoke.py
```

### Slice 11: Runtime Prepared-Action Response Helpers

Status: implemented

Boundary:

- `agentops_mis_core/approval_wall.py`

Moved out of `server.py`:

- shared waiting-approval response shaping for prepared actions
- Approval Wall approval/action id extraction for response payloads
- prepared-action hash exposure for waiting responses
- next-action construction for inspect, approve and exact resume instructions
- token-omission proof on prepared-action waiting responses
- runtime probe, Dify upload, Notion export and customer-worker external-write
  response assembly now reuse the shared helper

Still owned by `server.py`:

- HTTP routes
- provider-specific prepared-action creation
- SQLite task/run/tool-call writes
- runtime events, audit logs and commits
- Dify/Notion/runtime resume-gate reads
- exact-once prepared-action resume writes and provider side-effect evidence

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/prepared_action_approval_wall_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/runtime_probe_prepared_action_gate_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/dify_upload_prepared_action_gate_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/notion_export_prepared_action_gate_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/customer_worker_external_write_gate_smoke.py
```

### Slice 12: Prepared-Action Route and Blocked Response Helpers

Status: implemented

Boundary:

- `agentops_mis_core/approval_wall.py`

Moved out of `server.py`:

- shared prepared-action blocked/error response shaping
- gate-error to `reason` projection for blocked responses
- consistent `status=blocked` and `token_omitted` proof for blocked responses
- route-level prepared-action resume not-found, approval-required, consumed and
  hash-mismatch response shaping
- route-level prepared-action resume success response shaping with
  `execute_once` and hash-verification proof
- runtime probe blocked payload now wraps the shared blocked-response helper
- Dify upload and Notion export prepared-action blocked responses now reuse the
  shared helper while keeping route-specific base fields

Still owned by `server.py`:

- HTTP routes
- provider-specific dry-run plans and response base fields
- runtime events, audit logs and commits for blocked routes
- SQLite reads for prepared action and approval rows
- exact-once prepared-action resume writes and provider side-effect evidence
- hash-mismatch audit writes before returning route-level blocked responses

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/prepared_action_approval_wall_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/runtime_probe_prepared_action_gate_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/dify_upload_prepared_action_gate_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/notion_export_prepared_action_gate_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 13: Prepared-Action Provider Result Reconciliation Helpers

Status: implemented

Boundary:

- `agentops_mis_core/approval_wall.py`

Moved out of `server.py`:

- shared provider-side prepared-action resume request shaping
- shared provider result fields for `approval_id`, public prepared action,
  resume status and token-omission proof
- OpenClaw, Agnesfallback CLI/API, Hermes default run-task, Dify upload and
  Notion export provider completion responses now use the shared helper

Still owned by `server.py`:

- provider execution and network/process calls
- provider-specific side-effect id derivation
- runtime events, audit logs, evaluations and commits
- exact-once prepared-action resume invocation
- provider-specific response base fields and delivery/sync evidence

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/runtime_probe_prepared_action_gate_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/dify_upload_prepared_action_gate_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/notion_export_prepared_action_gate_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/prepared_action_approval_wall_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 14: Prepared-Action Route Access/Error Helpers

Status: implemented

Boundary:

- `agentops_mis_core/approval_wall.py`

Moved out of `server.py`:

- prepared-action get-route not-found response shaping
- prepared-action bound-agent inspect-forbidden response shaping
- prepared-action resume-forbidden response shaping
- prepared-action route workspace-mismatch response shaping
- unified prepared-action route access/error branch selection for inspect and
  resume paths
- route access/error response token-omission proof for these cases

Still owned by `server.py`:

- HTTP routes
- Agent Gateway identity resolution
- bound-token detection
- workspace and agent identity inputs used by the route access helper
- SQLite reads for prepared action and approval rows
- exact-once prepared-action resume writes and provider side-effect evidence

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/prepared_action_approval_wall_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 15: Prepared-Action Prepare Response Helpers

Status: implemented

Boundary:

- `agentops_mis_core/approval_wall.py`

Moved out of `server.py`:

- tool-call `prepare_action=true` response `approval_wall` projection
- prepared-action prepare `next_action` construction for inspect, approve and
  exact resume
- token-omission proof on the prepared-action prepare response fields

Still owned by `server.py`:

- HTTP routes
- tool-call validation, risk classification and row writes
- prepared-action creation orchestration
- runtime events, audit logs and commits
- exact-once prepared-action resume writes and provider side-effect evidence

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/prepared_action_approval_wall_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/high_risk_toolcall_prepared_action_gate_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 16: Prepared-Action Decision Projection Helper

Status: implemented

Boundary:

- `agentops_mis_core/approval_wall.py`

Moved out of `server.py`:

- prepared-action decision response projection
- `resume_required` decision flag for approved prepared actions
- public prepared-action projection and token-omission proof on prepared-action
  decision responses

Still owned by `server.py`:

- HTTP routes
- approval decision state transitions
- prepared-action status updates
- linked tool/run/task state updates
- runtime events, audit logs and commits
- hash-mismatch audit writes before blocked approval responses

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/prepared_action_approval_wall_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/approval_decision_side_effect_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 17: High-Risk Tool-Call Required Response Helper

Status: implemented

Boundary:

- `agentops_mis_core/approval_wall.py`

Moved out of `server.py`:

- high-risk external side-effect tool-call 428 response projection
- `prepare_action=true` remediation guidance
- token-omission proof on the blocked response

Still owned by `server.py`:

- HTTP routes
- run access checks
- tool-call validation and risk classification
- external side-effect intent detection
- runtime events, audit logs and commits
- prepared-action creation orchestration when `prepare_action=true`

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/high_risk_toolcall_prepared_action_gate_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 18: Agent Plan Approval Decision Response Helper

Status: implemented

Boundary:

- `agentops_mis_core/agent_plans.py`

Moved out of `server.py`:

- Agent Plan approval decision response projection
- Agent Plan verification result hash exposure on approval responses
- token-omission proof on Agent Plan approval decision responses

Still owned by `server.py`:

- HTTP routes
- approval decision state transitions
- Agent Plan verification and status transitions
- approval audit writes and commits
- task/run execution gates that consume Agent Plan approval state

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/agent_plan_integrity_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 19: Agent Plan Create And Role-Gate Response Helpers

Status: implemented

Boundary:

- `agentops_mis_core/agent_plans.py`

Moved out of `server.py`:

- approval-required Agent Plan missing-anchor response projection
- agent-created invalid initial status response projection
- bound Agent Gateway token/session approval-forbidden response projection
- token-omission proof on Agent Plan role-gate responses

Still owned by `server.py`:

- HTTP routes
- task/run anchor lookup
- Agent Plan creation, verification and state transitions
- scoped auth, bound-token detection and role resolution
- approval rows, runtime events, audit logs and commits

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/agent_plan_integrity_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 20: Agent Plan Contract And Hash Helpers

Status: implemented

Boundary:

- `agentops_mis_core/agent_plans.py`

Moved out of `server.py`:

- Agent Plan JSON-list row parsing helper
- Agent Plan row-field fallback helper
- immutable Agent Plan contract projection
- Agent Plan contract hash
- Agent Plan verification result hash

Still owned by `server.py`:

- HTTP routes
- repository path/reference resolution
- memory/base/spec authority checks
- Agent Plan verification decisions and persistence
- approval rows, runtime events, audit logs and commits
- run-start task/agent/status execution gates

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/agent_plan_integrity_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/run_start_plan_gate_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 21: Agent Plan Path Scope Helpers

Status: implemented

Boundary:

- `agentops_mis_core/agent_plans.py`

Moved out of `server.py`:

- Agent Plan safe relative path check
- Agent Plan repository-contained path resolver
- Agent Plan referenced-spec authority projection
- Agent Plan proposed-file scope projection

Still owned by `server.py`:

- HTTP routes
- root path selection for this deployment
- database-backed memory authority checks
- database-backed base authority checks
- Agent Plan verification decisions and persistence
- approval rows, runtime events, audit logs and commits

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/agent_plan_integrity_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 22: Agent Plan Verification Result Builder

Status: implemented

Boundary:

- `agentops_mis_core/agent_plans.py`

Moved out of `server.py`:

- Agent Plan verification check list assembly
- Agent Plan failed-check collection
- Agent Plan verification summary projection
- Agent Plan verification token-omission proof

Still owned by `server.py`:

- HTTP routes
- root path selection for this deployment
- database-backed memory authority checks
- database-backed base authority checks
- Agent Plan verification persistence
- approval rows, runtime events, audit logs and commits

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/agent_plan_integrity_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/run_start_plan_gate_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 23: Agent Plan Pending Approval Projection

Status: implemented

Boundary:

- `agentops_mis_core/agent_plans.py`

Moved out of `server.py`:

- Agent Plan pending approval row projection
- Approval reason text derived from plan id, risk and plan hash prefix
- Pending decision defaults and timestamp field layout

Still owned by `server.py`:

- HTTP routes
- stable approval id generation
- created/expires timestamp generation
- governance anchor run creation
- approval row insertion
- runtime events, audit logs and commits

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/agent_plan_integrity_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 24: Agent Plan Transition Error Projections

Status: implemented

Boundary:

- `agentops_mis_core/agent_plans.py`

Moved out of `server.py`:

- Agent Plan not-transitionable response projection
- Agent Plan not-approvable response projection
- Agent Plan verification-failed response projection
- Token-omission proof for those transition errors

Still owned by `server.py`:

- HTTP routes
- transition actor resolution
- workspace authorization
- SQLite reads and writes
- verification persistence
- approval row updates
- runtime events, audit logs and commits

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/agent_plan_integrity_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 25: Agent Plan Approval Run Projection

Status: implemented

Boundary:

- `agentops_mis_core/agent_plans.py`

Moved out of `server.py`:

- Agent Plan governance anchor run row projection
- Approval-run ledger defaults for runtime/status/model/token/cost/error fields
- Agent Plan, plan hash, trace and delegation linkage fields

Still owned by `server.py`:

- HTTP routes
- stable run, trace and delegation id generation
- created timestamp generation
- existing-run lookup
- `upsert_run` orchestration
- approval row insertion
- runtime events, audit logs and commits

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/agent_plan_integrity_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/run_start_plan_gate_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 26: Agent Plan Run-Start Gate Responses

Status: implemented

Boundary:

- `agentops_mis_core/agent_plans.py`

Moved out of `server.py`:

- Agent Plan required response for run start
- Agent Plan task/agent mismatch response projections
- Agent Plan not-executable response projection
- Agent Plan approval-required response projection
- Agent Plan hash-mismatch response projection
- Run-start verification-failed response now uses the shared Agent Plan
  verification-failed helper

Still owned by `server.py`:

- HTTP routes
- requested/default Agent Plan lookup
- workspace authorization
- task and agent matching checks
- approval row lookup
- hash recomputation and plan verification
- verification persistence
- run insertion, runtime events, audit logs and commits

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/agent_plan_integrity_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/run_start_plan_gate_smoke.py --base-url http://127.0.0.1:8787
```

### Slice 27: Run-Start Rebind Response Projection

Status: implemented

Boundary:

- `agentops_mis_core/agent_plans.py`

Moved out of `server.py`:

- Run-start rebind-forbidden response projection
- Existing/requested Agent Plan id and plan hash readback fields
- Rebind mismatch list and token-omission proof

Still owned by `server.py`:

- HTTP routes
- existing run lookup
- expected/actual binding comparison
- mismatch calculation
- rebind-blocked audit writes
- run insertion, runtime events, audit logs and commits

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/run_start_plan_gate_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/agent_plan_integrity_smoke.py --base-url http://127.0.0.1:8787
```

## Next Candidate Slices

- Continue P1-05 with small smoke-backed strangler slices only; prefer pure
  helper extraction before moving stateful route orchestration.

Each candidate must be extracted in a separate, smoke-backed slice.
