# Run Start Work-Packet Decision Gate Acceptance

## Purpose

This slice makes `agent_work_packet_decision_v1` an execution precondition for
Agent Gateway `run_start` on governed local runtimes.

Before a Hermes/OpenClaw run row is created, AgentOps MIS now reads the compact
work-packet decision derived from loop supervision. Unsafe decisions fail closed
with `run_start_work_packet_decision_blocked`; safe governance-first decisions
are attached to the run-start response and run audit metadata by hash.

## Verification

```bash
python3 scripts/run_start_work_packet_decision_gate_smoke.py
python3 scripts/run_start_loop_supervision_gate_smoke.py
python3 scripts/operator_loop_driver_dogfood_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/secret_scan_smoke.py
git diff --check
```

Local result on 2026-07-01:

- `python3 scripts/run_start_work_packet_decision_gate_smoke.py`: passed
- `python3 scripts/run_start_loop_supervision_gate_smoke.py`: passed
- `python3 scripts/operator_loop_driver_dogfood_smoke.py`: passed
- `python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py`: passed
- `python3 scripts/release_evidence_packet_smoke.py`: passed
- `python3 scripts/secret_scan_smoke.py`: passed
- `git diff --check`: passed

## Expected Evidence

- blocked Hermes decision returns HTTP-style status `428`
- blocked path does not create a `runs` row
- blocked path writes `agent_gateway.run_start_work_packet_decision_blocked`
- ready OpenClaw decision returns `201`
- ready response includes `work_packet_decision_gate`
- ready response includes `agent_plan.work_packet_decision_hash`
- mock runtime is unaffected and does not read loop supervision
- all gate payloads prove read-only, no ledger mutation before run creation,
  no server shell, no live execution, raw prompt/response/content omitted and
  token omitted

## Boundary

- This does not execute Hermes or OpenClaw.
- This does not start a worker daemon.
- This does not add hosted/commercial scope.
- This does not store raw prompts, raw responses, credentials, private
  transcripts or local DB contents.
