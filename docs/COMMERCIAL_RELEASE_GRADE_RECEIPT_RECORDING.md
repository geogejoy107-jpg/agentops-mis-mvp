# Commercial Release-Grade Receipt Recording

Contract: `commercial_release_grade_receipt_recording_v1`

Current status: `blocked_receipt_recording_preview`.

This is the preview layer after `commercial_release_grade_rerun_bundle_v1`. It
turns each Gate 1-5 rerun bundle into an operator-safe receipt recording
request: the current-head rerun commands, the target
`COMMERCIAL_EVIDENCE_RECEIPTS.json` location, and the JSON patch fields that
would be recorded only after the operator supplies fresh evidence. Every patch
operation is `preview_only_json_patch` in this preview layer.

Default mode is offline, read-only, and CI-safe:

```bash
python3 scripts/commercial_release_grade_receipt_recording.py
```

Add current-head GitHub Actions evidence:

```bash
python3 scripts/commercial_release_grade_receipt_recording.py --include-external-ci-evidence
```

Add a fresh real Hermes/OpenClaw runtime acceptance JSON:

```bash
HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api > /tmp/agentops-mis-runtime-acceptance.json
python3 scripts/commercial_release_grade_receipt_recording.py --include-external-ci-evidence --runtime-acceptance-json /tmp/agentops-mis-runtime-acceptance.json --require-current-runtime-evidence
```

Strict recording readiness must fail until all global invariants and per-gate
receipt freshness requirements are true:

```bash
python3 scripts/commercial_release_grade_receipt_recording.py --include-external-ci-evidence --runtime-acceptance-json /tmp/agentops-mis-runtime-acceptance.json --require-current-runtime-evidence --require-recording-ready
```

Recording readiness requires `all_gate_recording_patches_materialized=true`,
`all_recording_patches_preview_only=true`,
`all_receipt_mutation_disabled=true`,
`all_gate_receipts_current_head=true`, `exact_head_ci_verified=true`,
`real_runtime_acceptance_verified=true`,
`current_runtime_evidence_supplied=true`, `clean_worktree_verified=true`,
`remote_sync_verified=true`, `release_complete=true`,
`commercial_handoff_allowed=true`, and `ready_to_merge=true`.

The packet never mutates `COMMERCIAL_EVIDENCE_RECEIPTS.json`, never executes
rerun commands, never promotes release-grade receipts, never runs live agents,
and never changes release, handoff, or merge readiness. It is a recording
request and patch preview, not the write path.

Invalid recording evidence includes `manual_receipt_promotion_without_ci`,
`direct_json_edit_without_recording_preview`,
`receipt_mutation_during_preview`,
`receipt_mutation_without_operator_confirmation`,
`rerun_command_auto_execution`,
`release_grade_receipt_write_without_current_head_ci`, `raw_prompts`,
`raw_responses`, `private_transcripts`, and `token_values`.
