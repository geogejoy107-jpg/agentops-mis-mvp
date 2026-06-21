# Agent Gateway CLI Spec

## Purpose

The Agent Gateway is the machine-facing layer that lets local and remote AI agents participate in AgentOps MIS without pretending to be human browser users.

Browser UI is for humans. CLI, API, and MCP are for agents.

## Why Browser UI Is For Humans

The browser UI is optimized for judgment, review, and supervision:

- Create or edit high-level goals.
- Inspect task queues and agent performance.
- Review approvals.
- Read reports.
- Inspect audit trails.
- Watch Pixel Office status.

Agents should not depend on browser clicks to do their work. Browser automation is brittle, hard to audit, and easy to confuse with human intent.

## Why CLI/API/MCP Is For Agents

Agents need stable machine contracts:

- Pull a task.
- Claim ownership.
- Start a run.
- Send heartbeat.
- Record tool calls.
- Request approval.
- Submit output summaries.
- Propose memory.
- Submit evaluations.
- Emit audit events.

The Agent Gateway makes these operations explicit, scoped, replayable, and auditable.

## Local Debugging And Secrets Policy

Local debugging is allowed and expected in v1.4, especially for OpenClaw, Hermes, Dify, OpenAI File Search, and remote agents. The rule is: debug locally, never persist raw secrets.

For local debug:

- Use environment variables, local config files, or OS keychain-style storage for API keys.
- Never commit `.env`, local tokens, local SQLite databases, runtime logs with credentials, or raw customer files.
- Never store full prompts, private chats, raw responses, or credentials in `runs`, `tool_calls`, `audit_logs`, or memory.
- Store summaries, hashes, IDs, timestamps, status, duration, cost, and scoped metadata.
- Redact request/response previews before writing them to MIS.
- Use `confirm_run:true` or an equivalent explicit flag for real runtime actions.
- Keep dry-run as the default for demos and cloned repos.

Example local environment names for future use:

```text
AGENTOPS_BASE_URL=http://127.0.0.1:8787
AGENTOPS_WORKSPACE_ID=local_demo
AGENTOPS_AGENT_ID=agt_local_researcher
AGENTOPS_API_KEY=local_dev_only_do_not_commit
```

## CLI Commands

The CLI should be a thin wrapper over the Agent Gateway API. It should return JSON by default so agents can parse it.

Current local MVP implementation:

```bash
./scripts/agentops --help
python3 -m pip install -e .
python3 -m pip install .
agentops --help
agentops doctor
./scripts/agentops login --base-url http://127.0.0.1:8787 --workspace-id local-demo --agent-id agt_local_worker
./scripts/agentops status
./scripts/agentops enrollment create --agent-id agt_remote_builder --name "Remote Builder" --runtime openclaw
```

The implementation lives in `agentops_mis_cli/agentops.py`, with `scripts/agentops` as a repo-local compatibility wrapper. `pyproject.toml` also exposes the same command through the `agentops-mis-cli` Python console script for pip source installs on local or remote agent machines. It uses only Python standard library modules, includes a tiny offline build backend, and reads configuration from environment variables or `~/.agentops/config.json`.

### `agentops login`

Stores a local API key or local token for the current workspace.

```bash
agentops login --base-url http://127.0.0.1:8787 --workspace-id local-demo
```

v1.4 can support environment-variable auth only. Interactive login is optional.

### `agentops status`

Checks Agent Gateway connectivity and safe auth metadata without pulling tasks or starting runs.

```bash
agentops status
```

With a scoped remote-agent token, status returns the auth mode, bound `agent_id`, bound `workspace_id`, allowed scopes, token id, expiry, and heartbeat state. It never returns the raw token or token hash.

### `agentops doctor`

Runs a read-only setup diagnostic for local and remote agent machines.

It reports:

- resolved base URL, workspace, agent id, and config path;
- whether an API key/session token is present without printing it;
- auth source category: flag, env, config, default, or missing;
- Agent Gateway status and token omission proof;
- worker provider status, worker count, running workers, pending tasks, and stuck tasks;
- setup hints for missing token, missing agent id, rejected token, or stuck worker recovery.

```bash
agentops doctor
AGENTOPS_API_KEY=agtok_... AGENTOPS_AGENT_ID=agt_remote_builder agentops doctor
```

### `agentops agent register`

Registers or updates an AI digital employee identity.

```bash
agentops agent register \
  --agent-id agt_kb_researcher \
  --name "Knowledge Base Researcher" \
  --role researcher \
  --runtime openclaw \
  --scope tasks:read,runs:write,toolcalls:write,artifacts:write,approvals:request
```

Maps to `agents`.

### `agentops enrollment create`

Creates a scoped bearer token for a local or remote agent. The token is shown once; MIS stores only a hash.

