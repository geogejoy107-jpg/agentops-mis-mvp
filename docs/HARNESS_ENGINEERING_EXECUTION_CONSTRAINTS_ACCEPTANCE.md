# Harness Engineering Execution Constraints Acceptance

## Purpose

This acceptance note records the product-safety slice that turns Harness
engineering research into concrete execution constraints for AgentOps MIS
work packets, gate chains, policy-style decisions, real-runtime proof and async
lane management.

## Scope

Added:

- `docs/HARNESS_ENGINEERING_EXECUTION_CONSTRAINTS.md`
- `scripts/harness_engineering_execution_constraints_smoke.py`
- CI and release-evidence wiring for the new smoke

Not added:

- no Harness Open Source vendoring
- no OPA/Rego dependency
- no backend route
- no UI feature
- no database migration
- no live Hermes/OpenClaw execution
- no generated exports, DB, cache, `dist`, `node_modules` or env file

## Verification

Run:

```bash
python3 scripts/harness_engineering_execution_constraints_smoke.py
python3 scripts/harness_engineering_control_plane_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/secret_scan_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
git diff --check
```

## Expected Evidence

- `operation=harness_engineering_execution_constraints_smoke`
- `ok=true`
- work packet fields are checked
- READ/PLAN/RETRIEVE/COMPARE/EXECUTE/VERIFY/RECORD gate chain is checked
- real-runtime proof and mock-evidence claim limits are checked
- CI and release-evidence wiring are checked

## Known Limits

This slice is static/product-contract evidence. It does not prove a fresh live
Hermes/OpenClaw task. Live dogfood remains a separate, explicit confirmation
slice.
