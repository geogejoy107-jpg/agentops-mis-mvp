# Commercial Release-Grade Receipt Plan

Contract: `commercial_release_grade_receipt_plan_v1`

Current status: `blocked_receipt_promotion_preview`.

This is the preview layer after `commercial_release_promotion_packet_v1`. It
shows which Gate 1-5 receipts are still stale, which commands must be rerun on
the current head, and which global release invariants still block release-grade
promotion.

Default mode is offline, read-only, and CI-safe:

```bash
python3 scripts/commercial_release_grade_receipt_plan.py
```

Add current-head GitHub Actions evidence:

```bash
python3 scripts/commercial_release_grade_receipt_plan.py --include-external-ci-evidence
```

Add a fresh real Hermes/OpenClaw runtime acceptance JSON:

```bash
HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api > /tmp/agentops-mis-runtime-acceptance.json
python3 scripts/commercial_release_grade_receipt_plan.py --include-external-ci-evidence --runtime-acceptance-json /tmp/agentops-mis-runtime-acceptance.json --require-current-runtime-evidence
```

Strict plan readiness must fail until all global invariants and per-gate
receipt freshness requirements are true:

```bash
python3 scripts/commercial_release_grade_receipt_plan.py --include-external-ci-evidence --runtime-acceptance-json /tmp/agentops-mis-runtime-acceptance.json --require-current-runtime-evidence --require-plan-ready
```

Plan readiness requires `all_local_receipts_complete=true`,
`all_gate_receipts_current_head=true`, `exact_head_ci_verified=true`,
`real_runtime_acceptance_verified=true`, `clean_worktree_verified=true`,
`remote_sync_verified=true`, `release_complete=true`,
`commercial_handoff_allowed=true`, and `ready_to_merge=true`.

The plan never mutates `COMMERCIAL_EVIDENCE_RECEIPTS.json`, never promotes
release-grade receipts by itself, never runs live agents, and never changes
release, handoff, or merge readiness.

Invalid plan evidence includes `manual_receipt_promotion_without_ci`,
`uncommitted_dirty_promotion`, `local_only_release_grade_claim`,
`mock_only_product_claim`, `release_complete_true_without_preflight`,
`raw_prompts`, `raw_responses`, `private_transcripts`, and `token_values`.
