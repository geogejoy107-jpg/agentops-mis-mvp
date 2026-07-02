# Commander Lane Packet Acceptance

## Scope

This slice adds a machine-facing Commander lane packet readback for agents,
workers and future OpenClaw/Hermes adapters. It does not execute work, call live
runtimes, create tasks/runs, scrape browser UI, or store raw prompts, responses,
source bodies, credentials or private transcripts.

## Implemented

- `GET /api/commander/lane-packets`
- `agentops commander lane-packets`
- Core read-model helpers in `agentops_mis_core/commander_work_packages.py`
- CI/release-evidence wiring through `scripts/commander_lane_packet_smoke.py`

Each lane packet includes:

- `lane_id`
- `objective`
- `owner`
- `runtime`
- `phase`
- `task_id`
- `run_id`
- `packet_hash`
- `blocked_reason`
- `next_command`
- `verification_command`
- `evidence_refs`
- `claim_limit`
- `safety`

## Verification

Run locally:

```bash
python3 scripts/commander_lane_packet_smoke.py
python3 scripts/module_boundary_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
python3 scripts/release_evidence_packet_smoke.py
git diff --check
```

The smoke starts an isolated server and temporary SQLite database, creates two
Commander work packages, dispatches one mock package, reads lane packets through
API and CLI, verifies stable packet hashes, and confirms the lane packet
readback does not mutate ledger tables.

## Known Limits

- This is a readback contract, not a worker daemon.
- Hermes/OpenClaw execution still happens only at explicit dispatch boundaries.
- Remote worker enrollment and production RBAC remain separate hardening lanes.
