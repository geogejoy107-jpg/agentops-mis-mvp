# AgentOps MIS v1.5 Eight Product Closure Spec

## One-Sentence Goal

AgentOps MIS v1.5 should prove that a normal MIS task can be assigned to a local or external AI worker, executed through a real adapter loop, and written back into the MIS ledger with run, tool, evaluation, memory, approval, and audit evidence, excluding Dify and Notion live-sync tracks.

## Scope Boundary

This spec covers the eight non-Dify/Notion product gaps identified during v1.5 planning.

Excluded from this closure spec:

- Dify live dataset upload and deployed chatbot hosting.
- Notion bidirectional sync.
- SaaS billing, hosted multi-tenant deployment, and marketplace connectors.

## Product Objective

Move AgentOps MIS from a dashboard/mock demo into a usable local control plane where AI workers can:

1. Register or enroll.
2. Pull real MIS tasks.
3. Claim work.
4. Execute through mock, Hermes, or OpenClaw adapters.
5. Write run/tool/evaluation/audit evidence.
6. Be started, stopped, or observed by a human operator.
7. Use scoped tokens when running outside the browser or on another machine.

## The Eight Product Closure Items

### 1. Real Long-Running Agent Worker

Goal:

- Provide a worker process that can continuously pull, claim, execute, and write back tasks.

Current v1.5 implementation:

- `scripts/agent_worker.py`
- Supports `--once`.
- Supports loop mode with `--poll-interval` and `--max-tasks`.
- Supports bounded daemon resilience with `--continue-on-error`, `--max-errors`, local state files, and JSONL iteration logs.
- Uses Agent Gateway HTTP API instead of direct SQLite writes.
- Local daemon supervisor APIs:
  - `GET /api/workers/status`
  - `GET /api/workers/local/logs`
  - `POST /api/workers/local/start`
  - `POST /api/workers/local/stop`

Acceptance evidence:

- Daemon auto-pull run: `run_gw_6ad797929084`
- Persistent daemon smoke: `max_tasks=0` showed running status and stopped cleanly.
- Resilience smoke: `python3 scripts/worker_daemon_resilience_smoke.py`
  - server daemon processed task `tsk_worker_daemon_resilience_20260617184522`
  - wrote run `run_gw_9ee54d8e4d95`
  - exposed `processed=1`, `iterations=1`, JSONL `worker.iteration`, and local state path
  - direct bad-URL worker recorded two errors and exited after `max_errors`.

Remaining product work:

- launchd/systemd service unit.
- Full restart policy with supervised relaunch after process death.
- Production log rotation.
- Fleet-level worker management.

### 2. OpenClaw / Hermes Adapter Loop

Goal:

- A normal MIS task should execute through local adapters and write results back into MIS.

Current v1.5 implementation:

- Worker adapter choices:
  - `mock`
  - `hermes`
  - `openclaw`
- Hermes/OpenClaw real execution requires explicit `--confirm-run`.
- Adapter output is summarized and hashed; raw prompt/response is not stored.

Acceptance evidence:

- Mock run: `run_gw_a20e5b2eb6e3`
- Hermes run: `run_gw_0d793ed6bbac`
- OpenClaw run: `run_gw_9b2a6550d489`

Remaining product work:

- Rich task-to-runtime prompt profiles.
- Adapter-specific retry handling.
- Runtime trust registry UI.

### 3. Repo-Local CLI, Not Global Package Yet

Goal:

- Agents and operators should have a stable CLI/API surface without depending on browser clicks.

Current v1.5 implementation:

- `scripts/agentops`
- `scripts/agentops.py`
- Commands include:
  - `agentops login`
  - `agentops enrollment create/list/revoke/rotate`
  - `agentops agent register`
  - `agentops agent heartbeat`
  - `agentops task pull`
  - `agentops task claim`
  - `agentops run start`
  - `agentops run heartbeat`
  - `agentops toolcall record`
  - `agentops artifact record`
  - `agentops approval request`
  - `agentops memory propose`
  - `agentops eval submit`
  - `agentops audit emit`

Acceptance evidence:

- CLI enrollment smoke passed with `agt_remote_cli_smoke`.
- Revoked token was rejected.

Remaining product work:

- Global `agentops` install.
- pip/Homebrew/npm packaging.
- Signed binary or installer.

### 4. Remote Agent Entry Shape

Goal:

- An agent running on another computer or server should be able to connect through a scoped token and work through the same Agent Gateway protocol.

Current v1.5 implementation:

