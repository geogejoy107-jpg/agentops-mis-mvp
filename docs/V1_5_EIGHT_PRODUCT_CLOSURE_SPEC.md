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
- Supports configurable idle/error backoff with `--idle-backoff-max`, `--error-backoff-max`, and `--backoff-factor`.
- Worker state records `consecutive_idle`, `last_sleep_sec`, `next_sleep_sec`, and `last_sleep_reason`.
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
  - latest server daemon processed task `tsk_worker_daemon_resilience_20260618091145`
  - wrote run `run_gw_29d23509f62e`
  - exposed `processed=1`, `iterations=1`, JSONL `worker.iteration`, and local state path
  - direct bad-URL worker recorded two errors and exited after `max_errors`
  - direct bad-URL worker exposed `last_sleep_reason=error_backoff` and `last_sleep_sec=0.1`.

Remaining product work:

- launchd/systemd service unit.
- Full supervised relaunch after process death.
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
- Live recheck on 2026-06-18:
  - Hermes worker task `tsk_worker_hermes_live_20260618065503` completed as `run_gw_6f995c9de929`.
  - OpenClaw worker task `tsk_worker_openclaw_live_20260618065555` completed as `run_gw_c274e7d62b61`.

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
- `scripts/install_agentops_cli.py` installs a local user shim at `~/.local/bin/agentops`.
- Commands include:
  - `agentops login`
  - `agentops status`
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
- Local CLI install smoke passed: `python3 scripts/agentops_cli_install_smoke.py`.
- CLI status smoke passed: `python3 scripts/agentops_status_smoke.py`.
- Current machine has `~/.local/bin/agentops` installed as a shim to this repo.

Remaining product work:

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
- Customer-facing enrollment requests can be created without issuing a token:
  - `POST /api/agent-gateway/enrollment/request`
  - `POST /api/agent-gateway/enrollment/issue-approved`
  - request creates task/run/approval/request ledger rows
  - token issue is blocked until the linked approval is approved
- Enrollment tokens can mint short-lived session tokens through `POST /api/agent-gateway/session/create`.
- Session tokens inherit the bound `agent_id`, `workspace_id`, and a subset of parent scopes.
- Session tokens cannot mint replacement sessions and expire automatically.
- Short-lived sessions can now be listed and revoked:
  - `GET /api/agent-gateway/sessions`
  - `POST /api/agent-gateway/session/revoke`
  - responses expose only metadata and never return `session_hash` or raw token values
  - enrollment revocation cascades to active child sessions
- Heartbeat freshness is tracked with explicit lifecycle states:
  - `never_seen`: active token exists but the remote worker has not heartbeated yet.
  - `fresh`: active token has a recent heartbeat inside its timeout window.
  - `stale`: active token has a heartbeat older than its timeout window.
  - `revoked`: revoked token is no longer treated as live even if it has old heartbeat data.
- Token-auth requests cannot override `agent_id` or `workspace_id` through body, query string, or headers.
- `tasks` and `runs` now carry `workspace_id`; Agent Gateway pull/claim/start/run-write paths check that boundary.
- Scope denial returns HTTP `403 forbidden` for valid tokens that lack a required endpoint permission.
- Agent Gateway can now record customer delivery artifacts with `artifacts:write`, so remote workers can submit report summaries without raw customer content.
- `/workspace/agents` exposes a first operator UI for creating, viewing, and revoking scoped enrollment tokens.
- `/workspace/agents` exposes approval-gated enrollment request controls: request approval, approve/reject enrollment requests, and issue approved tokens.
- `/workspace/agents` also exposes scope presets and per-token rotation.
- `/workspace/agents` exposes recent short-lived sessions and can revoke an active session directly.
- `/workspace/agents` surfaces Agent Gateway readiness/auth mode/scope count/active enrollment/stale heartbeat cards for operators.
- New/rotated enrollment responses include a safe `next_steps` launch packet for remote machines: env setup, `agentops status`, heartbeat, one-shot worker, and loop worker commands. Commands use an API-key placeholder rather than embedding the raw token.
- Launch-packet worker commands now use `--use-session --session-ttl-sec 900`, so remote workers mint a short-lived session before processing tasks instead of holding the enrollment token in the worker loop.

Acceptance evidence:

- HTTP scoped-token smoke passed with `agt_remote_enroll_smoke`.
- Remote token worker smoke passed:
  - `run_gw_876a7c777841`
  - repeat run `run_gw_f5635ff603fd`
- `GET /api/agent-gateway/status` and `agentops status` report safe token-bound auth metadata for remote debugging without printing token secrets.
- Browser verification showed `远程 Agent 接入`, `创建接入 token`, and `最近接入记录` on `/workspace/agents`.
- Playwright snapshot verified `提交审批申请`, `审批式接入申请`, and `审批后发 token` on `/workspace/agents`.
- Frontend build verified the `/workspace/agents` Agent Gateway status card.
- `python3 scripts/enrollment_launch_steps_smoke.py` verified create/rotate launch packets omit raw tokens and include status/session/worker commands.
- `python3 scripts/remote_launch_packet_worker_smoke.py` verified the returned launch packet environment can run a scoped worker through a short-lived session and write run/tool/evaluation ledger evidence:
  - run `run_gw_eed70c81def8`
  - session `agtsess_agt_launch_packet_worker_20260618150315_local_demo_33826b3d655c`
