# Commander Work Package Planner

## Purpose

The Commander Work Package Planner turns one customer or operator goal into a bounded set of MIS work-package tasks for an AI team.

It is the product version of the current development workflow: a commander decomposes work, assigns lanes, keeps scope boundaries visible, and lets workers execute through Agent Gateway CLI/API instead of browser clicks.

## Safety Model

- Preview is the default and does not mutate the ledger.
- Real task creation requires `confirm_create:true` or `--confirm-create`.
- The planner does not execute Hermes, OpenClaw, Dify, Notion, shell, or browser actions.
- Work-package dispatch is explicit and targeted by `task_id`; it runs through the Agent Gateway worker loop, not an ad hoc backend shortcut.
- Mock dispatch is safe for local demos. Hermes/OpenClaw dispatch requires explicit `confirm_run:true` / `--confirm-run`.
- Stored text is redacted and bounded; raw prompts, credentials, tokens, raw model responses, and private transcripts are not stored.
- Confirmed planning writes normal MIS task rows plus runtime/audit evidence.

## API

Preview:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/plan \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Use AgentOps MIS to coordinate a customer AI-team project.",
    "max_packages": 5
  }' | jq .
```

Create planned work-package tasks:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/plan \
  -H "Content-Type: application/json" \
  -d '{
    "goal": "Use AgentOps MIS to coordinate a customer AI-team project.",
    "max_packages": 5,
    "confirm_create": true
  }' | jq .
```

Read persisted work packages:

```bash
curl -s "http://127.0.0.1:8787/api/commander/work-packages?project_id=proj_x&limit=25" | jq .
```

The readback endpoint is read-only. It reconstructs work-package state from
normal MIS `tasks`, links the latest run, counts evidence rows, and returns a
recommended next action for each lane.

Dispatch one persisted package through the mock worker:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/tsk_cmd_example_strategy/dispatch \
  -H "Content-Type: application/json" \
  -d '{"adapter":"mock"}' | jq .
```

Confirmed live dispatch uses the same endpoint but must be explicit:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/tsk_cmd_example_strategy/dispatch \
  -H "Content-Type: application/json" \
  -d '{"adapter":"openclaw","confirm_run":true}' | jq .
```

If `adapter` is `hermes` or `openclaw` and confirmation is omitted, MIS writes a
confirm-required runtime/audit event and does not create a run.

Queue several planned packages as async workflow jobs:

```bash
curl -s -X POST http://127.0.0.1:8787/api/commander/work-packages/dispatch-batch \
  -H "Content-Type: application/json" \
  -d '{
    "project_id": "proj_x",
    "status": "planned",
    "limit": 5,
    "adapter": "mock"
  }' | jq .
```

The batch endpoint creates `workflow_jobs` rows and returns immediately. Each job
then executes the exact target work-package `task_id` through the same Agent
Gateway worker loop. Hermes/OpenClaw batch dispatch is rejected unless
`confirm_run:true` is present.

## CLI

Preview:

```bash
./scripts/agentops commander plan \
  --goal "Use AgentOps MIS to coordinate a customer AI-team project." \
  --max-packages 5
```

Create tasks:

```bash
./scripts/agentops commander plan \
  --goal "Use AgentOps MIS to coordinate a customer AI-team project." \
  --max-packages 5 \
  --confirm-create
```

Read persisted packages:

```bash
./scripts/agentops commander packages --project-id proj_x --limit 25
```

Dispatch a package:

```bash
./scripts/agentops commander dispatch-package \
  --task-id tsk_cmd_example_strategy \
  --adapter mock
```

Confirmed live dispatch:

```bash
./scripts/agentops commander dispatch-package \
  --task-id tsk_cmd_example_strategy \
  --adapter openclaw \
  --confirm-run
```

Queue planned packages in parallel:

```bash
./scripts/agentops commander dispatch-batch \
  --project-id proj_x \
  --status planned \
  --limit 5 \
  --adapter mock
```

Then poll returned jobs:

```bash
./scripts/agentops workflow job-status --job-id wfjob_x --wait
./scripts/agentops commander packages --project-id proj_x --limit 25
```

## Default Lanes

- Strategy: clarify goal, acceptance gates, approvals, and scope.
- Research: gather grounded repo/product evidence without ingesting private transcripts.
- Implementation: make the smallest useful bounded product increment.
- QA: verify ledger evidence, smoke tests, and safety gates.
- Ops: prepare customer-facing handoff and runbook notes.

Each generated task includes:

- owner agent
- collaborators
- scope
- avoid scope
- dependencies
- verification commands
- return checklist
- acceptance criteria

## UI

Open `/workspace/agents` and use **Commander Work Package Planner**.

The panel supports:

- previewing the work-package split
- confirming task creation
- opening created task detail pages
- reading persisted work-package status after refresh
- dispatching a persisted package through mock, Hermes, or OpenClaw worker adapters
- queueing currently planned packages as mock async workflow jobs
- seeing safety proof for no live execution and token omission

## Verification

```bash
python3 scripts/commander_work_package_plan_smoke.py
python3 scripts/commander_work_package_dispatch_smoke.py
python3 scripts/commander_work_package_batch_dispatch_smoke.py
python3 -m py_compile server.py scripts/*.py agentops_mis_cli/*.py
cd ui/start-building-app && npm run build
```