- Enrollment API:
  - `POST /api/agent-gateway/enrollment/create`
  - `GET /api/agent-gateway/enrollments`
  - `POST /api/agent-gateway/enrollment/revoke`
  - `POST /api/agent-gateway/enrollment/rotate`
- Tokens are:
  - shown once,
  - stored only as hashes,
  - bound to one `agent_id`,
  - bound to one `workspace_id`,
  - scoped by endpoint permissions,
  - revocable.
- Active tokens can be rotated; the old token is revoked and the replacement token is shown once.
- Heartbeat freshness is tracked.
- Token-auth requests cannot override `agent_id` or `workspace_id` through body, query string, or headers.
- `tasks` and `runs` now carry `workspace_id`; Agent Gateway pull/claim/start/run-write paths check that boundary.
- Agent Gateway can now record customer delivery artifacts with `artifacts:write`, so remote workers can submit report summaries without raw customer content.
- `/workspace/agents` exposes a first operator UI for creating, viewing, and revoking scoped enrollment tokens.
- `/workspace/agents` also exposes scope presets and per-token rotation.

Acceptance evidence:

- HTTP scoped-token smoke passed with `agt_remote_enroll_smoke`.
- Remote token worker smoke passed:
  - `run_gw_876a7c777841`
  - repeat run `run_gw_f5635ff603fd`
- Browser verification showed `远程 Agent 接入`, `创建接入 token`, and `最近接入记录` on `/workspace/agents`.
- `python3 scripts/enrollment_rotation_smoke.py` verified API and CLI rotation with redacted one-time token output.
- `python3 scripts/workspace_isolation_smoke.py` verified:
  - workspace A token only pulls workspace A tasks,
  - workspace B tasks do not leak into pull results,
  - header/query workspace spoofing returns 403,
  - cross-workspace claim/start returns 403,
  - matching workspace claim/start/heartbeat succeeds.

Remaining product work:

- Short-lived sessions.
- Reconnection/backoff policy.
- Customer-facing enrollment approval workflow.

### 5. MVP Security Boundary

Goal:

- Keep local-first execution useful without silently storing secrets, prompts, full responses, or private transcripts.

Current v1.5 implementation:

- Token hash storage only.
- Raw token values are not written to audit/runtime metadata.
- Rotation smoke output omits raw token values; raw tokens are still one-time only.
- Minimal workspace isolation is enforced for Agent Gateway token-auth task and run paths.
- `workspace_id` values are normalized rather than redacted, preventing identifier corruption.
- Worker output is summarized.
- Tool args are normalized and redacted.
- Hermes/OpenClaw real execution requires explicit confirmation.
- `.agentops_runtime/`, local DB, node modules, and build output are gitignored.

Acceptance evidence:

- DB check confirmed no `agtok_` raw token in audit metadata.
- `agent_gateway_tokens` table has `token_hash`, not raw token.

Remaining product work:

- Full RBAC.
- Multi-tenant hosted isolation beyond this local SQLite MVP.
- Secret manager.
- Connector trust registry UI.

### 6. UI Operation Loop

Goal:

- A human customer/operator should see that agents are actually working, not just static dashboard cards.

Current v1.5 implementation:

- `/workspace/agents` includes:
  - worker status panel,
  - one-shot mock/Hermes/OpenClaw dispatch buttons,
  - daemon start/stop controls,
  - daemon status cards.
  - remote agent enrollment token panel.
  - worker fleet telemetry with daemon log tails and recent Agent Gateway events.
- `/workspace/approvals` reads live approvals from the backend and can approve/reject through the real API.
- `/admin/toolcalls` reads live tool-call evidence from the backend instead of mock data.
- `/admin/tasks/:id` shows delivery artifacts and links related runs to their Run Detail pages.
- Approval decisions preserve the original approval reason and synchronize linked tool/run/task status: approval completes the tool without overwriting completed run output; rejection blocks the tool, run and task.
- Browser verification confirmed the controls render.

Acceptance evidence:

- UI mock dispatch run: `run_gw_8fae81a1bfa6`
- Browser snapshot showed:
  - `本地 Worker 循环`
  - `启动 mock 常驻`
  - `停止常驻 worker`
  - `远程 Agent 接入`
  - `创建接入 token`
  - `Worker Fleet 观测`
  - `Daemon 日志`
  - `最近网关事件`
  - daemon status cards.
