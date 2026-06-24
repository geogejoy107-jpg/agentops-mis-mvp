# Commercial Current Evidence Status

Contract: `commercial_current_evidence_status_v1`

Current status: `current_evidence_required`.

This packet is the CI-safe evidence coverage layer under
`commercial_handoff_status_v1`. It reads the commercial release packet,
release entry point, freeze protocol, and merge-readiness status:
`commercial_release_evidence_packet_v1`, `release_evidence_packet_v1`,
`release_freeze_protocol_v1`, and `merge_readiness_status_v1`. It exposes
`phase_gate_evidence_statuses`, `evidence_current`,
`gates_requiring_current_evidence`, and `required_commands` so operators can see
which phase gates still require current evidence. Passing this check means the
evidence map is internally consistent; it does not mean the commercial release
is ready.

Read the current evidence coverage:

```bash
python3 scripts/commercial_current_evidence_status.py
```

Verify the evidence status contract:

```bash
python3 scripts/commercial_current_evidence_status_smoke.py
```

Strict current-evidence assertions must fail while any gate still has
`evidence_current=false`:

```bash
python3 scripts/commercial_current_evidence_status.py --require-current-evidence
python3 scripts/commercial_current_evidence_status_smoke.py --require-current-evidence
```

The status intentionally does not execute Docker, browser, Postgres, or live
Hermes/OpenClaw checks. It names those required commands so the handoff status
can show the operator exactly what still needs fresh evidence.

Required heavy/live evidence remains:

```bash
python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture
python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture
python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture
HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api
```

Invalid evidence includes `--skip-postgres-if-unavailable`,
`mock_only_product_claim`, `release_complete_true`, raw prompts, raw responses,
private transcripts, token values, and SQLite fallback presented as Postgres
proof.
