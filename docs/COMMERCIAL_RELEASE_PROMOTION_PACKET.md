# Commercial Release Promotion Packet

Contract: `commercial_release_promotion_packet_v1`

Current status: `blocked_release_promotion_required`.

This is the operator-facing packet for commercial release promotion. It
aggregates the promotion preflight, local/release-grade receipt state,
current-head GitHub Actions evidence when explicitly requested, and real
Hermes/OpenClaw runtime acceptance evidence when an operator supplies the
fresh `local_runtime_acceptance.py` JSON output.

Source contracts include `commercial_release_promotion_preflight_v1`,
`commercial_exact_head_ci_evidence_v1`, `commercial_evidence_receipts_v1`,
`commercial_current_evidence_status_v1`, `commercial_handoff_status_v1`,
`release_freeze_protocol_v1`, and `merge_readiness_status_v1`.

Default packet generation is read-only, CI-safe, and offline:

```bash
python3 scripts/commercial_release_promotion_packet.py
```

Read exact-head CI from external GitHub Actions state:

```bash
python3 scripts/commercial_release_promotion_packet.py --include-external-ci-evidence
```

Attach a fresh real-runtime acceptance run without storing prompts, responses,
private transcripts, token values, databases, or generated artifacts:

```bash
HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api > /tmp/agentops-mis-runtime-acceptance.json
python3 scripts/commercial_release_promotion_packet.py --include-external-ci-evidence --runtime-acceptance-json /tmp/agentops-mis-runtime-acceptance.json --require-current-runtime-evidence
```

Strict promotion must remain blocked until every release condition is true:

```bash
python3 scripts/commercial_release_promotion_packet.py --include-external-ci-evidence --runtime-acceptance-json /tmp/agentops-mis-runtime-acceptance.json --require-current-runtime-evidence --require-promotion-packet-ready
```

Promotion requires:

```text
all_local_receipts_complete=true
gates_with_release_grade_receipts_complete=true
clean_worktree_verified=true
remote_sync_verified=true
exact_head_ci_verified=true
real_runtime_acceptance_verified=true
release_complete=true
commercial_handoff_allowed=true
ready_to_merge=true
```

The packet never mutates `COMMERCIAL_EVIDENCE_RECEIPTS.json`, never promotes
release-grade receipts by itself, never runs live agents, and never changes
handoff or merge readiness.

Invalid packet evidence includes `manual_receipt_promotion_without_ci`,
`uncommitted_dirty_promotion`, `local_only_release_grade_claim`,
`mock_only_product_claim`, `release_complete_true_without_preflight`,
`raw_prompts`, `raw_responses`, `private_transcripts`, and `token_values`.
