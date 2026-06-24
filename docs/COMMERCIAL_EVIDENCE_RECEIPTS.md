# Commercial Evidence Receipts

Contract: `commercial_evidence_receipts_v1`

Current status: `partial_local_receipts_not_release_complete`.

This is a hash/ref-only receipt ledger for commercial migration evidence. It
records local isolated evidence that has been run, but it does not execute those
commands and does not claim release completion. Local receipts are useful for
handoff triage; release-grade evidence still requires a clean worktree, remote
sync, exact-head CI, and all phase gates current. Gates 1-5 now have local
receipt state `local_receipts_complete_exact_head_required`.
The release-grade flags intentionally remain `exact_head_ci_verified=false`,
`remote_sync_verified=false`, and `clean_worktree_verified=false` until final
release review.

Read receipts:

```bash
python3 scripts/commercial_evidence_receipts.py
```

Verify the receipt contract:

```bash
python3 scripts/commercial_evidence_receipts_smoke.py
```

Strict release-grade assertions must fail while receipts remain local-only:

```bash
python3 scripts/commercial_evidence_receipts.py --require-release-grade
python3 scripts/commercial_evidence_receipts_smoke.py --require-release-grade
```

Gate 1 `gate_1_product_packaging_and_entitlement` has local receipts for:

```bash
python3 scripts/commercial_entitlements_smoke.py
python3 scripts/team_entitlement_enrollment_smoke.py
python3 scripts/enrollment_approval_workflow_smoke.py
```

Gate 2 `gate_2_production_safety_baseline` has local receipts for:

```bash
python3 scripts/production_auth_fail_closed_smoke.py --configured-production-fixture
python3 scripts/security_production_readiness_smoke.py --configured-production-fixture
python3 scripts/agent_gateway_scope_matrix_smoke.py --isolated-fixture
python3 scripts/workspace_isolation_smoke.py --isolated-fixture
python3 scripts/workspace_rbac_governance_smoke.py --isolated-fixture
python3 scripts/workspace_memory_session_governance_smoke.py --isolated-fixture
```

Gate 3 `gate_3_storage_boundary_before_postgres` has local receipts for:

```bash
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
```

Gate 4 `gate_4_ui_api_parity_before_nextjs` has local receipts for:

```bash
python3 scripts/nextjs_parity_smoke.py
python3 scripts/ui_api_parity_matrix_smoke.py
python3 scripts/ui_covered_route_retirement_packet_smoke.py
python3 scripts/vite_playwright_snapshot_smoke.py
python3 scripts/nextjs_playwright_snapshot_smoke.py
cd ui/start-building-app && npm run build
cd ui/next-app && npm run build
```

Gate 5 `gate_5_byoc_enterprise_deployment` has local receipts for:

```bash
python3 scripts/audit_retention_policy_smoke.py
python3 scripts/audit_retention_controls_smoke.py --configured-fixture
python3 scripts/deployment_readiness_smoke.py --configured-retention-fixture --configured-enterprise-fixture
python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture
python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture
python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture
HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api
```

The receipts must remain free of raw prompts, raw responses, private
transcripts, token values, local databases, generated artifacts, secrets, and
`mock_only_product_claim` evidence.