```bash
agentops enrollment create \
  --agent-id agt_remote_builder \
  --name "Remote Builder" \
  --runtime openclaw \
  --scopes agents:write,agents:heartbeat,tasks:create,tasks:read,tasks:claim,runs:write,toolcalls:write,artifacts:write,evaluations:submit,audit:write \
  --ttl-days 30
```

Optional:

```bash
agentops enrollment create --agent-id agt_local_worker --name "Local Worker" --save-token
```

`--save-token` writes the returned token to the local CLI config for this machine only.

The create response also includes a `next_steps` launch packet for the remote machine:

- environment variables for `AGENTOPS_BASE_URL`, `AGENTOPS_WORKSPACE_ID`, and `AGENTOPS_AGENT_ID`
- a placeholder for `AGENTOPS_API_KEY`, never the raw token embedded in a command
- `agentops status`
- `agentops-worker preflight`
- `agentops worker preflight`
- `agentops agent heartbeat`
- one-shot `agentops-worker --once`
- loop-mode `agentops-worker --max-tasks 0 --continue-on-error`
- launchd/systemd service template generation through `agentops-worker service-template`
- dry-run-by-default service file installation through `agentops-worker service-install`
- read-only service diagnostics through `agentops-worker service-check`
- repo-local fallback commands using `python3 scripts/agent_worker.py ...`

This packet is safe to display in the UI because it omits the token value from command strings.

### `agentops enrollment request`

Creates a human approval request before any remote-agent token is issued. This is the safer customer-facing path for unknown machines or contractors.

```bash
agentops enrollment request \
  --agent-id agt_customer_worker \
  --name "Customer Worker" \
  --runtime mock \
  --scopes agents:heartbeat,tasks:create,tasks:read,tasks:claim,runs:write,toolcalls:write,evaluations:submit,audit:write \
  --reason "Customer server worker needs to process assigned MIS tasks"
```

The response includes `request_id`, `approval_id`, `task_id`, and `run_id`, but no token.

### `agentops enrollment issue-approved`

Issues a one-time-visible token only after the linked approval has been approved.

```bash
agentops enrollment issue-approved --approval-id ap_123
```

Maps to `agent_gateway_enrollment_requests`, `approvals`, `tasks`, `runs`, `audit_logs`, and then `agent_gateway_tokens`.

### `agentops enrollment list`

Lists token metadata, status, scopes, expiry, and heartbeat freshness. It never prints token secrets.

```bash
agentops enrollment list
```

Heartbeat freshness uses product-facing lifecycle states:

- `never_seen`: token was issued but the remote worker has not connected yet.
- `fresh`: token is active and the latest heartbeat is inside the timeout window.
- `stale`: token is active but the latest heartbeat is older than the timeout window.
- `revoked`: token is no longer valid and should not be shown as live even if it has old heartbeat data.

### `agentops enrollment revoke`

Revokes one token or all active tokens for an agent.

```bash
agentops enrollment revoke --token-id agtok_...
agentops enrollment revoke --agent-id agt_remote_builder
```

### `agentops enrollment rotate`

Revokes an active token and issues a replacement token with the same agent binding and scopes by default. The replacement token is shown once; MIS stores only a hash.

```bash
agentops enrollment rotate --token-id agtok_...
agentops enrollment rotate --agent-id agt_remote_builder --ttl-days 30 --save-token
```

Optional `--scopes` can narrow or replace the previous scope list during rotation.

### `agentops agent heartbeat`

Reports liveness, runtime, current task, and safe status metadata.

```bash
agentops agent heartbeat --agent-id agt_kb_researcher --status running
```

Maps to `agents` and `audit_logs`.

### `agentops task create`

Creates a normal MIS task that local or remote agents can pull through the
Gateway. This is the customer/API-facing path when an external system wants to
assign work without using the browser UI.

```bash
agentops task create \
  --title "Build a knowledge-base Q&A bot" \
  --description "Clean source material, build the KB, run test questions, and submit a delivery report." \
  --owner-agent-id agt_kb_researcher \
  --priority high \
  --risk medium \
  --acceptance "Worker must write run, tool call, evaluation and audit evidence."
```

Maps to `POST /api/agent-gateway/tasks` for CLI/remote-agent use, writes
`tasks`, `runtime_events`, and `audit_logs`, and returns JSON with `operation`,
`outcome`, `task_id`, and the redacted task row. Scoped tokens require
`tasks:create` and cannot create tasks as another agent or workspace. Repeated
calls with the same `task_id` update the same task instead of creating
duplicates.

### `agentops task pull`

Returns available tasks for the agent based on role, scope, and workspace policy.

```bash
agentops task pull --agent-id agt_kb_researcher --limit 5
```

Reads from `tasks`.

### `agentops task claim`

Claims a task for an agent.

```bash
agentops task claim --task-id tsk_clean_sources --agent-id agt_doc_cleaner
```

