# AgentOps MIS v1.5 Agent Worker Acceptance

## Build / Syntax

Command:

```bash
python3 -m py_compile server.py scripts/*.py
git diff --check
```

Result: passed.

## Runtime Prerequisites Used

- AgentOps MIS backend: `http://127.0.0.1:8787`
- Hermes OpenAI-compatible gateway: `http://127.0.0.1:8642`
- OpenClaw CLI: `/opt/homebrew/bin/openclaw`
- Dify and Notion: not used in this acceptance pass.

## Worker Commands Run

Mock adapter:

```bash
python3 scripts/agent_worker.py --once --adapter mock --agent-id agt_worker_local
```

Hermes adapter:

```bash
python3 scripts/agent_worker.py \
  --once \
  --adapter hermes \
  --confirm-run \
  --agent-id agt_worker_local \
  --hermes-gateway-url http://127.0.0.1:8642
```

OpenClaw adapter:

```bash
python3 scripts/agent_worker.py \
  --once \
  --adapter openclaw \
  --confirm-run \
  --agent-id agt_worker_local \
  --openclaw-timeout 180
```

## Evidence

| Adapter | Task | Run | Result |
| --- | --- | --- | --- |
| mock | `tsk_worker_debug_create` | `run_gw_a20e5b2eb6e3` | completed |
| hermes | `tsk_worker_hermes_acceptance_20260617145544` | `run_gw_0d793ed6bbac` | completed |
| openclaw | `tsk_worker_openclaw_acceptance_20260617145647` | `run_gw_9b2a6550d489` | completed |

All three runs produced:

- `runs.status = completed`
- one `tool_calls` row with `agent_worker.{adapter}`
- one `evaluations` row with `pass`
- `audit_logs` entries including `agent_worker.task_processed`
- completed task status

## What This Proves

The v1.5 worker loop can process normal MIS tasks, not just connector probes:

```text
planned MIS task
  -> Agent Gateway task pull
  -> claim
  -> run start
  -> adapter execution
  -> tool call record
  -> run heartbeat completed/failed
  -> evaluation submit
  -> audit emit
  -> optional memory proposal
```

## Boundaries

- Hermes/OpenClaw live execution requires `--confirm-run`.
- The worker does not call Dify or Notion.
- The worker does not store full prompts or raw responses.
- The worker is repo-local; it is not yet a launchd service, pip package, npm package, or signed binary.
- Remote enrollment, token revocation, RBAC, scope enforcement, and UI worker controls remain future work.
