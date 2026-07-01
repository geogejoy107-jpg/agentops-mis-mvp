# Harness Engineering Control Plane Acceptance

## Purpose

This acceptance note records the local, static product slice that turns the
Harness engineering research brief into executable AgentOps MIS constraints.

## Scope

Added:

- `docs/HARNESS_ENGINEERING_CONTROL_PLANE_SPEC.md`
- `scripts/harness_engineering_control_plane_smoke.py`
- CI and release-evidence wiring for the new smoke

Not added:

- no new runtime dependency
- no Harness Open Source vendoring
- no OPA/Rego dependency
- no database migration
- no live Hermes/OpenClaw execution
- no generated export, DB, cache, `dist`, `node_modules` or env file

## Verification

Run:

```bash
python3 scripts/harness_engineering_control_plane_smoke.py
python3 scripts/open_source_mainline_governance_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
python3 scripts/secret_scan_smoke.py
python3 scripts/release_evidence_packet_smoke.py
git diff --check
```

Local result on 2026-07-01:

- `python3 scripts/harness_engineering_control_plane_smoke.py`: passed
- `python3 scripts/open_source_mainline_governance_smoke.py`: passed
- `python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py`: passed
- `python3 scripts/secret_scan_smoke.py`: passed
- `python3 scripts/release_evidence_packet_smoke.py`: passed
- `git diff --check`: passed

## Expected Evidence

- `operation=harness_engineering_control_plane_smoke`
- `ok=true`
- smoke confirms the spec, research brief, open-source boundary doc, CI wiring,
  release evidence wiring and secret-boundary checks
- release packet includes
  `python3 scripts/harness_engineering_control_plane_smoke.py`

## Product Boundary

This slice is not product-readiness proof for real Hermes/OpenClaw execution.
It is a control-plane doctrine and static gate. Live runtime dogfood remains a
separate, approval-gated execution slice.
