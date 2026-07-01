# Loop Driver Dogfood Acceptance

## Purpose

This slice proves the Hermes/OpenClaw operator loop can be consumed by
machine-style callers through the AgentOps MIS CLI/API contract, not only by a
human reading the UI.

It starts an isolated local MIS server with a temporary SQLite database and
asks both `hermes` and `openclaw` adapters to:

1. read `agent_work_packet_decision_v1` through loop supervision,
2. preview the decision-gated loop driver,
3. receive an `operator_loop_driver_agent_loop_packet`,
4. avoid live adapter execution, server shell, DB mutation and token leakage.

## Commands

```bash
python3 scripts/operator_loop_driver_dogfood_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py
python3 scripts/secret_scan_smoke.py
git diff --check
```

## Expected Evidence

- `operation=operator_loop_driver_dogfood_smoke`
- adapters: `hermes`, `openclaw`
- `secret_leaked=false`
- read-only DB counts unchanged for `runs`, `audit_logs`, `runtime_events`
- loop-driver status remains `preview`
- `work_packet_decision.operation=operator_loop_driver_work_packet_decision_gate`
- `agent_loop_packet.operation=operator_loop_driver_agent_loop_packet`
- confirm and execute commands are copied to the agent packet rather than
  executed by the server

## Boundary

- This is not a live Hermes/OpenClaw runtime execution.
- This does not claim autonomous customer task completion.
- This does not ingest prompts, raw responses, credentials, private messages or
  transcripts.
- This does not commit local SQLite DBs, caches, `dist`, `node_modules` or env
  files.

## Next Slice

After this passes and PR #65 lands, rebase this branch onto `origin/main`, run
the strict release evidence packet, and open a draft PR for the dogfood smoke
plus acceptance record.
