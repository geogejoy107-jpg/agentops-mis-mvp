# Loop Work Packet Decision Acceptance

Date: 2026-07-01

Branch: `codex/osbi-loop-decision-mainline`

## Slice

This slice ports the smallest useful OSBI loop-decision layer onto current
`origin/main`. It adds a read-only `agent_work_packet_decision_v1` projection
for Hermes/OpenClaw/Codex local loop callers so agents can consume the compact
work packet without scraping the full supervision payload.

## Boundary

- Adds `GET /api/operator/loop-supervision?decision=1`.
- Adds `agentops operator loop-supervision --decision`.
- Keeps the server copy-only: no shell execution, no live Hermes/OpenClaw run,
  no approval decision, no ledger mutation, and no raw prompt/response/token
  persistence.
- Keeps Research Lab consumption as an optional explicit contract only. Missing
  `research_lab_consumption` metadata on current main does not force ordinary
  packets into `record_research_consumption_first`.
- Does not port the loop-driver decision consumer from the OSBI branch; that is
  the next separable slice.

## Verification

```bash
python3 -m py_compile server.py agentops_mis_cli/agentops.py
python3 scripts/operator_loop_supervision_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/secret_scan_smoke.py
git diff --check
```

Results:

- `py_compile`: pass
- `operator_loop_supervision_smoke`: pass, no failures, `secret_leaked=false`
- `release_evidence_packet_smoke`: pass, `release_status=READY_TO_MERGE`
- `secret_scan_smoke`: pass, 0 findings
- `git diff --check`: pass

## Known Limitations

- The decision projection classifies the next copyable command; it does not run
  the command.
- Loop-driver consumption of `agent_work_packet_decision_v1` remains a separate
  v1.5 follow-up slice.
- Real Hermes/OpenClaw runtime execution is intentionally out of scope for this
  read-only governance projection.

## Next Slice

Port the loop-driver consumer from the OSBI branch after this decision
projection is merged:

- fetch decision gate in loop-driver preview and confirmed paths
- expose before/after/final decision readback
- extend `scripts/operator_loop_driver_smoke.py`