- `GET /api/workers/local/logs?adapter=mock` returned 80 log-tail lines.
- `GET /api/approvals` returned 12 live approval rows, including pending `ap_gw_f289a8baafcd`.
- `GET /api/tool-calls` returned 6928 live tool-call rows, including `artifact.delivery_summary`.
- `GET /api/tasks/tsk_kb_bot_20260617185442_06` returned delivery artifact `art_kb_bot_delivery_20260617185442`.
- `python3 scripts/approval_decision_side_effect_smoke.py` verified approve and reject status propagation.

Remaining product work:

- Dedicated worker control console.
- Better customer-facing task submission flow.
- Clearer live/dry-run/approval state indicators.

### 7. Customer-Task Usefulness

Goal:

- MIS should be usable for a real customer-style task, not only internal probes.

Current v1.5 implementation:

- Pixel Office customer dispatch exists.
- Worker loop can process normal MIS tasks.
- Remote token worker smoke creates and completes a normal task through the ledger.
- AI knowledge-base / Q&A bot customer demo creates a six-step AI-team project, pending approval for external upload, evaluations, memories, audit events, and a customer delivery artifact through Agent Gateway.
- Agent Gateway supports `POST /api/agent-gateway/artifacts` and CLI `agentops artifact record` for delivery summaries that store only safe summary/URI/hash metadata.
- Pixel Office can start the same six-step customer project through `POST /api/workflows/kb-bot-project`, so the classroom/customer flow no longer requires manually running the script.

Acceptance evidence:

- Customer task workflow previously verified with `run_customer_task_ce855c707aace6c8`.
- Daemon normal task run: `run_gw_6ad797929084`
- Remote token worker normal task run: `run_gw_f5635ff603fd`
- Knowledge-base bot smoke: `python3 scripts/kb_bot_demo_smoke.py`
  - project: `20260617185442`
  - delivery artifact: `art_kb_bot_delivery_20260617185442`
  - pending external-upload approval: `ap_gw_f289a8baafcd`
- Browser-facing workflow smoke: `python3 scripts/kb_bot_workflow_api_smoke.py`
  - project: `20260617190650`
  - final task: `tsk_kb_bot_20260617190650_06`
  - final run: `run_gw_b365e7e325c6`
  - delivery artifact: `art_kb_bot_delivery_20260617190650`
  - pending external-upload approval: `ap_gw_8002e643f058`

Remaining product work:

- Task templates for common customer jobs.
- Better task result pages and report export.

### 8. Productization Track

Goal:

- Preserve a clear path from local MVP to a real product.

Current v1.5 implementation:

- Product usage model exists.
- Agent Gateway CLI/API spec exists.
- Worker daemon spec exists.
- Scoped remote-token entry exists.
- GitHub PR has implementation history and acceptance docs.

Acceptance evidence:

- `docs/PRODUCT_USAGE_AND_ACTOR_MODEL.md`
- `docs/AGENT_GATEWAY_CLI_SPEC.md`
- `docs/V1_5_AGENT_WORKER_LOOP_SPEC.md`
- `docs/V1_5_AGENT_WORKER_ACCEPTANCE.md`
- This closure spec.

Remaining product work:

- Hosted server mode.
- Multi-workspace and user accounts.
- RBAC and workspace isolation.
- Billing/plan model.
- Customer deployment guide.
- Backup/restore.
- Monitoring/logging.

## Current Verification Commands

```bash
python3 -m py_compile server.py scripts/*.py
git diff --check
cd ui/start-building-app && npm run build
python3 scripts/demo_acceptance.py
python3 scripts/kb_bot_demo_smoke.py
python3 scripts/kb_bot_workflow_api_smoke.py
python3 scripts/approval_decision_side_effect_smoke.py
python3 scripts/remote_agent_token_worker_smoke.py
python3 scripts/workspace_isolation_smoke.py
```

## Current Status Summary

Implemented and verified:

- Local worker loop.
- Local daemon start/stop/status.
- Mock/Hermes/OpenClaw adapter loop.
- UI one-shot worker dispatch.
- UI daemon controls.
- UI worker fleet telemetry.
- Live Approvals Inbox.
- Live Tool Call Ledger.
- Scoped token enrollment.
- Remote enrollment UI.
- Token revocation.
- Token rotation.
- Endpoint-level scope enforcement.
- Minimal workspace isolation for token-auth Agent Gateway pull/claim/run/write paths.
- Remote-token worker end-to-end smoke.
- Customer-style knowledge-base bot project smoke with delivery artifact.

Not yet product-complete:

- Global CLI package.
- Full RBAC and hosted multi-tenant isolation.
- Short-lived sessions.
- Production worker fleet manager.
- Hosted SaaS/commercial deployment layer.
