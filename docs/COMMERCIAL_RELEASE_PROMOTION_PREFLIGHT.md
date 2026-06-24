# Commercial Release Promotion Preflight

Contract: `commercial_release_promotion_preflight_v1`

Current status: `blocked_release_promotion_required`.

This is the CI-safe preflight for promoting local commercial evidence receipts
to release-grade evidence. It reads git state and the commercial evidence
packets, but it does not push, mutate receipt JSON, run browsers, run Docker, or
run live Hermes/OpenClaw.

Run the preflight:

```bash
python3 scripts/commercial_release_promotion_preflight.py
python3 scripts/commercial_release_promotion_preflight.py --include-external-ci-evidence
```

Verify the preflight contract:

```bash
python3 scripts/commercial_exact_head_ci_evidence_smoke.py
python3 scripts/commercial_release_promotion_preflight_smoke.py
```

Strict promotion assertions must fail until all promotion requirements are true:

```bash
python3 scripts/commercial_exact_head_ci_evidence.py --from-gh --require-current-head
python3 scripts/commercial_release_promotion_preflight.py --include-external-ci-evidence --require-promotion-ready
```

Promotion requires:

```text
all_local_receipts_complete=true
gates_with_release_grade_receipts_complete=true
clean_worktree_verified=true
remote_sync_verified=true
exact_head_ci_verified=true
release_complete=true
commercial_handoff_allowed=true
ready_to_merge=true
```

The runtime payload exposes `release_promotion_allowed`,
`release_grade_update_allowed`, `clean_worktree_verified`,
`remote_sync_verified`, and `exact_head_ci_verified` so release operators can
see which blocker still prevents promotion.

For PR #22, the latest recorded exact-head CI evidence is GitHub Actions run
`28107647712` for head `1195c9b`. Any newer evidence commit must still pass its
own PR CI before `exact_head_ci_verified` can clear. Promotion must remain
blocked until release-grade receipts are promoted under a clean worktree and the
handoff/merge gates explicitly allow release completion.

Current-head CI proof must be read from external GitHub Actions state rather
than committed JSON:

```bash
python3 scripts/commercial_exact_head_ci_evidence.py --from-gh --require-current-head
```

Invalid promotion evidence includes `manual_receipt_promotion_without_ci`,
`uncommitted_dirty_promotion`, `local_only_release_grade_claim`,
`mock_only_product_claim`, raw prompts, raw responses, private transcripts, and
token values.
