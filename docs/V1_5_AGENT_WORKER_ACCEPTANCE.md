# AgentOps MIS v1.5 Agent Worker Acceptance

## Build / Syntax

Command:

```bash
python3 -m py_compile server.py scripts/*.py
git diff --check
cd ui/start-building-app && npm run build
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

| Path | Adapter | Task | Run | Result |
| --- | --- | --- | --- | --- |
| CLI | mock | `tsk_worker_debug_create` | `run_gw_a20e5b2eb6e3` | completed |
| CLI | hermes | `tsk_worker_hermes_acceptance_20260617145544` | `run_gw_0d793ed6bbac` | completed |
| CLI | openclaw | `tsk_worker_openclaw_acceptance_20260617145647` | `run_gw_9b2a6550d489` | completed |
| UI | mock | `tsk_worker_ui_mock_20260617150557_657b7768` | `run_gw_8fae81a1bfa6` | completed |

All CLI/live adapter runs produced:

- `runs.status = completed`
- one `tool_calls` row with `agent_worker.{adapter}`
- one `evaluations` row with `pass`
- `audit_logs` entries including `agent_worker.task_processed`
- completed task status

The UI-triggered mock worker run was launched from `/workspace/agents` through:

```http
POST /api/workers/local/dispatch-once
```

It produced the same ledger evidence:

```text
runs:        run_gw_8fae81a1bfa6 completed
tool_calls:  agent_worker.mock completed
evaluations: pass
audit_logs:  task.create, worker.dispatch_task.create, task_claim, run.create, run_heartbeat, agent_worker.task_processed, worker.dispatch_once
```

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
- The UI worker panel is a one-shot dispatch surface, not a daemon supervisor.
- Remote enrollment, token revocation, RBAC, and scope enforcement remain future work.
