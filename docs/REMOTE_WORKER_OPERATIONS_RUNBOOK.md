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
python3 scripts/demo_acceptance.py
git diff --check
```

The expected proof is:

- `agentops worker preflight` returns JSON and `live_execution_performed=false`.
- Hermes/OpenClaw daemon starts without `--confirm-run` fail closed.
- Remote launch packet commands can create ledger evidence through Agent Gateway.
- Demo acceptance remains safe and reproducible.