Updates `tasks` and writes `audit_logs`.

### `agentops run start`

Starts a run for a claimed task.

```bash
agentops run start --task-id tsk_clean_sources --agent-id agt_doc_cleaner --runtime hermes
```

Maps to `runs`.

### `agentops run heartbeat`

Updates run progress without storing full private output.

```bash
agentops run heartbeat --run-id run_123 --status running --summary "Cleaned 4 source files"
```

Maps to `runs` and optionally `audit_logs`.

### `agentops toolcall record`

Records a tool call summary, risk level, duration, status, and redacted metadata.

```bash
agentops toolcall record \
  --run-id run_123 \
  --tool browser.search \
  --status completed \
  --risk low \
  --summary "Checked Dify knowledge-base import docs"
```

Maps to `tool_calls`.

### `agentops approval request`

Requests human approval for a risky operation.

```bash
agentops approval request \
  --run-id run_123 \
  --task-id tsk_upload_sources \
  --risk high \
  --reason "Upload customer PDFs to Dify knowledge base"
```

Maps to `approvals` and `audit_logs`.

### `agentops memory propose`

Creates a reviewable memory candidate.

```bash
agentops memory propose \
  --task-id tsk_eval_retrieval \
  --type evaluation_finding \
  --text "OpenAI File Search needs source metadata for reliable citations"
```

Maps to `memories`.

### `agentops eval submit`

Submits an evaluation result for a run, artifact, or task.

```bash
agentops eval submit \
  --run-id run_123 \
  --gate citation_grounding \
  --score 86 \
  --pass true \
  --notes "Answers cite the uploaded course notes in 8/10 checks"
```

Maps to `evaluations`.

### `agentops audit emit`

Emits a structured audit event for important state transitions.

```bash
agentops audit emit \
  --actor-type agent \
  --actor-id agt_kb_researcher \
  --action connector.plan_created \
  --entity-type task \
  --entity-id tsk_kb_setup
```

Maps to `audit_logs`.

### `agentops workflow templates`

Lists customer-facing workflow templates in JSON for humans, scripts, or
external agents. This is the machine-readable version of the Pixel Office
template picker.

```bash
agentops workflow templates
```

Maps to `GET /api/workflows/customer-task-templates`. It is read-only and must
not print raw tokens, credentials, private transcripts, or customer documents.

### `agentops workflow run-template`

Runs a selected customer workflow template through the same MIS workflow layer
used by Pixel Office. This is the preferred CLI/API path when a customer or
external agent wants to launch a predefined delivery workflow without operating
the browser UI.

```bash
agentops workflow run-template \
  --template-id tpl_customer_kb_qa_bot \
  --title "Build a formal AI knowledge-base Q&A bot" \
  --description "Clean source docs, prepare the KB workflow, run test questions, and submit a delivery report."
```

Maps to `POST /api/workflows/customer-task-templates/run` and returns
`project_id`, `task_id`, `run_id`, `artifact_id`, pending approval ids, and a
customer report URL when available. The command stores only safe summaries,
hashes, and ledger ids; it must not print or persist raw customer documents,
full prompts, full model responses, tokens, or credentials.

Templates can also be dispatched through the real Agent Worker adapter loop:

```bash
agentops workflow run-template \
  --template-id tpl_customer_ui_review \
  --adapter openclaw \
  --confirm-run \
  --request-timeout 420 \
  --title "Optimize the AgentOps MIS customer workspace"
```

Without `--adapter`, the template uses its default safe workflow. With
`--adapter mock|hermes|openclaw`, it maps the template defaults into
`POST /api/workflows/customer-worker-task`, executes through the worker loop,
and returns run/tool/evaluation/audit/artifact/memory/approval evidence. Hermes
and OpenClaw require `--confirm-run`; without confirmation the command creates
a planned task and returns `confirm_run_required_for_live_adapter`.

Long live runs can exceed the default CLI HTTP timeout. Use
`--request-timeout` or `AGENTOPS_REQUEST_TIMEOUT`; the CLI automatically raises
the timeout for confirmed Hermes/OpenClaw template runs.

For customer or remote-agent use, long template runs can be submitted as a
workflow job and polled instead of holding one HTTP request open:

```bash
agentops workflow run-template \
  --template-id tpl_customer_ui_review \
  --adapter hermes \
  --confirm-run \
  --async-job

agentops workflow job-status --job-id wfjob_... --wait --timeout 420
```

`--async-job` maps to `POST /api/workflows/customer-task-templates/submit`.
`job-status` maps to `GET /api/workflows/jobs/:job_id`. The job record stores
status, request hash, safe summaries, result ids, and token omission metadata;
it must not store raw prompts, raw documents, credentials, or token values.

### `agentops workflow customer-worker-task`

