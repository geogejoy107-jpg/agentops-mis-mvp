# Commander Lane Packet Dispatch Acceptance

## Scope

This slice binds Commander dispatch evidence to the machine-readable lane packet
introduced in PR #78. It does not start live Hermes/OpenClaw by default, does
not add a daemon, and does not store raw prompts, responses, source bodies,
credentials or private transcripts.

## Implemented

- `POST /api/commander/work-packages/:task_id/dispatch` builds a safe
  `commander_lane_packet` summary before worker execution.
- Successful mock dispatch responses include `commander_lane_packet`.
- Hermes/OpenClaw no-confirm gates include `commander_lane_packet` even when no
  run is created.
- Dispatch audit metadata stores both `commander_lane_packet` and
  `commander_lane_packet_hash`.
- Runtime event payload hashes include the lane packet hash so dispatch evidence
  can be traced without storing the raw packet source context.

## Verification

Run with an isolated server and SQLite DB:

```bash
python3 scripts/commander_work_package_dispatch_smoke.py
python3 scripts/module_boundary_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
git diff --check
```

The dispatch smoke verifies API dispatch, CLI dispatch and the Hermes
confirm-required gate all return a lane packet hash, then reads audit metadata
from SQLite to confirm the ledger stores the same packet hash.

## Product Meaning

This is the evidence bridge between a Commander lane packet and a worker run.
Future Hermes/OpenClaw adapter loops can claim "this run followed a Commander
lane packet" only when the run's dispatch evidence carries this packet hash.
