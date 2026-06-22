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
- trust updates and audit/runtime event writes

Verification:

```bash
python3 scripts/module_boundary_smoke.py
python3 scripts/runtime_capability_manifest_smoke.py --base-url http://127.0.0.1:8787
python3 scripts/worker_adapter_readiness_smoke.py --base-url http://127.0.0.1:8787
```

## Next Candidate Slices

- Read-model cache helpers.
- Runtime connector trust update service.
- Worker fleet status/readiness aggregation.
- Commander work-package read models.
- Approval Wall prepared-action helpers.

Each candidate must be extracted in a separate, smoke-backed slice.