Dispatches a customer-facing task through the AgentOps worker loop. This is the
CLI/API shape for the product usage model where a customer or external agent
sends work to the MIS, and the AI digital employee uses Agent Gateway/worker to
execute it.

```bash
agentops workflow customer-worker-task \
  --adapter mock \
  --title "Improve the customer workspace" \
  --description "Review task creation, AI execution, approval, evaluation, audit and delivery report flow." \
  --acceptance "Return run, tool, evaluation, audit and artifact evidence."
```

Hermes/OpenClaw live execution still requires explicit confirmation:

```bash
agentops workflow customer-worker-task \
  --adapter openclaw \
  --confirm-run \
  --title "Optimize AgentOps MIS customer workspace" \
  --description "Use local OpenClaw to produce product recommendations."
```

Maps to `POST /api/workflows/customer-worker-task` and returns `task_id`,
`run_id`, `artifact_id`, and evidence counts. It must not print raw tokens,
full prompts, full raw model responses, credentials, or private transcripts.

For real Hermes/OpenClaw work or any customer task that may run longer than a
short HTTP request, submit it as an async workflow job:

```bash
agentops workflow customer-worker-task \
  --adapter openclaw \
  --confirm-run \
  --async-job \
  --title "Optimize AgentOps MIS customer workspace" \
  --description "Use local OpenClaw to produce product recommendations."

agentops workflow job-status --job-id wfjob_... --wait --timeout 420
```

`--async-job` maps to `POST /api/workflows/customer-worker-task/submit`.
The job starts quickly, records request hash and safe summaries, and later
stores `result_task_id`, `result_run_id`, `result_artifact_id`, status, and safe
result JSON. This is the preferred product path for customer-visible long
runtime work because the browser and CLI can observe status without pretending
the agent is a human UI user or holding a fragile synchronous request open.

Workflow job recovery commands:

```bash
agentops workflow stuck-jobs --threshold-sec 900 --limit 25
agentops workflow job-mark-failed \
  --job-id wfjob_... \
  --reason "Gateway process died during live run; operator reviewed ledger."
```

`stuck-jobs` maps to `GET /api/workflows/jobs/stuck`. `job-mark-failed` maps to
`POST /api/workflows/jobs/:job_id/mark-failed`. This is an operator recovery
path for jobs left in `queued` or `running` after a server restart, runtime
crash, or gateway disconnect. It does not delete evidence or claim success; it
marks the job failed and writes runtime/audit evidence.

### `agentops workflow run-task`

Creates a normal MIS task through the scoped Agent Gateway path, executes one
local worker iteration, then returns the task/run ids plus tool/evaluation
evidence. This is the compact CLI path for a customer, script, or external
agent that wants one command instead of manually chaining `task create` and
`agentops-worker --once`.

```bash
agentops workflow run-task \
  --adapter mock \
  --worker-agent-id agt_remote_builder \
  --title "Improve the customer workspace" \
  --description "Review task creation, AI execution, approval, evaluation, audit and delivery report flow."
```

Hermes/OpenClaw live execution still requires explicit confirmation:

```bash
agentops workflow run-task \
  --adapter openclaw \
  --confirm-run \
  --worker-agent-id agt_openclaw_builder \
  --title "Optimize AgentOps MIS customer workspace" \
  --description "Use local OpenClaw to produce product recommendations."
```

The command returns JSON with `task_id`, `run_id`, `run_status`,
`task_status`, `evidence`, and `token_omitted:true`. It must not print raw
tokens, full prompts, full raw model responses, credentials, or private
transcripts. Without `--confirm-run`, Hermes/OpenClaw create a planned task but
do not execute the live adapter.

### `agentops worker status`

Returns the same safe worker fleet summary used by `/workspace/agents`: worker count, running workers, pending worker tasks, stuck worker tasks, daemon state, recent worker runs, and recent Gateway events.

```bash
agentops worker status
```

It is read-only and does not print raw tokens.

### `agentops worker preflight`

Runs read-only Gateway and adapter readiness checks from the main operator CLI.
It does not pull a task, claim work, start a run, execute a runtime, or write
ledger rows.

```bash
agentops worker preflight --adapter mock
agentops worker preflight --adapter hermes
agentops worker preflight --adapter openclaw
```

For Hermes it checks the configured OpenAI-compatible gateway health/models
endpoints. For OpenClaw it checks whether the binary is present and executable,
and attempts a version read only. The result includes
`live_execution_performed:false`.

### `agentops worker start`

Starts a local worker daemon through the MIS supervisor. `mock` can start directly; `hermes` and `openclaw` require explicit `--confirm-run`.

```bash
agentops worker start --adapter mock --poll-interval 5 --max-tasks 0
agentops worker start --adapter hermes --confirm-run --poll-interval 5 --max-tasks 0
```

Maps to `POST /api/workers/local/start`.

### `agentops worker logs`

Returns daemon metadata and a bounded log tail for one adapter.

