# Commercial Handoff Status

Contract: `commercial_handoff_status_v1`

Current status: `blocked_release_evidence_required`.

This is the operator-facing status surface for the commercial migration lane. It
aggregates `commercial_release_evidence_packet_v1`,
`release_evidence_packet_v1`, `release_freeze_protocol_v1`, and
`merge_readiness_status_v1`, plus the
`commercial_current_evidence_status_v1` evidence coverage map, without running
Docker, browsers, or live agents.
Passing the default check means the handoff status is internally consistent; it
does not mean the product is release-complete.

Expected source statuses are `gate_enforced_not_release_complete`,
`freeze_active_not_release_complete`, and `blocked_release_evidence_required`.

Read the current handoff status:

```bash
python3 scripts/commercial_handoff_status.py
python3 scripts/commercial_current_evidence_status.py
```

Verify the status contract:

```bash
python3 scripts/commercial_handoff_status_smoke.py
python3 scripts/commercial_current_evidence_status_smoke.py
```

Strict handoff assertions must fail while the status remains blocked:

```bash
python3 scripts/commercial_handoff_status.py --require-handoff-ready
python3 scripts/commercial_handoff_status_smoke.py --require-handoff-ready
```

The status must expose `commercial_handoff_allowed`, `release_complete`,
`ready_to_merge`, `explicit_blockers`, `required_commands`, and
`phase_gate_statuses`.

Required evidence commands include:

```bash
python3 scripts/commercial_handoff_status.py
python3 scripts/commercial_handoff_status_smoke.py
python3 scripts/commercial_current_evidence_status.py
python3 scripts/commercial_current_evidence_status_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/commercial_release_evidence_packet_smoke.py
python3 scripts/release_freeze_protocol_smoke.py
python3 scripts/merge_readiness_status_smoke.py
python3 scripts/commercial_migration_readiness.py
python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture
python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture
python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture
HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api
```

Invalid evidence includes `--skip-postgres-if-unavailable`,
`mock_only_product_claim`, `release_complete_true`, raw prompts, raw responses,
private transcripts, token values, and SQLite fallback presented as Postgres
proof.
