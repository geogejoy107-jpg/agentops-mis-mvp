# Release Evidence Packet

This packet defines the auditable release evidence shape for AgentOps MIS. It is
not a static generated artifact because the Exact RC SHA changes with every
commit. The authoritative packet is emitted at runtime by:

```bash
python3 scripts/release_evidence_packet_smoke.py
```

For a final RC candidate, run the stricter form:

```bash
python3 scripts/release_evidence_packet_smoke.py --require-clean --require-green-ci
python3 scripts/merge_readiness_status_smoke.py --require-ready-to-merge
```

## Required Evidence

### Exact RC SHA

- Source: `git rev-parse HEAD`.
- The packet records the current branch, upstream ahead/behind counts and dirty
  working-tree entry count.
- The SHA must not be hand-copied into a tracked document as the release source
  of truth.

### CI Links and Status

- Checklist phrase: CI links and status.
- In GitHub Actions, the packet derives the run URL from `GITHUB_SERVER_URL`,
  `GITHUB_REPOSITORY` and `GITHUB_RUN_ID`.
- Outside CI, the packet may use `gh run list` to find a run for the current
  head SHA.
- If no current-head run is available, the packet must say so and keep the
  release in local MVP / NOT_READY posture.
- READY evidence requires current-head CI with status `completed` and conclusion
  `success`.

### Merge Readiness State

- Source: `docs/V1_5_MERGE_READINESS_CHECKLIST.md`.
- Default check: `python3 scripts/merge_readiness_status_smoke.py`.
- Strict check: `python3 scripts/merge_readiness_status_smoke.py --require-ready-to-merge`.
- The default check may pass while the branch is still `NOT_READY`; it proves
  that the checklist is honest, the final state matches the header state, and
  remaining blockers are explicit.
- The strict check must fail until the checklist is advanced to
  `READY_TO_MERGE`, the working tree is clean, upstream is synchronized, the
  exact HEAD has green CI, and no unchecked blocker remains.

### Test Command List and Summary

Checklist phrase: Test command list and summary.

The packet includes the canonical command manifest used for release review:

- `python3 -m py_compile server.py agentops_mis_cli/*.py scripts/*.py && git diff --check`
- `python3 scripts/release_branch_control_smoke.py`
- `python3 scripts/release_evidence_packet_smoke.py`
- `python3 scripts/merge_readiness_status_smoke.py`
- `python3 scripts/secret_scan_smoke.py`
- `python3 scripts/license_provenance_smoke.py`
- `python3 scripts/public_claims_release_gate_smoke.py`
- `python3 scripts/migration_rollback_smoke.py`
- `python3 scripts/knowledge_retrieval_quality_smoke.py`
- `python3 scripts/ai_employees_responsiveness_smoke.py`
- `python3 scripts/security_production_readiness_smoke.py --base-url "$AGENTOPS_BASE_URL"`
- `python3 scripts/safe_closure_evidence_packet_smoke.py`
- `python3 scripts/protected_live_runtime_ids_smoke.py`
- `cd ui/start-building-app && npm ci && npm run build`

The smoke verifies each command is backed by `.github/workflows/ci.yml` and that
referenced script files exist.

## Forbidden Evidence

Never include raw credentials, private prompts, raw model responses, customer
document bodies, local databases, private transcripts, or unsafe runtime logs in
release evidence. The packet output must stay summary-only and token-omitted.
