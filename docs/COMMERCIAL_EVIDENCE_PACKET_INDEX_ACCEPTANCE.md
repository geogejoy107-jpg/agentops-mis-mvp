# Commercial Evidence Packet Index Acceptance

## Scope

This slice starts Lane 4 of the commercial migration clean-room plan by adding a
static packet inventory and safety gate. It does not implement packet generation
or change backend/UI behavior.

## Verification

- `python3 scripts/commercial_evidence_packet_index_smoke.py`
- `python3 -m py_compile scripts/commercial_evidence_packet_index_smoke.py scripts/release_evidence_packet_smoke.py`
- `python3 scripts/release_evidence_packet_smoke.py`
- `python3 scripts/secret_scan_smoke.py`
- `git diff --check`

## Acceptance Checklist

- [x] PR #22 remains reference-only and is not merged or copied wholesale.
- [x] Commercial evidence packets are listed with purpose, source of truth,
  current status, and future smoke names.
- [x] Forbidden inputs exclude secrets, raw logs, raw prompts/responses, private
  messages, full transcripts, DB files, generated snapshots, caches,
  `node_modules`, and `dist`.
- [x] Exact current-head CI is required before promotion or release claims.
- [x] The index makes no hosted, billing, cleanup, Postgres, commercial-ready,
  or live-runtime execution claims.
- [x] The new smoke is wired into CI and the release evidence command manifest.

## Known Limitations

- This is an index/gate only. The first actual generator should be the current
  evidence status packet.
- No packet is generated or committed by this slice.
- No live Hermes/OpenClaw execution is required because this is a static
  commercial evidence boundary slice.

