# Work Delivery Graph Readback Acceptance

## Purpose

This slice adds a Harness-style, read-only work delivery graph without changing
the existing run delegation graph.

The new graph exposes one run's MIS authority chain:

```text
workspace -> task -> agent_plan -> run
run -> tool_calls/runtime_events/evaluations/artifacts/audit_logs
plan_evidence_manifest -> run
```

## Added Surface

- `GET /api/runs/:id/evidence-graph`
- `GET /api/agent-gateway/runs/:id/evidence-graph`
- `agentops run evidence-graph --run-id <run_id>`
- `scripts/work_delivery_graph_readback_smoke.py`

The existing `GET /api/runs/:id/graph`,
`GET /api/agent-gateway/runs/:id/graph`, and
`agentops run graph --run-id <run_id>` remain delegation-only.

## Verification

```bash
python3 scripts/work_delivery_graph_readback_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
python3 scripts/secret_scan_smoke.py
python3 scripts/release_evidence_packet_smoke.py
git diff --check
```

Local result on 2026-07-01:

- `python3 scripts/work_delivery_graph_readback_smoke.py`: passed
- `python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py`: passed
- `python3 scripts/secret_scan_smoke.py`: passed
- `python3 scripts/release_evidence_packet_smoke.py`: passed
- `git diff --check`: passed

## Expected Evidence

- `operation=work_delivery_graph_readback_smoke`
- `work_delivery_graph_v1`
- evidence counts for tool calls, runtime events, evaluations, artifacts,
  audit logs and plan evidence manifests
- graph hash present
- legacy `run graph` stays delegation-only
- isolated temp SQLite DB
- no live Hermes/OpenClaw execution
- token, raw prompt and raw response omitted

## Boundary

This is a read model over existing MIS ledgers. It does not create a second
authority store, execute runtime adapters, mutate ledgers during readback, or
store raw prompts/responses/credentials.
