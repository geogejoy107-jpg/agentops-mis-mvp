# API Spec

本 MVP 暴露 REST 风格 API。所有响应均为 JSON。真实产品可迁移为 OpenAPI 3.1。

## Agents

```http
GET /api/agents
POST /api/agents
GET /api/agents/:id
GET /api/agents/:id/performance
```

POST body 示例：

```json
{
  "name": "Research Agent",
  "role": "Researcher",
  "runtime_type": "mock",
  "model_provider": "anthropic",
  "model_name": "claude-sonnet-4.5",
  "budget_limit_usd": 5,
  "allowed_tools": ["browser.search", "github.read", "memory.propose"]
}
```

## Tasks

```http
GET /api/tasks
POST /api/tasks
GET /api/tasks/:id
PATCH /api/tasks/:id/status
PATCH /api/tasks/:id/assign
```

## Mock Runtime

```http
POST /api/mock-runs/start
POST /api/mock-runs/:id/complete
```

`POST /api/mock-runs/start` body:

```json
{
  "task_id": "tsk_competitor",
  "agent_id": "agt_research"
}
```

行为：创建 run，随机生成 2-5 个 tool calls；如果出现高风险 tool call，则生成 approval 并进入 waiting_approval；否则自动完成并生成 evaluation 与 memory candidate。

## Runs

```http
GET /api/runs
GET /api/runs/:id
GET /api/runs/:id/graph
GET /api/runs/export
```

支持 query：

```text
/api/runs?task_id=tsk_competitor
/api/runs?agent_id=agt_research
```

## Agent Gateway Scoped Readback

For machine-facing agents and remote workers, prefer the scoped Agent Gateway
read endpoints over the local UI/demo list endpoints:

```http
GET /api/agent-gateway/tasks
GET /api/agent-gateway/tasks/:id
GET /api/agent-gateway/runs
GET /api/agent-gateway/runs/:id
GET /api/agent-gateway/runs/:id/graph
GET /api/agent-gateway/artifacts
GET /api/agent-gateway/review/queue
```

These require `tasks:read` for scoped tokens and are constrained to the token's
workspace plus tasks/runs/artifacts/review items visible to the bound agent.
The browser UI may still use the local list endpoints for the single-machine
demo. `GET /api/review/queue` remains the local UI/demo read path; machine-facing
CLI/remote agents should use `GET /api/agent-gateway/review/queue`.

## Tool Calls

```http
GET /api/tool-calls
POST /api/tool-calls/:id/request-approval
```

## Approvals

```http
GET /api/approvals
POST /api/approvals/:id/approve
POST /api/approvals/:id/reject
```

## Memories

```http
GET /api/memories
GET /api/memories/export
POST /api/memories/:id/approve
POST /api/memories/:id/reject
```

## Evaluations

```http
GET /api/evaluations
POST /api/evaluations/run-rule-check
```

## Dashboard

```http
GET /api/dashboard/metrics
```

Dashboard metrics include baseline MIS counts plus:

- `runtime_health`: OpenClaw, Hermes and Notion status.
- `openclaw_import`: imported OpenClaw agent, cron task, cron run and failed gate counts.
- `agent_performance_summary`: run count, success rate, duration, cost, failure and approval counts.

## Workflows

```http
POST /api/workflows/customer-worker-task
POST /api/workflows/customer-worker-task/submit
POST /api/workflows/customer-task-templates/run
POST /api/workflows/customer-task-templates/submit
GET  /api/workflows/jobs
GET  /api/workflows/jobs/stuck
GET  /api/workflows/jobs/:job_id
POST /api/workflows/jobs/:job_id/mark-failed
```

`/customer-worker-task` executes a customer task through the Agent Gateway
worker loop and returns run/artifact/evidence ids. `/customer-worker-task/submit`
queues the same workflow as a `workflow_jobs` row and returns immediately with a
`job_id`, which is the preferred path for real Hermes/OpenClaw work that may
outlive a short browser or CLI request. Job records store status, request hash,
safe summaries, result ids, and safe result JSON; they must not store raw
prompts, raw responses, credentials, tokens, or private transcripts.

`/workflows/jobs/stuck` lists queued/running jobs older than a threshold.
`/mark-failed` is an operator recovery action for stale jobs; it marks the job
failed and writes runtime/audit evidence without deleting result history.

## Audit

```http
GET /api/audit
```

## Integrations / OpenClaw

```http
GET  /api/integrations/openclaw/status
POST /api/integrations/openclaw/import
POST /api/integrations/openclaw/probe
```

Import reads local files only:

```text
~/.openclaw/openclaw.json
~/.openclaw/cron/jobs.json
~/.openclaw/cron/runs/*.jsonl
~/.openclaw/subagents/runs.json
```

Deterministic IDs prevent duplicate records on repeated import:

- Agent: `agt_oc_{agentId}`
- Cron task: `tsk_oc_cron_{jobId}`
- Cron run: `run_oc_cron_{jobId}_{sessionId_or_ts}`

Privacy boundary: cron run `summary` raw text is never stored. The database stores a redacted first 200 characters in `runs.output_summary`, plus `summary_hash`, `source_path`, `job_id` and `session_id` style metadata in audit/tool-call metadata.

`POST /api/integrations/openclaw/probe` is manual only. It creates a probe task/run/evaluation and does not run on a schedule.

