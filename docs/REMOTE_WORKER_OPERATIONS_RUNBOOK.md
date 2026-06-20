# Remote Worker Operations Runbook

This runbook is the v1.5 operator path for using AgentOps MIS as a control
plane while an AI digital employee runs on the same machine or another customer
machine. The browser UI is for humans. The `agentops` and `agentops-worker`
commands are for agent runtimes.

## Safety Defaults

- Do not paste real tokens into the repo, screenshots, GitHub issues, or demo
  scripts.
- Do not commit `.agentops_runtime`, `agentops_mis.db`, `.env`, generated
  service files with real tokens, worker logs, or runtime caches.
- Hermes and OpenClaw live worker daemons require explicit `--confirm-run`.
- `agentops worker preflight` is read-only. It checks readiness but does not
  pull a task, start a run, call a model, or write ledger rows.
- Worker evidence stores summaries, hashes, statuses, IDs, and audit metadata.
  It must not store full prompts, raw model responses, private transcripts, or
  credentials.

## Local Operator Path

Run these from the AgentOps MIS repo:

```bash
python3 -m pip install .
agentops doctor
agentops status
agentops worker status
agentops worker preflight --adapter mock
```

For a safe local daemon:

```bash
agentops worker start --adapter mock --poll-interval 5 --max-tasks 0
agentops worker status
agentops worker logs --adapter mock
agentops worker stop --adapter mock
```

For live local Hermes or OpenClaw recording, first run a read-only preflight:

```bash
agentops worker preflight --adapter hermes
agentops worker preflight --adapter openclaw
```

Then start only with explicit confirmation:

```bash
agentops worker start --adapter hermes --confirm-run --poll-interval 5 --max-tasks 0
agentops worker start --adapter openclaw --confirm-run --poll-interval 5 --max-tasks 0
```

Stop live daemons after the recording or task:

```bash
agentops worker stop --adapter hermes
agentops worker stop --adapter openclaw
```

## Remote Machine Enrollment

On the MIS/admin machine, create or request enrollment:

```bash
./scripts/agentops enrollment create \
  --agent-id agt_remote_builder \
  --name "Remote Builder" \
  --runtime mock
```

For a human approval flow:

```bash
./scripts/agentops enrollment request \
  --agent-id agt_remote_builder \
  --name "Remote Builder" \
  --runtime mock
```

After approval:

```bash
./scripts/agentops enrollment issue-approved --request-id <request_id>
```

The token is shown once. Send it through a secure channel to the remote machine.
Do not write it into source control.

## Remote Machine Setup

On the remote machine:

```bash
python3 -m pip install .
export AGENTOPS_BASE_URL="http://<mis-host>:8787"
export AGENTOPS_WORKSPACE_ID="local-demo"
export AGENTOPS_AGENT_ID="agt_remote_builder"
export AGENTOPS_API_KEY="<paste one-time token here>"

agentops doctor
agentops status
agentops agent heartbeat --status idle --summary "remote worker ready"
agentops worker preflight --adapter mock
agentops-worker --once --adapter mock --use-session --session-ttl-sec 900
```

For a long-running remote loop:

```bash
agentops-worker \
  --adapter mock \
  --use-session \
  --session-ttl-sec 900 \
  --poll-interval 5 \
  --max-tasks 0 \
  --continue-on-error \
  --write-state \
  --jsonl-log
```

If the remote machine will execute Hermes or OpenClaw, run preflight first and
then add `--confirm-run` only after the operator confirms that the runtime is
intended to execute live tasks.

## Service Templates

Generate a restartable service template with placeholders only:

```bash
agentops-worker service-template \
  --manager launchd \
  --adapter mock \
  --agent-id agt_remote_builder \
  > ~/Library/LaunchAgents/local.agentops.worker.agt_remote_builder.plist
```

```bash
agentops-worker service-template \
  --manager systemd \
  --adapter mock \
  --agent-id agt_remote_builder \
  > ~/.config/systemd/user/agentops-worker-agt_remote_builder.service
```

Before loading either service, replace `<paste one-time token here>` locally on
the worker machine. Do not commit the generated service file if it contains a
real token.

Run a read-only service check before loading or troubleshooting a worker
service:

```bash
agentops-worker service-check \
  --manager launchd \
  --adapter mock \
  --agent-id agt_remote_builder
```

```bash
agentops worker service-check \
  --manager systemd \
  --adapter mock \
  --agent-id agt_remote_builder \
  --service-path ~/.config/systemd/user/agentops-worker-agt_remote_builder.service
```

