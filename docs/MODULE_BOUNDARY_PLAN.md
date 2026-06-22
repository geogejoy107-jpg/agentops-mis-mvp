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

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/read_model_cache_smoke.py
python3 scripts/runtime_capability_manifest_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/worker_adapter_readiness_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/runtime_connector_trust_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/agentops_worker_status_smoke.py
python3 scripts/agentops_worker_fleet_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/commander_work_package_plan_smoke.py
python3 scripts/commander_work_package_dispatch_smoke.py
```

## Next Candidate Slices

- Approval Wall prepared-action helpers.
- Operator command-center read-model aggregation.

Each candidate must be extracted in a separate, smoke-backed slice.
