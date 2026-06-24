# Commercial Evidence Receipts

Contract: `commercial_evidence_receipts_v1`

Current status: `partial_local_receipts_not_release_complete`.

This is a hash/ref-only receipt ledger for commercial migration evidence. It
records local isolated evidence that has been run, but it does not execute those
commands and does not claim release completion. Local receipts are useful for
handoff triage; release-grade evidence still requires a clean worktree, remote
sync, exact-head CI, and all phase gates current. Gate 5 local receipt state is
`local_receipts_complete_exact_head_required`.
The release-grade flags intentionally remain `exact_head_ci_verified=false`,
`remote_sync_verified=false`, and `clean_worktree_verified=false` until final
release review for `gate_5_byoc_enterprise_deployment`.

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

Gate 5 has local receipts for:

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
