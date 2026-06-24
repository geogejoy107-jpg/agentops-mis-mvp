# Commercial Handoff Status

Contract: `commercial_handoff_status_v1`

Current status: `blocked_release_evidence_required`.

This is the operator-facing status surface for the commercial migration lane. It
aggregates `commercial_release_evidence_packet_v1`,
`release_evidence_packet_v1`, `release_freeze_protocol_v1`, and
`merge_readiness_status_v1`, plus `commercial_evidence_receipts_v1` and the
`commercial_current_evidence_status_v1` evidence coverage map and
`commercial_release_promotion_preflight_v1`, without running Docker, browsers,
or live agents.
Passing the default check means the handoff status is internally consistent; it
does not mean the product is release-complete.
The embedded current-evidence summary exposes `gates_with_local_receipts` and
`gates_with_release_grade_receipts` so local Gate 1-5 receipts can be visible
with `local_receipts_complete_exact_head_required` without changing
release-grade readiness. Exact-head CI and remote sync are already verified for
PR #22 head `1195c9b`; release-grade receipts, clean worktree, handoff, and
merge readiness still block commercial handoff.

Expected source statuses are `gate_enforced_not_release_complete`,
`freeze_active_not_release_complete`, and `blocked_release_evidence_required`.

Read the current handoff status:

```bash
python3 scripts/commercial_handoff_status.py
python3 scripts/commercial_release_promotion_preflight.py
python3 scripts/commercial_evidence_receipts.py
python3 scripts/commercial_current_evidence_status.py
```

Verify the status contract:

```bash
python3 scripts/commercial_handoff_status_smoke.py
python3 scripts/commercial_release_promotion_preflight_smoke.py
python3 scripts/commercial_evidence_receipts_smoke.py
python3 scripts/commercial_current_evidence_status_smoke.py
```

Strict handoff assertions must fail while the status remains blocked:

```bash
python3 scripts/commercial_handoff_status.py --require-handoff-ready
python3 scripts/commercial_release_promotion_preflight.py --require-promotion-ready
python3 scripts/commercial_handoff_status_smoke.py --require-handoff-ready
```

The status must expose `commercial_handoff_allowed`, `release_complete`,
`ready_to_merge`, `explicit_blockers`, `required_commands`, and
`phase_gate_statuses`.

Required evidence commands include:

```bash
python3 scripts/commercial_handoff_status.py
python3 scripts/commercial_handoff_status_smoke.py
python3 scripts/commercial_release_promotion_preflight.py
python3 scripts/commercial_release_promotion_preflight_smoke.py
python3 scripts/commercial_release_promotion_preflight.py --require-promotion-ready
python3 scripts/commercial_evidence_receipts.py
python3 scripts/commercial_evidence_receipts_smoke.py
python3 scripts/commercial_current_evidence_status.py
python3 scripts/commercial_current_evidence_status_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/commercial_release_evidence_packet_smoke.py
python3 scripts/release_freeze_protocol_smoke.py
python3 scripts/merge_readiness_status_smoke.py
python3 scripts/commercial_migration_readiness.py
python3 scripts/commercial_entitlements_smoke.py
python3 scripts/team_entitlement_enrollment_smoke.py
python3 scripts/enrollment_approval_workflow_smoke.py
python3 scripts/production_auth_fail_closed_smoke.py --configured-production-fixture
python3 scripts/security_production_readiness_smoke.py --configured-production-fixture
python3 scripts/agent_gateway_scope_matrix_smoke.py --isolated-fixture
python3 scripts/workspace_isolation_smoke.py --isolated-fixture
python3 scripts/workspace_rbac_governance_smoke.py --isolated-fixture
python3 scripts/workspace_memory_session_governance_smoke.py --isolated-fixture
python3 scripts/storage_boundary_sqlite_smoke.py
python3 scripts/storage_postgres_contract_smoke.py
python3 scripts/storage_postgres_container_smoke.py
python3 scripts/storage_postgres_adapter_contract_smoke.py
python3 scripts/storage_postgres_optional_adapter_smoke.py
python3 scripts/storage_postgres_boundary_parity_smoke.py
python3 scripts/storage_postgres_route_read_model_smoke.py
python3 scripts/storage_backend_selection_smoke.py
python3 scripts/storage_postgres_http_read_parity_smoke.py
python3 scripts/storage_postgres_cli_read_parity_smoke.py
python3 scripts/storage_postgres_write_helper_parity_smoke.py
python3 scripts/storage_postgres_http_write_task_smoke.py
python3 scripts/storage_postgres_cli_write_parity_smoke.py
python3 scripts/nextjs_parity_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/ui_covered_route_retirement_packet_smoke.py
python3 scripts/vite_playwright_snapshot_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
cd ui/start-building-app && npm run build
cd ui/next-app && npm run build
python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture
python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture
python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture
HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api
```

Invalid evidence includes `--skip-postgres-if-unavailable`,
`mock_only_product_claim`, `release_complete_true`, raw prompts, raw responses,
private transcripts, token values, and SQLite fallback presented as Postgres
proof.