```bash
agentops worker logs --adapter mock
```

Maps to `GET /api/workers/local/logs`.

### `agentops worker stop`

Stops one local daemon or all local daemons.

```bash
agentops worker stop --adapter mock
agentops worker stop --adapter all
```

Maps to `POST /api/workers/local/stop`.

### `agentops worker stuck`

Lists running worker tasks that exceeded the local recovery threshold. This is an operator view; it does not expose prompts, responses, or tokens.

```bash
agentops worker stuck --threshold-sec 900 --limit 25
```

Maps to `GET /api/workers/stuck-tasks`.

### `agentops worker release`

Releases a stuck running task back to `planned` and blocks any linked running run with `WorkerTaskReleased`.

```bash
agentops worker release --task-id tsk_... --reason "operator recovery"
```

Maps to `POST /api/workers/tasks/release` and writes runtime/audit evidence.

### `agentops session create`

Mints a short-lived session token from a scoped enrollment token. The session inherits the bound `agent_id`, `workspace_id`, and a scope subset. It is shown once; MIS stores only a hash.

```bash
agentops session create \
  --ttl-sec 900 \
  --scopes agents:heartbeat,tasks:read,runs:write,toolcalls:write,evaluations:submit,audit:write
```

Session tokens cannot mint more sessions. They are for worker loops, not for browser users.

### `agentops session list`

Lists short-lived session metadata without secrets.

```bash
agentops session list
```

Maps to `GET /api/agent-gateway/sessions`. The response omits `session_hash` and raw token values.

### `agentops session revoke`

Revokes one short-lived session or all active sessions for one agent.

```bash
agentops session revoke --session-id agtsess_...
agentops session revoke --agent-id agt_remote_builder
```

Maps to `POST /api/agent-gateway/session/revoke` and writes runtime/audit evidence.

## API Endpoint Proposal

All endpoints are under the existing local API server.

```http
GET  /api/agent-gateway/enrollments
GET  /api/agent-gateway/sessions
GET  /api/agent-gateway/status
POST /api/agent-gateway/enrollment/create
POST /api/agent-gateway/enrollment/request
POST /api/agent-gateway/enrollment/issue-approved
POST /api/agent-gateway/enrollment/revoke
POST /api/agent-gateway/enrollment/rotate
POST /api/agent-gateway/session/create
POST /api/agent-gateway/session/revoke
POST /api/agent-gateway/register
POST /api/agent-gateway/heartbeat
GET  /api/agent-gateway/tasks/pull
POST /api/agent-gateway/tasks/:id/claim
POST /api/agent-gateway/runs/start
POST /api/agent-gateway/runs/:id/heartbeat
POST /api/agent-gateway/tool-calls
POST /api/agent-gateway/artifacts
POST /api/agent-gateway/approvals/request
POST /api/agent-gateway/memories/propose
POST /api/agent-gateway/evaluations/submit
POST /api/agent-gateway/audit
```

### Common Request Fields

Every write endpoint should accept or infer:

```json
{
  "workspace_id": "local_demo",
  "agent_id": "agt_kb_researcher",
  "runtime_type": "openclaw",
  "request_id": "optional_idempotency_key"
}
```

### `GET /api/agent-gateway/status`

Returns safe gateway readiness and auth metadata for local or remote agents.

Reads:

- `agent_gateway_tokens`
- `agents`

Never returns:

- raw token value
- token hash
- full prompts or raw outputs

### `POST /api/agent-gateway/register`

Creates or updates an agent identity.

Writes:

- `agents`
- `audit_logs`

### `POST /api/agent-gateway/heartbeat`

Updates liveness and current work state.

Writes:

- `agents`
- `audit_logs` for meaningful state changes only

### `GET /api/agent-gateway/tasks/pull`

Returns tasks matching agent scope, role, and status.

Reads:

- `tasks`
- `agents`
- future policy tables

### `POST /api/agent-gateway/tasks/:id/claim`

Assigns a task to the caller when allowed.

Writes:

- `tasks`
- `audit_logs`

### `POST /api/agent-gateway/runs/start`

Creates a run for an agent and task.

Writes:

- `runs`
- `audit_logs`

### `POST /api/agent-gateway/runs/:id/heartbeat`

Updates run status, duration, safe output summary, and progress metadata.

Writes:

- `runs`
- `audit_logs` for important transitions

### `POST /api/agent-gateway/tool-calls`

Records tool-call evidence.

Writes:

- `tool_calls`
- `approvals` when policy requires approval
- `audit_logs`

### `POST /api/agent-gateway/artifacts`

Records a delivery artifact summary without storing raw customer content.

Writes:

- `artifacts`
- `runtime_events`
- `audit_logs`

### `agentops artifact record`

Records a customer-readable artifact reference after a run, while keeping the full artifact body in the customer-approved system of record.

