# Run Ledger Evidence Affordance Acceptance

## Purpose

The Run Ledger is the operator's list view for recent agent execution. After
the work-delivery evidence graph landed on Run Detail, the list view also needs
a low-cost way to show which runs are ready for evidence review and open the
graph directly.

## Scope

This slice adds an `Evidence` / `证据` column to `/admin/runs`.

Each row now shows:

- evidence posture from existing run metadata;
- live/mock runtime posture;
- approval-wall attention when `approval_required` is true;
- failure review state for failed, error, blocked or timeout runs;
- a direct link to `/admin/runs/:id#work-delivery-graph`.

The Run Detail work-delivery graph card now has the stable
`#work-delivery-graph` anchor.

## Safety Boundary

- No new backend route is added.
- Run Ledger does not call `/api/runs/:id/evidence-graph` per row.
- No live runtime execution is triggered.
- No ledger mutation is performed.
- No raw prompt, raw response, token, credential, DB or generated artifact is
  committed.

## Verification

Run from the repository root:

```bash
python3 scripts/run_ledger_evidence_ui_smoke.py
python3 scripts/run_detail_evidence_ui_smoke.py
cd ui/start-building-app && npm run build
python3 scripts/secret_scan_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
git diff --check
```

## Known Limits

This is a list-view affordance, not a full graph preview. The authoritative
graph readback still lives on Run Detail and the `agentops run evidence-graph`
CLI/API path.
