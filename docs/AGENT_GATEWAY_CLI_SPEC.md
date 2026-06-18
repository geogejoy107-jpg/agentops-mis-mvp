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
./scripts/agentops login --base-url http://127.0.0.1:8787 --workspace-id local-demo --agent-id agt_local_worker
./scripts/agentops enrollment create --agent-id agt_remote_builder --name "Remote Builder" --runtime openclaw
```

The implementation lives in `scripts/agentops.py`, with `scripts/agentops` as a shell wrapper. It uses only Python standard library modules and reads configuration from environment variables or `~/.agentops/config.json`.

### `agentops login`

Stores a local API key or local token for the current workspace.

```bash
agentops login --base-url http://127.0.0.1:8787 --workspace local_demo
```

v1.4 can support environment-variable auth only. Interactive login is optional.

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
  --scopes agents:write,agents:heartbeat,tasks:read,tasks:claim,runs:write,toolcalls:write,artifacts:write,evaluations:submit,audit:write \
  --ttl-days 30
```

Optional:

```bash
agentops enrollment create --agent-id agt_local_worker --name "Local Worker" --save-token
```

`--save-token` writes the returned token to the local CLI config for this machine only.

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

## API Endpoint Proposal

All endpoints are under the existing local API server.

```http
GET  /api/agent-gateway/enrollments
POST /api/agent-gateway/enrollment/create
POST /api/agent-gateway/enrollment/revoke
POST /api/agent-gateway/enrollment/rotate
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
- Gateway endpoints check required scopes.
- Task pull, task claim, run start, run heartbeat, tool call, approval, memory, evaluation, and audit write paths enforce the run/task workspace boundary.
- `POST /api/agent-gateway/enrollment/revoke` revokes tokens.
- `POST /api/agent-gateway/enrollment/rotate` revokes an active token and returns a one-time replacement token.
- `GET /api/agent-gateway/enrollments` reports heartbeat freshness.
- Revoked tokens report `heartbeat_state=revoked`, not `fresh` or `stale`.

Current endpoint scope map:

| Endpoint | Required scope |
| --- | --- |
| `POST /api/agent-gateway/register` | `agents:write` |
| `POST /api/agent-gateway/heartbeat` | `agents:heartbeat` |
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

- Short-lived session tokens.
- Token rotation.
- Workspace-level RBAC.
- Connector-specific scoped credentials.
- Remote agent enrollment and revocation.
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

The first implementation can be a Python script under `scripts/` or a small package later.

Status: implemented as `scripts/agentops.py` and `scripts/agentops`.

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
```

This helper creates a scoped token, creates a normal MIS task for that agent, runs `scripts/agent_worker.py --once` with the token, verifies run/tool/eval evidence, and revokes the token by default. It does not print the raw token.
The workspace isolation helper creates workspace A/B tasks, verifies that the workspace A token cannot pull, claim, start, or write workspace B work, and verifies that normal workspace A execution still succeeds.
The enrollment health helper verifies `never_seen -> fresh -> stale -> revoked` without printing the raw token.

Remaining future work:

- Production enrollment approval workflow.
- Short-lived session tokens.
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