The check inspects the service file and OS service status only. It does not
install, load, unload, restart, or execute the worker. It omits raw service file
content and fails closed if token-like values such as enrollment/session/API
tokens are detected in a generated file.

## Operations Loop

1. Human creates or assigns a task in AgentOps MIS.
2. Worker pulls planned tasks through Agent Gateway.
3. Worker claims the task, starts a run, executes the adapter, and writes
   tool-call/evaluation/audit evidence.
4. Human reviews Runs, Tool Calls, Evaluations, Audit, and Approvals.
5. If a worker dies mid-task, run:

```bash
agentops worker stuck
agentops worker release --task-id <task_id> --reason "reviewed stale worker"
```

Machine-facing task creation can come from a local script, another server, or an
external agent process. Use the CLI when the caller should not operate the
browser UI:

```bash
agentops task create \
  --title "Build a knowledge-base Q&A bot" \
  --description "Clean source docs, create a KB, run test questions, and submit a delivery report." \
  --owner-agent-id agt_remote_builder \
  --priority high \
  --risk medium \
  --acceptance "Worker must write run, tool call, evaluation and audit evidence."
```

Then the same remote worker can consume it:

```bash
agentops-worker --once --adapter mock --agent-id agt_remote_builder
```

For a one-command local/customer execution, use:

```bash
agentops workflow run-task \
  --adapter mock \
  --worker-agent-id agt_remote_builder \
  --title "Build a knowledge-base Q&A bot" \
  --description "Clean source docs, create a KB, run test questions, and submit a delivery report."
```

This creates the task through Agent Gateway, executes one worker iteration, and
returns `task_id`, `run_id`, status, and evidence counts. Hermes/OpenClaw still
require explicit `--confirm-run`.

For scoped remote tokens, `agentops task create` maps to
`POST /api/agent-gateway/tasks` and requires `tasks:create`. The Gateway binds
the created task to the token's own `agent_id` and `workspace_id`; attempts to
assign work as another agent or another workspace are rejected with `403`.

## Customer Task API Path

For product dogfooding or customer-facing demos, use the workflow endpoint
instead of manually creating worker tasks:

```bash
curl -fsS -X POST http://127.0.0.1:8787/api/workflows/customer-worker-task \
  -H "Content-Type: application/json" \
  -d '{
    "adapter": "mock",
    "title": "Improve the AgentOps MIS customer workspace",
    "description": "Use the worker loop to produce product recommendations.",
    "acceptance_criteria": "Write run, tool, evaluation, audit and artifact evidence."
  }' | jq .
```

For local live Hermes/OpenClaw dogfood:

```bash
python3 scripts/customer_worker_live_dogfood.py --adapter hermes
python3 scripts/customer_worker_live_dogfood.py --adapter openclaw
```

This path creates a normal MIS task, executes through the worker adapter, and
returns the `run_id`, `artifact_id`, and evidence counts. Hermes/OpenClaw live
execution still requires explicit confirmation inside the workflow call.

## Revocation And Rotation

List enrollments and sessions:

```bash
agentops enrollment list
agentops session list
```

Revoke one session:

```bash
agentops session revoke --session-id <session_id>
```

Revoke or rotate an enrollment token:

```bash
agentops enrollment revoke --agent-id agt_remote_builder
agentops enrollment rotate --agent-id agt_remote_builder
```

Revoking an enrollment also invalidates active child sessions.

## Acceptance Checks

Use these lightweight checks before a demo or customer handoff:

```bash
python3 -m py_compile server.py scripts/*.py agentops_mis_cli/*.py
python3 scripts/agentops_worker_preflight_smoke.py
python3 scripts/worker_live_confirm_gate_smoke.py
python3 scripts/remote_launch_packet_worker_smoke.py
python3 scripts/agent_gateway_task_create_scope_smoke.py
python3 scripts/agentops_workflow_run_task_smoke.py
python3 scripts/demo_acceptance.py
git diff --check
```

The expected proof is:

- `agentops worker preflight` returns JSON and `live_execution_performed=false`.
- `agentops worker service-check` returns JSON, omits raw service content, and
  detects token-like values without printing them.
- Hermes/OpenClaw daemon starts without `--confirm-run` fail closed.
- Remote launch packet commands can create ledger evidence through Agent Gateway.
- Scoped task creation requires `tasks:create` and rejects agent/workspace impersonation.
- `agentops workflow run-task` creates a task, executes one worker iteration, and returns evidence.
- Demo acceptance remains safe and reproducible.
