# Release Evidence Packet

This packet defines the auditable release evidence shape for AgentOps MIS. It is
not a static generated artifact because the Exact RC SHA changes with every
commit. The authoritative packet is emitted at runtime by:

```bash
python3 scripts/release_evidence_packet_smoke.py
```

For a final RC candidate, run the stricter form:

```bash
python3 scripts/github_required_checks_smoke.py
python3 scripts/release_evidence_packet_smoke.py --require-clean --require-green-ci
python3 scripts/release_freeze_protocol_smoke.py --require-clean --require-green-ci --require-remote-checks
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

### Release Freeze And Required Checks

- Source: `docs/RELEASE_FREEZE_PROTOCOL.md`.
- Default check: `python3 scripts/release_freeze_protocol_smoke.py`.
- Strict check:
  `python3 scripts/release_freeze_protocol_smoke.py --require-clean --require-green-ci --require-remote-checks`.
- Required checks before merge are verified by
  `python3 scripts/github_required_checks_smoke.py`.
- In GitHub Actions, this smoke may report `ci_permission_limited` if the
  short-lived workflow token cannot read branch protection; final local review
  must use an authenticated `gh` session that can read the live protection rule.

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

- `python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py && git diff --check`
- `python3 scripts/release_branch_control_smoke.py`
- `python3 scripts/release_freeze_protocol_smoke.py`
- `python3 scripts/clean_machine_rc_smoke.py`
- `python3 scripts/release_evidence_packet_smoke.py`
- `python3 scripts/merge_readiness_status_smoke.py`
- `python3 scripts/v1_5_product_closure_evidence_smoke.py`
- Manual product-readiness gate, intentionally not CI-backed:
  `python3 scripts/customer_worker_real_runtime_acceptance.py --confirm-live --adapter hermes --adapter openclaw`
- `python3 scripts/customer_worker_hermes_retry_gateway_smoke.py`
- `python3 scripts/module_boundary_smoke.py`
- `python3 scripts/read_model_cache_smoke.py`
- `python3 scripts/open_source_adoption_boundary_smoke.py`
- `python3 scripts/external_connector_runtime_inventory_smoke.py`
- `python3 scripts/sqlite_concurrency_smoke.py`
- `python3 scripts/secret_scan_smoke.py`
- `python3 scripts/license_provenance_smoke.py`
- `python3 scripts/public_claims_release_gate_smoke.py`
- `python3 scripts/migration_rollback_smoke.py`
- `python3 scripts/knowledge_retrieval_quality_smoke.py`
- `python3 scripts/commander_repo_map_smoke.py`
- `python3 scripts/commander_coding_project_template_smoke.py`
- `python3 scripts/commander_coding_workspace_smoke.py`
- `python3 scripts/operator_command_center_smoke.py`
- `python3 scripts/commander_work_package_plan_smoke.py`
- `python3 scripts/commander_work_package_dispatch_smoke.py`
- `python3 scripts/local_coding_project_template_smoke.py`
- `python3 scripts/ai_employees_responsiveness_smoke.py`
- `python3 scripts/operator_action_queue_ui_smoke.py`
- `python3 scripts/operator_advance_loop_smoke.py`
- `python3 scripts/operator_loop_control_smoke.py`
- `python3 scripts/operator_loop_launch_packet_smoke.py`
- `python3 scripts/task_detail_evidence_ui_smoke.py`
- `python3 scripts/security_production_readiness_smoke.py --base-url "$AGENTOPS_BASE_URL"`
- `python3 scripts/operator_runtime_doctor_smoke.py`
- `python3 scripts/operator_execution_mode_smoke.py`
- `python3 scripts/runtime_capability_manifest_smoke.py --base-url "$AGENTOPS_BASE_URL"`
- `python3 scripts/worker_fleet_hygiene_smoke.py --base-url "$AGENTOPS_BASE_URL"`
- `python3 scripts/agent_gateway_knowledge_scope_smoke.py`
- `python3 scripts/safe_closure_evidence_packet_smoke.py`
- `python3 scripts/protected_live_runtime_ids_smoke.py`
- `cd ui/start-building-app && npm ci && npm run build`

The smoke verifies each CI command is backed by `.github/workflows/ci.yml` and
that referenced script files exist. `customer_worker_hermes_retry_gateway_smoke`
uses a deterministic loopback OpenAI-compatible gateway to prove retry metadata
is wired through the real customer-worker Hermes adapter path; it is still not
live product-readiness proof. Manual-live commands are tracked in the packet but
intentionally excluded from CI because they call real local Hermes/OpenClaw
runtimes and require explicit operator confirmation.

### Manual Live Product Evidence

CI/offline smokes prove merge hygiene and regression coverage; they do not prove
product readiness by themselves. Product-readiness, demo, dogfood, or
customer-usefulness claims require current manual live evidence when local
Hermes/OpenClaw are available and authorized:

```bash
python3 scripts/customer_worker_real_runtime_acceptance.py \
  --confirm-live \
  --adapter hermes \
  --adapter openclaw
```

The release note or handoff must cite the resulting Hermes/OpenClaw run IDs and
artifact IDs. Mock-only evidence must be described as CI/offline fallback, not
as product-level completion.

Server-backed commands, including
`python3 scripts/local_coding_project_template_smoke.py`, require a running
AgentOps MIS server selected by `AGENTOPS_BASE_URL`. The GitHub Actions backend
suite starts an isolated `127.0.0.1:8787` server with a temporary SQLite
database and live Hermes/OpenClaw/Dify/Notion disabled before running them.

### Clean-Machine RC

Checklist phrase: clean-machine RC.

`python3 scripts/clean_machine_rc_smoke.py` clones the exact current HEAD into a
temporary directory, rejects tracked runtime/generated files, uses isolated
SQLite state, verifies source-package installation including `agentops --help`
and `agentops-worker --help`, runs release gates, creates a safe closure packet
with submitted/verified Agent Plan evidence, starts a reset local server, and
checks the read-only delivery board. The UI build remains covered by the
dedicated CI `UI build` job and by the packet's canonical command manifest.

## Forbidden Evidence

Never include raw credentials, private prompts, raw model responses, customer
document bodies, local databases, private transcripts, or unsafe runtime logs in
release evidence. The packet output must stay summary-only and token-omitted.
