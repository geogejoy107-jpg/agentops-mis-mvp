# Merge Readiness Status

Contract: `merge_readiness_status_v1`

Current status: `blocked_release_evidence_required`.

This file makes the commercial migration merge state explicit. The branch can
continue accumulating verified slices, but it must not claim ready-to-merge
until the release evidence packet, freeze protocol, Gate 5 BYOC/Postgres
handoff fixtures, real Hermes/OpenClaw acceptance, clean worktree, remote sync,
and exact-head CI evidence are all current.

Default smoke:

```bash
python3 scripts/merge_readiness_status_smoke.py
```

Required before ready-to-merge:

```bash
python3 scripts/commercial_current_evidence_status_smoke.py
python3 scripts/commercial_handoff_status_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/commercial_release_evidence_packet_smoke.py
python3 scripts/release_freeze_protocol_smoke.py
python3 scripts/commercial_migration_readiness.py
python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture
python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture
python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture
HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api
```

Final ready-to-merge assertion:

```bash
python3 scripts/merge_readiness_status_smoke.py --require-ready-to-merge
```

The strict ready-to-merge assertion must fail while this status remains
`blocked_release_evidence_required`.
