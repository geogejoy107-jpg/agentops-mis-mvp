# Release Freeze Protocol

Contract: `release_freeze_protocol_v1`

This protocol keeps the commercial migration in a hardening freeze until the
release evidence packet and Gate 5 BYOC/Postgres handoff evidence are current.
It does not claim the product is release-complete.
Current status: `freeze_active_not_release_complete`.

Verify the freeze gate:

```bash
python3 scripts/release_freeze_protocol_smoke.py
```

Final local review can additionally require a clean worktree:

```bash
python3 scripts/release_freeze_protocol_smoke.py --require-clean
```

The freeze requires the release packet, commercial release packet, backend
Postgres readiness fixture, Next Postgres browser fixture, BYOC Postgres handoff
fixture, and real Hermes/OpenClaw acceptance. `--skip-postgres-if-unavailable`
and mock-only product claims are not valid release evidence.

Required freeze evidence commands:

```bash
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/commercial_release_evidence_packet_smoke.py
python3 scripts/commercial_migration_readiness.py
python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture
python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture
python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture
HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api
```
