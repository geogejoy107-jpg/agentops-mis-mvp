# AgentOps MIS v1.5 Agent Worker Loop Spec

## Goal

Turn the current Agent Gateway protocol into a runnable local execution loop: a worker can pull MIS tasks, claim them, execute through a selected local adapter, and write run/tool/evaluation/audit evidence back into MIS.

## Scope: the Eight Non-Dify/Notion Gaps

This v1.5 track intentionally excludes Dify and Notion live sync. Those remain separate connector tracks.

1. Long-running Agent Worker
   - v1.5 must provide a repo-local worker daemon script.
   - It must support both `--once` and loop mode.
   - It must use Agent Gateway API, not direct SQLite writes.

2. OpenClaw/Hermes Adapter Loop
   - v1.5 must support at least `mock`, `hermes`, and `openclaw` adapters.
   - The worker must map one MIS task to one run and record tool/eval/audit evidence.
   - Live runtime execution must require explicit opt-in.

3. Repo-Local CLI, Not Install Package Yet
   - v1.5 keeps `./scripts/agentops` and `scripts/agent_worker.py` as repo-local tools.
   - Packaging as `agentops` global CLI is v1.6+.

4. Remote Agent Entry Shape
   - v1.5 worker must be API-first so the same loop can run on another machine later.
   - v1.5 does not implement enrollment UI, token issuance, revocation, or reconnection policy.

5. MVP Security Boundary
   - v1.5 keeps local token/API key behavior.
   - Raw prompts, raw responses, credentials, private messages, and full transcripts must not be stored.
   - Tool args must be summaries or hashes.
   - High-risk operations should not run automatically.

6. UI Operation Loop
   - v1.5 adds a minimal worker status and one-shot dispatch panel in the AI Employees page.
   - The UI can trigger `mock`, `hermes`, or `openclaw` single-run workers.
   - The evidence must appear in existing task/run/tool/evaluation/audit pages.
   - Full start/stop daemon supervision remains v1.6+.

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
POST /api/workers/local/dispatch-once
```

`GET /api/workers/status` returns recent worker agents, worker-owned tasks, worker runs, and Agent Gateway runtime events.

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

## Acceptance

Minimum acceptance for v1.5 worker loop:

1. `python3 -m py_compile server.py scripts/*.py` passes.
2. `git diff --check` passes.
3. A planned MIS task can be created for the worker.
4. `python3 scripts/agent_worker.py --once --adapter mock` completes that task and writes run/tool/eval/audit.
5. `python3 scripts/agent_worker.py --once --adapter hermes --confirm-run` can complete a task when local Hermes gateway is live.
6. `python3 scripts/agent_worker.py --once --adapter openclaw --confirm-run` can complete a task when OpenClaw CLI is live.
7. `/workspace/agents` can trigger one mock worker run from the browser and the run appears in run/tool/eval/audit ledgers.
8. Dify and Notion endpoints are not called by this worker.

## Known Limitations

- No global package install.
- No daemon supervisor or launchd unit.
- No remote enrollment UI.
- No per-agent scope enforcement beyond existing MVP API key boundary.
- UI controls are one-shot dispatch controls, not a persistent worker process manager.
- Hermes/OpenClaw execution is still fixed safe adapter execution, not arbitrary prompt automation.
- Long-form customer deliverables need a later artifact pipeline.