- `python3 scripts/enrollment_rotation_smoke.py` verified API and CLI rotation with redacted one-time token output.
- `python3 scripts/enrollment_health_state_smoke.py` verified the remote enrollment lifecycle `never_seen -> fresh -> stale -> revoked`.
- `python3 scripts/workspace_isolation_smoke.py` verified:
  - workspace A token only pulls workspace A tasks,
  - workspace B tasks do not leak into pull results,
  - header/query workspace spoofing returns 403,
  - cross-workspace claim/start returns 403,
  - matching workspace claim/start/heartbeat succeeds.
- `python3 scripts/agent_gateway_scope_matrix_smoke.py` verified observer-scope RBAC:
  - heartbeat, task pull, and audit writes are allowed,
  - claim, run start, tool call, and artifact writes are rejected with HTTP `403 forbidden`,
  - a worker token can claim and start the same task.
- `python3 scripts/agent_gateway_session_smoke.py` verified short-lived sessions:
  - an enrollment token mints a narrowed session,
  - sessions can be listed without leaking `session_hash`,
  - a session can be revoked directly and is then rejected,
  - session auth reports `agent_session`,
  - session can heartbeat and pull tasks,
  - session cannot mint another session,
  - expired sessions are rejected,
  - parent enrollment revocation cascades to active child sessions.
- `python3 scripts/enrollment_approval_workflow_smoke.py` verified the approval-gated enrollment path:
  - request returned `request_id`, `approval_id`, `task_id`, and `run_id` but no token,
  - token issue before approval returned `approval_required`,
  - approval unlocked one-time token issue,
  - issued token successfully heartbeated,
  - cleanup revoked the token.

Remaining product work:

- Session refresh policy.
- Reconnection/backoff policy.
- Hosted customer enrollment policy UI.

### 5. MVP Security Boundary

Goal:

- Keep local-first execution useful without silently storing secrets, prompts, full responses, or private transcripts.

Current v1.5 implementation:

- Token hash storage only.
- Session hash storage only.
- Raw token values are not written to audit/runtime metadata.
- Rotation smoke output omits raw token values; raw tokens are still one-time only.
- Redaction keeps safe operational evidence such as loopback URLs and run/task IDs readable while still hiding email, phone, bearer token, raw `sk-`, and raw `ntn_` secrets.
- Minimal workspace isolation is enforced for Agent Gateway token-auth task and run paths.
- `workspace_id` values are normalized rather than redacted, preventing identifier corruption.
- Valid scoped tokens missing a required endpoint permission receive HTTP `403 forbidden`, not `401 unauthorized`.
- Worker output is summarized.
- Tool args are normalized and redacted.
- Hermes/OpenClaw real execution requires explicit confirmation.
- `.agentops_runtime/`, local DB, node modules, and build output are gitignored.

Acceptance evidence:

- DB check confirmed no `agtok_` raw token in audit metadata.
- `agent_gateway_tokens` table has `token_hash`, not raw token.
- `python3 scripts/redaction_policy_smoke.py` passed.
- HTTP write/read proof `run_gw_dc141fcaab51` preserved `127.0.0.1:8642` and task id text without `[PHONE_REDACTED]`.

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
  - Agent Gateway status card,
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
- The Agent Gateway card shows gateway readiness, auth mode, workspace, scope count, active enrollments, and stale heartbeats.

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
python3 scripts/agentops_cli_install_smoke.py
python3 scripts/agentops_status_smoke.py
python3 scripts/remote_agent_token_worker_smoke.py
python3 scripts/workspace_isolation_smoke.py
python3 scripts/enrollment_health_state_smoke.py
python3 scripts/redaction_policy_smoke.py
python3 scripts/enrollment_launch_steps_smoke.py
python3 scripts/remote_launch_packet_worker_smoke.py
python3 scripts/agent_gateway_scope_matrix_smoke.py
python3 scripts/agent_gateway_session_smoke.py
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
- Agent Gateway safe status check via `GET /api/agent-gateway/status` and `agentops status`.
- Agent Gateway status surfaced in `/workspace/agents`.
- Remote enrollment launch packet surfaced in `/workspace/agents` after token creation/rotation.
- Remote enrollment launch packet worker path now uses short-lived sessions before task processing.
- Remote enrollment UI.
- Token revocation.
- Token rotation.
- Enrollment heartbeat states: `never_seen`, `fresh`, `stale`, and `revoked`.
- Short-lived session list/revoke API, CLI, and `/workspace/agents` panel.
- Endpoint-level scope enforcement.
- Scoped RBAC matrix smoke for observer-vs-worker permissions.
- Short-lived Agent Gateway sessions, including metadata listing, direct revocation, and parent-token revoke cascade.
- Minimal workspace isolation for token-auth Agent Gateway pull/claim/run/write paths.
- Remote-token worker end-to-end smoke.
- Remote launch-packet worker end-to-end smoke.
- Customer-style knowledge-base bot project smoke with delivery artifact.

Not yet product-complete:

- Global CLI package.
- Full RBAC and hosted multi-tenant isolation.
- Session revocation UI and refresh policy.
- Production worker fleet manager.
- Hosted SaaS/commercial deployment layer.