```bash
agentops artifact record \
  --run-id run_123 \
  --title "Knowledge-base bot delivery summary" \
  --type customer_delivery_report \
  --uri agentops://kb-bot-demo/project/delivery-summary \
  --summary "Delivered task plan, connector decision, QA rubric and pending external upload approval."
```

Maps to `artifacts`, `runtime_events`, and `audit_logs`.

### `POST /api/agent-gateway/approvals/request`

Creates a human approval request.

Writes:

- `approvals`
- `audit_logs`

### `POST /api/agent-gateway/memories/propose`

Creates a candidate memory, never an auto-approved memory.

Writes:

- `memories`
- `audit_logs`

### `POST /api/agent-gateway/evaluations/submit`

Submits quality-gate output.

Writes:

- `evaluations`
- `audit_logs`

### `POST /api/agent-gateway/audit`

Emits a direct audit event for state transitions that do not fit another endpoint.

Writes:

- `audit_logs`

## Required Auth Model

### v1.4 Local Auth / v1.5 Scoped Tokens

v1.4 used a simple local token or API key. v1.5.2 adds per-agent scoped bearer tokens for local and remote workers.

Required fields:

- `workspace_id`
- `agent_id`
- API key or local token
- permission scope

Supported auth headers:

```http
Authorization: Bearer <local_token>
X-AgentOps-Agent-Id: agt_kb_researcher
X-AgentOps-Workspace-Id: local_demo
```

Scopes should be explicit:

```text
agents:write
tasks:create
tasks:read
tasks:claim
runs:write
toolcalls:write
artifacts:write
approvals:request
memories:propose
evaluations:submit
audit:write
```

Current implementation:

- `AGENTOPS_API_KEY` remains a global local development key.
- `POST /api/agent-gateway/enrollment/create` issues an agent-bound bearer token.
- MIS stores only a token hash.
- The token can act only as its bound `agent_id`.
- The token can act only in its bound `workspace_id`.
- Token-auth requests cannot override `agent_id` or `workspace_id` through request body, query string, or headers.
- Token-auth task creation is bound to the token's own `agent_id` and `workspace_id`; a remote agent cannot create work as another agent or another workspace.
- Gateway endpoints check required scopes.
- Valid scoped tokens that lack an endpoint scope return `403 forbidden`, not `401 unauthorized`.
- Enrollment launch packets now recommend minting a short-lived session before worker execution:
  - `agentops session create --ttl-sec 900 --save-session`
  - `agentops-worker ... --use-session --session-ttl-sec 900`
- `agentops-worker --use-session` now refreshes short-lived sessions during loop mode before expiry, using the parent enrollment token only in process memory and writing only session metadata to state/output. `scripts/agent_worker.py` remains a repo-local compatibility wrapper.
- Task claim is guarded for multi-worker use:
  - public pool tasks may be visible to multiple agents before claim,
  - first claim moves the task to `running` and binds `owner_agent_id`,
  - repeat claim by the same agent is idempotent,
  - claim or run start by another agent is rejected with `403` or `409`.
- Task pull, task claim, run start, run heartbeat, tool call, approval, memory, evaluation, and audit write paths enforce the run/task workspace boundary.
- Worker recovery is operator-visible:
  - `GET /api/workers/stuck-tasks` lists stale running worker tasks,
  - `POST /api/workers/tasks/release` returns a stuck task to `planned`,
  - linked running runs are marked `blocked` with `WorkerTaskReleased`.
- `POST /api/agent-gateway/enrollment/revoke` revokes tokens.
- `POST /api/agent-gateway/enrollment/rotate` revokes an active token and returns a one-time replacement token.
- `POST /api/agent-gateway/enrollment/request` creates task/run/approval/request ledger rows without issuing a token.
- `POST /api/agent-gateway/enrollment/issue-approved` issues the token only after the linked approval is approved.
- `POST /api/agent-gateway/session/create` mints a short-lived session token from a valid enrollment token or local API key.
- Session tokens inherit agent/workspace bindings and a subset of parent scopes.
- Session tokens cannot mint replacement sessions.
- `GET /api/agent-gateway/sessions` lists session metadata without `session_hash` or raw token values.
- `POST /api/agent-gateway/session/revoke` revokes one session or all active sessions for an agent.
- Revoking an enrollment token also revokes active child sessions.
- `GET /api/agent-gateway/enrollments` reports heartbeat freshness.
- Revoked tokens report `heartbeat_state=revoked`, not `fresh` or `stale`.

Current endpoint scope map:

| Endpoint | Required scope |
| --- | --- |
| `POST /api/agent-gateway/enrollment/request` | local request path; no token issued |
| `POST /api/agent-gateway/enrollment/issue-approved` | admin/local approval authority |
| `POST /api/agent-gateway/session/create` | valid enrollment token or local API key |
| `GET /api/agent-gateway/sessions` | admin/local authority |
| `POST /api/agent-gateway/session/revoke` | admin/local authority |
| `POST /api/agent-gateway/register` | `agents:write` |
| `POST /api/agent-gateway/heartbeat` | `agents:heartbeat` |
| `POST /api/agent-gateway/tasks` | `tasks:create` |
| `GET /api/agent-gateway/tasks/pull` | `tasks:read` |
| `POST /api/agent-gateway/tasks/:id/claim` | `tasks:claim` |
| `POST /api/agent-gateway/runs/start` | `runs:write` |
| `POST /api/agent-gateway/runs/:id/heartbeat` | `runs:write` |
| `POST /api/agent-gateway/tool-calls` | `toolcalls:write` |
| `POST /api/agent-gateway/artifacts` | `artifacts:write` |
| `POST /api/agent-gateway/approvals/request` | `approvals:request` |
| `POST /api/agent-gateway/memories/propose` | `memories:propose` |
| `POST /api/agent-gateway/evaluations/submit` | `evaluations:submit` |
| `POST /api/agent-gateway/audit` | `audit:write` |

### Future Auth

Future product versions should add:

- Workspace-level RBAC.
- Connector-specific scoped credentials.
- Hosted customer enrollment policy UI.
- mTLS or signed heartbeats for server-side agents.
- Trust registry for external runtimes.

## Data Mapping To Existing Tables

| Gateway object | Existing table | Notes |
| --- | --- | --- |
| Agent identity | `agents` | Register, role, runtime, status, tool scope, budget. |
| Task assignment | `tasks` | Pull, claim, status changes, ownership. |
| Run lifecycle | `runs` | Start, heartbeat, completion, failure, output summary. |
| Tool evidence | `tool_calls` | Tool name, risk, duration, status, redacted metadata. |
| Human gate | `approvals` | Required for high-risk side effects. |
| Memory candidate | `memories` | Candidate only; approval is separate. |
| Quality result | `evaluations` | Gate name, score, pass/fail, notes. |
| Audit event | `audit_logs` | Append-only operational evidence. |

## v1.4 Implementation Plan

### Step 1: Docs Only

Create and review the product usage model and Agent Gateway CLI/API spec. No backend or UI change is required for this step.

### Step 2: Minimal CLI Wrapper

Add a small `agentops` CLI wrapper that can:

- Read `AGENTOPS_BASE_URL`.
- Read `AGENTOPS_API_KEY`.
- Send JSON requests.
- Print JSON responses.
- Avoid writing secrets to logs.

The first implementation can be a Python script under `scripts/` or a small installable package.

Status: implemented as `agentops_mis_cli/agentops.py`, `scripts/agentops`, and the editable Python package entry in `pyproject.toml` / `agentops_mis_cli`.

### Step 3: Backend Endpoints

Add minimal local endpoints under `/api/agent-gateway/*`.

The first backend pass should support:

- Register.
- Heartbeat.
- Task pull.
- Task claim.
- Run start.
- Run heartbeat.
- Tool-call record.
- Approval request.
- Evaluation submit.
- Audit emit.

Status: implemented in the local Python server for v1.4 MVP.

### Step 4: Connect OpenClaw / Hermes Adapters

Add adapters that translate runtime activity into Agent Gateway calls:

- OpenClaw agent or cron jobs call `task pull`, `run start`, `toolcall record`, and `eval submit`.
- Hermes or Agnesfallback local probes call `run start`, `run heartbeat`, and `audit emit`.
- Dify / OpenAI File Search workflows can be represented as external runtimes or connectors, with uploads and writes gated by approvals.

### Step 5: Remote Agent Support

Current v1.5.2 minimal support:

- Remote agent gets a scoped token.
- Remote agent registers with workspace and runtime metadata.
- Remote agent heartbeats periodically.
- Remote agent pulls scoped tasks.
- MIS can revoke the agent token.
- Raw files and credentials stay outside the ledger unless explicitly approved and redacted.

Verification helper:

```bash
python3 scripts/remote_agent_token_worker_smoke.py
python3 scripts/workspace_isolation_smoke.py
python3 scripts/enrollment_health_state_smoke.py
python3 scripts/agentops_pip_install_smoke.py
python3 scripts/agentops_doctor_smoke.py
python3 scripts/agentops_worker_status_smoke.py
python3 scripts/agentops_worker_daemon_cli_smoke.py
python3 scripts/agentops_status_smoke.py
python3 scripts/enrollment_launch_steps_smoke.py
python3 scripts/remote_launch_packet_worker_smoke.py
python3 scripts/agent_gateway_scope_matrix_smoke.py
python3 scripts/agent_gateway_session_smoke.py
python3 scripts/enrollment_approval_workflow_smoke.py
python3 scripts/task_claim_conflict_smoke.py
python3 scripts/worker_stuck_recovery_smoke.py
python3 scripts/worker_session_refresh_smoke.py
python3 scripts/worker_adapter_retry_smoke.py
python3 scripts/agentops_worker_package_smoke.py
python3 scripts/agentops_customer_worker_cli_smoke.py
python3 scripts/agentops_task_create_cli_smoke.py
python3 scripts/agent_gateway_task_create_scope_smoke.py
```

