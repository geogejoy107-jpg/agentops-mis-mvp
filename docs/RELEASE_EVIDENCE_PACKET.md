# Release Evidence Packet

Contract: `release_evidence_packet_v1`

This branch delegates the detailed release checklist to
`commercial_release_evidence_packet_v1` in
`docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json`. The current operator handoff
aggregate is `commercial_handoff_status_v1`, backed by
`commercial_evidence_receipts_v1` and `commercial_current_evidence_status_v1`.

Verify the release packet entry point:

```bash
python3 scripts/release_evidence_packet_smoke.py
```

Verify the detailed commercial packet:

```bash
python3 scripts/commercial_release_evidence_packet_smoke.py
```

Verify freeze and merge-readiness entry points:

```bash
python3 scripts/commercial_handoff_status.py
python3 scripts/commercial_handoff_status_smoke.py
python3 scripts/commercial_evidence_receipts.py
python3 scripts/commercial_evidence_receipts_smoke.py
python3 scripts/commercial_current_evidence_status.py
python3 scripts/commercial_current_evidence_status_smoke.py
python3 scripts/release_freeze_protocol_smoke.py
python3 scripts/merge_readiness_status_smoke.py
```

Gate 5 release evidence must include:

- `python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture`
- `python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture`
- `python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture`
- `HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api --openclaw-timeout 300 --hermes-timeout 600 --request-timeout 720`

The release packet must not accept `--skip-postgres-if-unavailable` or mock-only
runtime evidence for product-readiness claims.
