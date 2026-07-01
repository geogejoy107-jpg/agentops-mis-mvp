# Work Delivery Graph UI Acceptance

## Purpose

Run Detail should show the work-delivery evidence graph that is already exposed
through the AgentOps MIS API and CLI. This makes a completed worker run easier
to review from the human workspace without changing runtime execution, ledger
authority or approval semantics.

## Scope

This slice adds a read-only Run Detail panel backed by:

- `GET /api/runs/:id/evidence-graph`
- `agentops run evidence-graph --run-id <run_id>`

The panel displays:

- graph availability;
- graph hash;
- node and edge counts;
- plan and plan-evidence references;
- ledger evidence counts for tool calls, runtime events, evaluations,
  approvals, artifacts, memories, audit logs and plan evidence manifests;
- safety readback for read-only and token omission.

## Safety Boundary

- No live Hermes/OpenClaw execution is triggered by the page.
- No ledger mutation is performed by the page.
- Raw prompts, raw responses, raw content, credentials and token values remain
  omitted.
- Existing delegation graph behavior is unchanged.

## Verification

Run from the repository root:

```bash
python3 scripts/run_detail_evidence_ui_smoke.py
cd ui/start-building-app && npm run build
python3 scripts/secret_scan_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
git diff --check
```

The deterministic smoke verifies that:

- Run Detail loads `loadRunEvidenceGraph`;
- the panel has `data-testid="run-detail-work-delivery-graph"`;
- the UI renders graph hash, evidence counts, runtime events, plan evidence
  manifests, safety and authority markers;
- the API loader has an unavailable fallback for stale local servers.

## Known Limits

- This is a human review panel, not a new graph database.
- The authoritative data still comes from MIS ledger tables.
- The UI does not visualize node layout yet; it shows compact counts and
  stable hashes for demo and operator review.