This helper creates a scoped token, creates a normal MIS task for that agent, runs `scripts/agent_worker.py --once` with the token, verifies run/tool/eval evidence, and revokes the token by default. It does not print the raw token.
The workspace isolation helper creates workspace A/B tasks, verifies that the workspace A token cannot pull, claim, start, or write workspace B work, and verifies that normal workspace A execution still succeeds.
The enrollment health helper verifies `never_seen -> fresh -> stale -> revoked` without printing the raw token.
The CLI status helper verifies `agentops status` reports safe token-bound metadata, updates to `fresh` after heartbeat, and rejects revoked tokens without leaking the raw token.
The CLI doctor helper verifies `agentops doctor` works in local no-token mode and scoped env-token mode, checks Gateway/worker status, and confirms the raw token is omitted from output.
The CLI worker-status helper verifies `agentops worker status` returns the worker fleet/daemon summary without token leakage.
The CLI worker-preflight helper verifies `agentops worker preflight` returns read-only Gateway/adapter readiness JSON with `live_execution_performed=false`.
The CLI worker-daemon helper verifies `agentops worker start/status/logs/stop` can manage a mock daemon without leaking secrets.
The live-confirm-gate helper verifies `agentops worker start --adapter hermes|openclaw` fails closed without `--confirm-run`.
The customer-worker CLI helper verifies `agentops workflow customer-worker-task` creates a real mock worker run with run/tool/evaluation/audit/artifact evidence and keeps Hermes live execution gated by confirmation.
The task-create CLI helper verifies `agentops task create` can create a normal customer/API task, then a worker can pull it and write run/tool/evaluation evidence without leaking token-like values.
The task-create scope helper verifies scoped tokens need `tasks:create`, cannot create tasks as another agent, and cannot cross workspace boundaries.
The launch-steps helper verifies create/rotate responses include safe remote-worker commands, a short-lived session command, `--use-session`, and do not embed the raw token in those commands.
The remote launch-packet helper uses the returned environment shape to run a real worker through `--use-session` and verify run/tool/evaluation ledger evidence.
The scope-matrix helper verifies an observer token can heartbeat/pull/audit but receives `403 forbidden` for claim/run/tool/artifact writes.
The session helper verifies an enrollment token can mint a narrowed short-lived session, sessions can be listed without hash leakage, one session can be revoked directly, a session can heartbeat/pull tasks, cannot mint another session, expired sessions are rejected, and parent enrollment revocation cascades to active child sessions.
The enrollment-approval helper verifies request-before-token behavior: request returns no token, premature issue is rejected, approval unlocks token issue, and the issued token can heartbeat.
The task-claim helper verifies two agents can initially see the same public pool task, the first claim wins, same-agent repeat claim is idempotent, and a second worker cannot claim or start the already claimed task.
The stuck-recovery helper verifies a stale running worker task is listed, released back to `planned`, and the linked running run is blocked with `WorkerTaskReleased`.
The worker package helper installs the Python source package into a temporary venv, verifies `agentops-worker --help`, then runs a one-shot no-task worker loop against a local stub Agent Gateway. It proves the installable worker can register, pull, heartbeat, write state outside the repo, and omit token values.
It also verifies `agentops-worker service-template --manager launchd|systemd` renders restartable service files with only a token placeholder, not a raw token.
It verifies `agentops-worker service-install --manager launchd|systemd` defaults to dry-run and only writes a placeholder service file when explicitly confirmed.
It verifies `agentops-worker preflight` can perform read-only Gateway/adapter readiness checks without executing tasks, writing ledger rows, or printing token values.
The session-refresh helper verifies a loop worker using `--use-session` refreshes short-lived sessions before expiry and still completes multiple tasks with run/tool/evaluation evidence.
The adapter-retry helper verifies retryable adapter failures can succeed after retry, while non-retryable safety gates such as missing `--confirm-run` stop after one attempt and still write failed run/tool/evaluation evidence.

Remaining future work:

- Hosted customer enrollment policy UI.
- Hosted multi-tenant isolation and full RBAC.
- Reconnection backoff policy.
- mTLS or signed heartbeats for server-side agents.

## Non-Goals For v1.4

- No SaaS multi-tenant billing.
- No public OAuth marketplace.
- No automatic secret ingestion.
- No browser-click automation as the primary agent integration.
- No default real external writes.
- No storage of full private transcripts or raw customer files in the ledger.
