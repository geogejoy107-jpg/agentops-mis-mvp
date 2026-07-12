# Private Host Cold Start Acceptance

Status: deterministic gates passed; fresh live rerun required

## Problem Found by Real Dogfood

The first authenticated Private Host live attempt reached both Hermes and
OpenClaw task intake, but both returned `409 loop_supervision_blocked`. The
fresh Host had no historical closed-loop evidence, so aggregate Local Readiness
was `blocked`; that status then prevented the first run that could create the
missing evidence.

No Runtime was called in this failed attempt. The isolated Host directory and
its credentials were removed after bounded failure evidence was inspected.

## Resolution

`operator_start_check_local_readiness_gate` now distinguishes:

- malformed, missing, or unsafe Local Readiness: hard `blocked`;
- structurally valid read-only Local Readiness whose aggregate product status
  is blocked on an empty ledger: advisory `attention`;
- ready/attention product state: gate `pass`.

This does not weaken current-code matching, adapter readiness, Runtime doctor,
connector trust, explicit `confirm_run`, external-write prepared actions,
Agent Plan, knowledge retrieval, evaluation, audit, or evidence gates.

## Verification

```bash
python3 -m py_compile server.py agentops_mis_core/operator_start_check.py
python3 scripts/operator_start_check_smoke.py
python3 scripts/operator_loop_supervision_smoke.py
git diff --check
```

The deterministic smoke proves a structurally safe empty-ledger state becomes
`attention`, while malformed Local Readiness remains `blocked`. Product-level
acceptance still requires a new isolated Private Host and fresh successful
Hermes/OpenClaw evidence after this fix.
