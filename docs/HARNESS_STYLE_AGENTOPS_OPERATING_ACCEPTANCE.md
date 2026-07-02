# Harness-Style AgentOps Operating Acceptance

## Scope

This acceptance record covers the Harness-style AgentOps operating spec slice.
It is a docs-and-static-gate change only: no backend route, UI feature,
runtime execution, DB read/write, credential ingest, generated export, or
third-party asset import is part of this slice.

## Build And Verification Commands

Commands run locally from the repository root:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/harness_style_agentops_operating_spec_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/harness_engineering_control_plane_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/harness_engineering_execution_constraints_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/release_evidence_packet_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile scripts/harness_style_agentops_operating_spec_smoke.py scripts/release_evidence_packet_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/secret_scan_smoke.py
git diff --check
```

## Result

All commands above passed locally before this acceptance record was added.

The release evidence packet includes
`python3 scripts/harness_style_agentops_operating_spec_smoke.py`, so future CI
and release review will continue to check the operating spec boundary.

## Acceptance Checklist

- Harness Worker Agents, MCP, Policy As Code, IDP, Scorecards and autonomous
  worker-agent patterns are summarized as operating constraints.
- AgentOps MIS remains the authority ledger; Harness-like tools are references
  or adapters only.
- Solo local company, dogfood engineering and remote worker modes are covered.
- Async commander lane fields are explicit and machine-readable enough to
  become a future API packet.
- Real-runtime proof remains preferred for product-readiness claims; mock/CI
  evidence must be labeled as fallback.
- Browser UI is for humans; agents use CLI/API/MCP surfaces.
- Pixel Office is treated as a visual read model, not a second task ledger.
- No DB, `.env`, token, cache, `node_modules`, `dist`, generated export, raw
  prompt or raw response is committed.

## Known Limitations

- This slice does not add the lane packet endpoint yet.
- This slice does not run Hermes/OpenClaw live dogfood; it only defines the
  operating rules for that next implementation.
- This slice does not add remote worker revocation or heartbeat timeout UI.

## Next Slice

Add a machine-readable commander lane packet endpoint and use it as the input
for one real Hermes/OpenClaw dogfood task, with run/evidence/scorecard writeback
recorded through AgentOps MIS.
