# HTTP Loop Work Packet Acceptance

## Scope

This slice exposes the existing Hermes/OpenClaw/Codex loop supervision work
packet through HTTP for machine callers:

```bash
GET /api/operator/loop-supervision?work_packet=1
```

The endpoint returns the same compact `agent_work_packet_bundle_v1` shape used
by `agentops operator loop-supervision --work-packet`, so remote or HTTP-only
agents can consume MIS next-step instructions without scraping the browser UI or
the larger supervision payload.

## Safety Boundary

- Read-only projection.
- No ledger mutation.
- No server-side shell execution.
- No live Hermes/OpenClaw adapter execution.
- No raw prompt, raw response, private transcript, credential, token, or local
  database content is stored or returned by this slice.

## Verification

Commands run locally from the clean mainline worktree:

```bash
git diff --check
python3 -m py_compile server.py agentops_mis_cli/agentops.py scripts/operator_loop_supervision_smoke.py scripts/release_evidence_packet_smoke.py
python3 scripts/operator_loop_supervision_smoke.py
python3 scripts/secret_scan_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/module_boundary_smoke.py
```

Results:

- `operator_loop_supervision_smoke.py`: passed, `secret_leaked=false`.
- `secret_scan_smoke.py`: passed, `finding_count=0`.
- `release_evidence_packet_smoke.py`: passed in non-strict local mode.
- `module_boundary_smoke.py`: passed.
- `git diff --check`: passed.
- `py_compile`: passed.

## Known Limits

- This is not a live runtime run. It deliberately exposes a read-only planning
  packet and leaves execution behind existing confirm-run, Agent Plan,
  retrieval, approval, receipt, and evidence gates.
- The compact HTTP packet currently contains the same mainline
  `agent_work_packet_v1` entries as the CLI packet; Research Lab-specific
  packet fields from experimental branches are intentionally not included here.

## Next Slice

Use this HTTP packet as the stable input for a real Hermes/OpenClaw agent loop:
read compact packet, record any required service receipt/readback, then run a
bounded confirmed loop-driver step only when the packet gates allow it.
