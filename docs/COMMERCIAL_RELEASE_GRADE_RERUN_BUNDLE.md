# Commercial Release-Grade Rerun Bundle

Contract: `commercial_release_grade_rerun_bundle_v1`

Current status: `blocked_rerun_bundle_preview`.

This is the preview layer after `commercial_release_grade_receipt_plan_v1`. It
turns the per-gate plan into Gate 1-5 rerun bundles: each bundle lists the
commands an operator must rerun on the current head and shows the exact
`COMMERCIAL_EVIDENCE_RECEIPTS.json` fields that would be updated after the
operator records fresh local receipt evidence.

Default mode is offline, read-only, and CI-safe:

```bash
python3 scripts/commercial_release_grade_rerun_bundle.py
```

Add current-head GitHub Actions evidence:

```bash
python3 scripts/commercial_release_grade_rerun_bundle.py --include-external-ci-evidence
```

Add a fresh real Hermes/OpenClaw runtime acceptance JSON:

```bash
HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api --openclaw-timeout 300 --hermes-timeout 600 --request-timeout 720 > /tmp/agentops-mis-runtime-acceptance.json
python3 scripts/commercial_release_grade_rerun_bundle.py --include-external-ci-evidence --runtime-acceptance-json /tmp/agentops-mis-runtime-acceptance.json --require-current-runtime-evidence
```

Strict bundle readiness must fail until all global invariants and per-gate
receipt freshness requirements are true:

```bash
python3 scripts/commercial_release_grade_rerun_bundle.py --include-external-ci-evidence --runtime-acceptance-json /tmp/agentops-mis-runtime-acceptance.json --require-current-runtime-evidence --require-bundle-ready
```

Bundle readiness requires `all_gate_rerun_bundles_materialized=true`,
`all_bundle_write_previews_read_only=true`,
`all_gate_receipts_current_head=true`, `exact_head_ci_verified=true`,
`real_runtime_acceptance_verified=true`, `clean_worktree_verified=true`,
`remote_sync_verified=true`, `release_complete=true`,
`commercial_handoff_allowed=true`, and `ready_to_merge=true`.

The bundle never mutates `COMMERCIAL_EVIDENCE_RECEIPTS.json`, never executes the
rerun commands by itself, never promotes release-grade receipts, never runs live
agents, and never changes release, handoff, or merge readiness. It is a
write-before preview, not the write path.

Invalid bundle evidence includes `manual_receipt_promotion_without_ci`,
`uncommitted_dirty_promotion`, `local_only_release_grade_claim`,
`mock_only_product_claim`, `release_complete_true_without_preflight`,
`receipt_mutation_during_preview`, `rerun_command_auto_execution`,
`raw_prompts`, `raw_responses`, `private_transcripts`, and `token_values`.