## Integrations / Hermes

```http
GET  /api/integrations/hermes/status
GET  /api/integrations/hermes/models
POST /api/integrations/hermes/probe
POST /api/integrations/hermes/cli-probe
POST /api/integrations/hermes/chat-completion-probe
POST /api/integrations/hermes/run-task
```

Hermes probe checks local gateway availability on `127.0.0.1:8642`. If the API port is not listening, the endpoint records an `unavailable` health failure as a normal run/evaluation instead of failing the whole MIS service.

Agnesfallback is exposed as a Hermes-compatible runtime connector:

- CLI connector: `rtc_agnesfallback_cli`
- OpenAI-compatible API connector: `rtc_agnesfallback_openai_api`
- Default behavior: dry-run only.
- Real fixed probes require both `HERMES_ALLOW_REAL_RUN=true` and request body `{"confirm_run": true}`.
- The CLI probe uses a fixed safe prompt and intentionally excludes `--yolo`.
- `/run-task` supports only a fixed safe Hermes default gateway probe when explicitly confirmed; arbitrary raw task prompts remain disabled.

Environment variables:

```text
HERMES_GATEWAY_URL=http://127.0.0.1:8642
HERMES_PROFILE=default
HERMES_RUNTIME_MODE=health_only
HERMES_ALLOW_REAL_RUN=false
HERMES_REQUIRE_CONFIRM_RUN=true
AGNESFALLBACK_BIN=~/.local/bin/agnesfallback
AGNESFALLBACK_GATEWAY_URL=http://127.0.0.1:8643
AGNESFALLBACK_PROFILE=agnesfallback
```

For local acceptance on machines where the Hermes gateway already exposes the Agnesfallback model through `127.0.0.1:8642`, `AGNESFALLBACK_GATEWAY_URL` may point at the same gateway URL. The connector still sends only the fixed probe prompt and stores hashes/summaries, not full prompts or raw responses.

## Integrations / Notion

```http
GET /api/integrations/notion/status
GET /api/integrations/notion/export-preview
POST /api/integrations/notion/export-report
POST /api/integrations/notion/preview
POST /api/integrations/notion/dry-run-export
POST /api/integrations/notion/export-confirmed
POST /api/integrations/notion/import-preview
POST /api/integrations/notion/sync-memory-candidates
POST /api/integrations/notion/sync-tasks
```

环境变量：

```text
NOTION_TOKEN=
NOTION_PARENT_PAGE_ID=
NOTION_DATABASE_ID=
NOTION_VERSION=2022-06-28
NOTION_WORKSPACE_PRIVATE_EXPORT=false
```

`NOTION_PARENT_PAGE_ID` 和 `NOTION_DATABASE_ID` 二选一即可。

产品化 OAuth / public integration 路径可以设置 `NOTION_WORKSPACE_PRIVATE_EXPORT=true`，在没有 parent/database 时尝试创建 workspace-level private page。Notion 官方限制是：internal integration 通常仍然需要 parent page 或 database；workspace-level private page 只适用于 Notion 允许的 public integration bot / personal access token 场景。

未配置 token，或没有 parent/database 且未开启 workspace private export 时，导出接口只返回 dry-run 预览，不会联网。

POST body：

```json
{
  "dry_run": true,
  "confirm_export": false,
  "title": "AgentOps MIS 项目汇报工作台"
}
```

安全默认：`dry_run` 默认为 `true`。真实导出必须显式传入：

```json
{
  "dry_run": false,
  "confirm_export": true
}
```

隐私边界：Notion 导出只包含项目汇报摘要和结构化指标，不导出 credentials、私聊正文、完整 session transcript 或原始命令体。

## Runtime Connectors / Bases / Templates

```http
GET /api/runtime-connectors
GET /api/runtime-events
GET /api/bases
GET /api/connectors
GET /api/external-links
GET /api/sync-events
GET /api/template-packages
GET /api/template-bindings
POST /api/migration/preview
```

These endpoints support the v1.2.1 "external base" story:

- Agent-MIS local bases remain canonical for task, memory, template and audit ledger records.
- Notion is modeled as an external base in dry-run mode by default.
- W&B, Plane, Docmost and Mattermost are represented as planned external bases with capability metadata.
- Template packages describe scenario-specific agent roles, base bindings, memory schema, quality gates and approval policy.
- Migration preview shows what can move between bases, what must stay local, permission changes and rollback steps.

No endpoint imports private Notion content or writes to external systems unless a dedicated confirmed export endpoint is used.

## Demo Scripts

```bash
python3 scripts/demo_seed_openclaw_redacted.py --reset
python3 scripts/demo_acceptance.py --start-server
```

The seed script creates deterministic synthetic data only:

- 10 demo agents
- 50 demo tasks
- 500 demo runs
- 800 demo tool calls
- 200 demo memory candidates
- 2000 demo audit records

The acceptance script verifies local API readiness for dashboard, integrations, runtime connectors, bases, templates, Notion dry-run, Agnesfallback dry-run and migration preview.

## 高风险工具策略

以下工具默认进入审批：

- `shell.exec`
- `github.push`
- `email.send`
- `file.delete`
- `database.write`
- `mcp.invoke`（本 MVP 作为 high risk 示例）
