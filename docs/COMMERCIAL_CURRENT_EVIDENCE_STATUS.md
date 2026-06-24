# Commercial Current Evidence Status

Contract: `commercial_current_evidence_status_v1`

Current status: `current_evidence_required`.

This packet is the CI-safe evidence coverage layer under
`commercial_handoff_status_v1`. It reads `commercial_evidence_receipts_v1`,
the commercial release packet,
release entry point, freeze protocol, and merge-readiness status:
`commercial_release_evidence_packet_v1`, `release_evidence_packet_v1`,
`release_freeze_protocol_v1`, and `merge_readiness_status_v1`. It exposes
`phase_gate_evidence_statuses`, `evidence_current`,
`local_receipt_current`, `gates_requiring_current_evidence`,
`gates_with_local_receipts`, `gates_with_release_grade_receipts`, and
`required_commands` so operators can see which phase gates still require
release-grade current evidence. Passing this check means the evidence map is
internally consistent; it does not mean the commercial release is ready.

Read the current evidence coverage:

```bash
python3 scripts/commercial_current_evidence_status.py
python3 scripts/commercial_evidence_receipts.py
```

Verify the evidence status contract:

```bash
python3 scripts/commercial_current_evidence_status_smoke.py
python3 scripts/commercial_evidence_receipts_smoke.py
```

Strict current-evidence assertions must fail while any gate still has
`evidence_current=false`:

```bash
python3 scripts/commercial_current_evidence_status.py --require-current-evidence
python3 scripts/commercial_current_evidence_status_smoke.py --require-current-evidence
```

The status intentionally does not execute Docker, browser, Postgres, or live
Hermes/OpenClaw checks. It names those required commands so the handoff status
can show the operator exactly what still needs fresh evidence. Gates 1-5 can
show `local_receipt_current=true` and
`receipt_state=local_receipts_complete_exact_head_required` while
`release_grade_current=false`; exact-head CI, remote sync, and clean worktree
remain release blockers.

Required heavy/live evidence remains:

```bash
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
