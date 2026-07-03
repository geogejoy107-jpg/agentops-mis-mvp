# Commander Work Package Batch Dispatch Acceptance

## Scope

This slice promotes Commander batch async dispatch from an available local
capability into release-gated evidence.

It does not add a new runtime adapter, does not start live Hermes/OpenClaw by
default, does not change the worker daemon, and does not store raw prompts,
raw responses, credentials, private transcripts, local DB files or generated
exports.

## Implemented

- CI server-backed smokes now run
  `python3 scripts/commander_work_package_batch_dispatch_smoke.py`.
- `scripts/release_evidence_packet_smoke.py` now lists
  `commander_work_package_batch_dispatch` as server-backed release evidence.
- `docs/RELEASE_EVIDENCE_PACKET.md` now includes the same command.
- Batch queue responses and workflow job audit metadata now include bounded
  `commander_lane_packet` evidence plus `commander_lane_packet_hash`.
- `workflow_jobs.result_json` stores a safe queued proof until the background
  worker overwrites it with completed dispatch results.

## Verification

Run with an isolated server and SQLite DB:

```bash
python3 scripts/commander_work_package_batch_dispatch_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
git diff --check
```

The smoke creates three Commander work-package tasks, queues two mock adapter
dispatches as `workflow_jobs`, waits for completion, verifies the resulting
run/tool/evaluation/job evidence, verifies queued and completed packet hashes,
checks workflow job submission audit metadata, and proves an OpenClaw batch
dispatch without `confirm_run:true` fails closed before creating jobs.

## Product Meaning

This is the first release-gated proof that AgentOps MIS can coordinate a small
AI-team style workload asynchronously:

```text
plan packages
-> queue selected lanes as workflow jobs
-> bind queued jobs to lane packet hashes
-> worker loop writes normal MIS evidence
-> team board/readback shows completed lanes
-> live adapters remain confirmation-gated
```

It moves the product closer to the user's target of using MIS itself for
multi-lane project development rather than treating parallel work as only a
Codex conversation pattern.
