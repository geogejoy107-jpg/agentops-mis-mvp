# Commercial Release Evidence Packet

Contract: `commercial_release_evidence_packet_v1`

This packet is the commercial migration release checklist. It is not a claim
that the product is release-complete yet; it is a fail-closed map of evidence
that must exist before the local-first/BYOC control plane can be treated as a
commercial handoff candidate.

Verify the packet itself:

```bash
python3 scripts/commercial_handoff_status.py
python3 scripts/commercial_handoff_status_smoke.py
python3 scripts/commercial_evidence_receipts.py
python3 scripts/commercial_evidence_receipts_smoke.py
python3 scripts/commercial_current_evidence_status.py
python3 scripts/commercial_current_evidence_status_smoke.py
python3 scripts/commercial_release_evidence_packet_smoke.py
```

The standard release entry point, freeze gate, and merge-readiness gate are:

```bash
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/release_freeze_protocol_smoke.py
python3 scripts/merge_readiness_status_smoke.py
```

## Non-Negotiable Gates

- Agent Gateway CLI/API/MCP remains the durable agent execution and evidence
  writeback contract.
- Python/SQLite/Vite remains valid until storage and UI parity gates prove a
  replacement path.
- Postgres/BYOC handoff requires backend and browser evidence, not only docs:
  `deployment_readiness_smoke.py --postgres-write-fixture`,
  `nextjs_playwright_snapshot_smoke.py --postgres-write-fixture`, and
  `byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture`.
- Product-readiness or customer-usefulness claims require real Hermes/OpenClaw
  evidence with `local_runtime_acceptance.py --live-openclaw --live-hermes`;
  mock evidence is CI/offline fallback only.
- No secrets, local databases, generated artifacts, raw prompts, raw responses,
  private transcripts, or token values may be committed.

## Gate 5 Handoff Evidence

The BYOC handoff path must prove:

- backup create/verify/restore, restore confirmation, overwrite safety copy,
  signed audit export, raw metadata omission, and tamper detection;
- configured retention and Enterprise SSO/private connector readiness;
- Postgres `experimental_write_http` deployment readiness with
  `runtime_write_gate=active`;
- fixed OpenClaw/Hermes prepared-action write contracts plus row-gated approval
  write contract;
- non-allowlisted writes blocked with `postgres_read_only_backend`;
- unchanged Postgres ledger counts while rendering backend and Next deployment
  readiness evidence;
- real Hermes/OpenClaw runtime acceptance separate from mock/offline smokes.

The machine-readable source of truth is
`docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json`. The current handoff aggregate is
`commercial_handoff_status_v1` in `docs/COMMERCIAL_HANDOFF_STATUS.json`; its
local receipt ledger is `commercial_evidence_receipts_v1`, and its evidence
coverage layer is `commercial_current_evidence_status_v1`.
