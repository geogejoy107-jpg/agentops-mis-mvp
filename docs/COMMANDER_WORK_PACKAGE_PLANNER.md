# Commander Work Package Planner

## Purpose

The Commander Work Package Planner turns one customer or operator goal into a bounded set of MIS work-package tasks for an AI team.

It is the product version of the current development workflow: a commander decomposes work, assigns lanes, keeps scope boundaries visible, and lets workers execute through Agent Gateway CLI/API instead of browser clicks.

## Safety Model

- Preview is the default and does not mutate the ledger.
- Real task creation requires `confirm_create:true` or `--confirm-create`.
- The planner does not execute Hermes, OpenClaw, Dify, Notion, shell, or browser actions.
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
- seeing safety proof for no live execution and token omission

## Verification

```bash
python3 scripts/commander_work_package_plan_smoke.py
python3 -m py_compile server.py scripts/*.py agentops_mis_cli/*.py
cd ui/start-building-app && npm run build
```
