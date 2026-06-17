# AgentOps MIS v1.5 Agent Worker Loop Spec

## Goal

Turn the current Agent Gateway protocol into a runnable local execution loop: a worker can pull MIS tasks, claim them, execute through a selected local adapter, and write run/tool/evaluation/audit evidence back into MIS.

## Scope: the Eight Non-Dify/Notion Gaps

This v1.5 track intentionally excludes Dify and Notion live sync. Those remain separate connector tracks.

The consolidated product closure spec is `docs/V1_5_EIGHT_PRODUCT_CLOSURE_SPEC.md`.

1. Long-running Agent Worker
   - v1.5 must provide a repo-local worker daemon script.
   - It must support both `--once` and loop mode.
   - It must use Agent Gateway API, not direct SQLite writes.
   - v1.5.1 adds local start/stop/status supervision for the repo-local worker process.

2. OpenClaw/Hermes Adapter Loop
   - v1.5 must support at least `mock`, `hermes`, and `openclaw` adapters.
   - The worker must map one MIS task to one run and record tool/eval/audit evidence.
   - Live runtime execution must require explicit opt-in.

3. Repo-Local CLI, Not Install Package Yet
   - v1.5 keeps `./scripts/agentops` and `scripts/agent_worker.py` as repo-local tools.
   - Packaging as `agentops` global CLI is v1.6+.

4. Remote Agent Entry Shape
   - v1.5 worker must be API-first so the same loop can run on another machine later.
   - v1.5.2 adds minimal token enrollment APIs for remote/local workers.
   - Token issuance, revocation, heartbeat freshness, and scope checks are supported.
   - Enrollment UI, reconnection policy, and production fleet management remain v1.6+.

5. MVP Security Boundary
   - v1.5 keeps local token/API key behavior and adds per-agent bearer tokens.
   - Raw prompts, raw responses, credentials, private messages, and full transcripts must not be stored.
   - Tool args must be summaries or hashes.
   - High-risk operations should not run automatically.

6. UI Operation Loop
   - v1.5 adds a minimal worker status and one-shot dispatch panel in the AI Employees page.
   - The UI can trigger `mock`, `hermes`, or `openclaw` single-run workers.
   - v1.5.1 adds daemon start/stop controls for local recording and self-use.
   - The evidence must appear in existing task/run/tool/evaluation/audit pages.
   - Production-grade service management, restart policy, and remote worker fleets remain v1.6+.

7. Customer-Task Usefulness
   - v1.5 worker output must be useful enough for a customer task summary.
   - It may use fixed safe adapter prompts or a redacted task summary, depending on adapter policy.

8. Productization Track
   - v1.5 does not add hosted server mode, billing, installer, backup/restore, or full monitoring.
   - It must preserve a clear path to those features by keeping the worker API-first.

## Worker Contract

Command:

```bash
python3 scripts/agent_worker.py --once --adapter hermes --confirm-run
python3 scripts/agent_worker.py --adapter mock --poll-interval 5 --max-tasks 10
```

Environment:

```text
AGENTOPS_BASE_URL=http://127.0.0.1:8787
AGENTOPS_WORKSPACE_ID=local-demo
AGENTOPS_AGENT_ID=agt_worker_local
AGENTOPS_API_KEY=
```

Task selection:

- Pull tasks through `GET /api/agent-gateway/tasks/pull`.
- Default statuses: `planned`.
- Claim through `POST /api/agent-gateway/tasks/:id/claim`.
- Start run through `POST /api/agent-gateway/runs/start`.

Adapter execution:

- `mock`: deterministic local summary, no external runtime.
- `hermes`: calls `POST /api/integrations/hermes/run-task` with `confirm_run:true` only when worker gets `--confirm-run`.
- `openclaw`: calls `POST /api/integrations/openclaw/probe` only when worker gets `--confirm-run`.

Writeback:

- Record one tool call describing the selected adapter and outcome.
- Complete or fail the run with a redacted output summary.
- Submit an evaluation.
- Emit an audit event.
- Optionally propose one memory candidate only for stable operational lessons or failures.

## Worker Status / Dispatch API

The browser UI stays a human control surface. It does not execute adapter logic directly; it asks the backend to create a normal MIS task and run the repo-local worker once.

Endpoints:

```http
GET  /api/workers/status
GET  /api/workers/local/logs?adapter=mock
POST /api/workers/local/dispatch-once
POST /api/workers/local/start
POST /api/workers/local/stop
```

`GET /api/workers/status` returns local daemon status, recent worker agents, worker-owned tasks, worker runs, and Agent Gateway runtime events.

`POST /api/workers/local/dispatch-once` accepts:

```json
{
  "adapter": "mock",
  "confirm_run": false,
  "title": "worker UI dispatch task",
  "description": "short redacted task summary",
  "acceptance_criteria": "short acceptance summary"
}
```

Behavior:

- Creates a normal planned task with a worker owner agent.
- Registers the worker agent through the same gateway agent path.
- Runs `scripts/agent_worker.py --once`.
- Requires `confirm_run:true` for Hermes/OpenClaw live adapter execution.
- Writes audit for dispatch task creation and dispatch completion.

`POST /api/workers/local/start` starts the repo-local worker in loop mode:

```json
{
  "adapter": "mock",
  "poll_interval": 2,
  "max_tasks": 0,
  "confirm_run": false
}
```

Behavior:

- Writes pid/log metadata to `.agentops_runtime/workers/`, which is gitignored.
- Uses `scripts/agent_worker.py --adapter ... --max-tasks ...`.
- `max_tasks:0` means keep polling until explicitly stopped.
- Hermes/OpenClaw daemon start requires `confirm_run:true`.
- Duplicate starts are idempotent if the daemon is already running.

`POST /api/workers/local/stop` stops one adapter or all adapters:

```json
{ "adapter": "all" }
```

Behavior:

- Sends `SIGTERM`, then `SIGKILL` only if the process does not exit.
- Reaps completed child processes and treats zombies as stopped.
- Writes runtime event and audit evidence for stop actions.

## Agent Gateway Enrollment API

The enrollment API lets a local or remote worker get a scoped token without storing raw credentials in the MIS ledger. The server stores only a hash.

Endpoints:

```http
GET  /api/agent-gateway/enrollments
POST /api/agent-gateway/enrollment/create
POST /api/agent-gateway/enrollment/revoke
```

Create request:

```json
{
  "workspace_id": "local-demo",
  "agent_id": "agt_remote_builder",
  "name": "Remote Builder",
  "runtime_type": "openclaw",
  "scopes": [
    "agents:write",
    "agents:heartbeat",
    "tasks:read",
    "tasks:claim",
    "runs:write",
    "toolcalls:write",
    "evaluations:submit",
    "audit:write"
  ],
  "ttl_days": 30,
  "heartbeat_timeout_sec": 300
}
```

Behavior:

- Creates or ensures the agent identity.
- Returns the bearer token once.
- Stores only `token_hash`, status, scope list, expiry, and heartbeat timestamps.
- A token can only act as its bound `agent_id`.
- Every gateway endpoint checks the required scope.
- `GET /api/agent-gateway/enrollments` reports `fresh`, `stale`, or `never_seen` heartbeat state.

## Acceptance

Minimum acceptance for v1.5 worker loop:

1. `python3 -m py_compile server.py scripts/*.py` passes.
2. `git diff --check` passes.
3. A planned MIS task can be created for the worker.
4. `python3 scripts/agent_worker.py --once --adapter mock` completes that task and writes run/tool/eval/audit.
5. `python3 scripts/agent_worker.py --once --adapter hermes --confirm-run` can complete a task when local Hermes gateway is live.
6. `python3 scripts/agent_worker.py --once --adapter openclaw --confirm-run` can complete a task when OpenClaw CLI is live.
7. `/workspace/agents` can trigger one mock worker run from the browser and the run appears in run/tool/eval/audit ledgers.
8. `/workspace/agents` can start and stop a mock daemon; status shows running while the process is alive.
9. A daemon can pull a newly planned task and complete it without a one-shot dispatch call.
10. A scoped token can heartbeat and pull tasks, while a token missing `tasks:read` is rejected for task pull.
11. `python3 scripts/remote_agent_token_worker_smoke.py` can use a scoped token to run a worker end-to-end and revoke the token.
12. Revoked tokens are rejected.
13. Dify and Notion endpoints are not called by this worker.

## Known Limitations

- No global package install.
- Local daemon supervision is repo-local and process-based; no launchd/systemd unit.
- No remote enrollment UI.
- Scope enforcement is minimal endpoint-level enforcement, not full RBAC/workspace isolation.
- UI controls are local self-use/recording controls, not a production fleet manager.
- Hermes/OpenClaw execution is still fixed safe adapter execution, not arbitrary prompt automation.
- Long-form customer deliverables need a later artifact pipeline.
