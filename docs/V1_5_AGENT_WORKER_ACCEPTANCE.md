# AgentOps MIS v1.5 Agent Worker Acceptance

## Build / Syntax

Command:

```bash
python3 -m py_compile server.py scripts/*.py
git diff --check
cd ui/start-building-app && npm run build
```

Result: passed.

## Runtime Prerequisites Used

- AgentOps MIS backend: `http://127.0.0.1:8787`
- Hermes OpenAI-compatible gateway: `http://127.0.0.1:8642`
- OpenClaw CLI: `/opt/homebrew/bin/openclaw`
- Dify and Notion: not used in this acceptance pass.

## Worker Commands Run

Mock adapter:

```bash
python3 scripts/agent_worker.py --once --adapter mock --agent-id agt_worker_local
```

Hermes adapter:

```bash
python3 scripts/agent_worker.py \
  --once \
  --adapter hermes \
  --confirm-run \
  --agent-id agt_worker_local \
  --hermes-gateway-url http://127.0.0.1:8642
```

OpenClaw adapter:

```bash
python3 scripts/agent_worker.py \
  --once \
  --adapter openclaw \
  --confirm-run \
  --agent-id agt_worker_local \
  --openclaw-timeout 180
```

Daemon supervisor API:

```bash
curl -fsS http://127.0.0.1:8787/api/workers/status | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/workers/local/start \
  -H "Content-Type: application/json" \
  -d '{"adapter":"mock","poll_interval":1,"max_tasks":1}' | jq .
curl -fsS -X POST http://127.0.0.1:8787/api/workers/local/stop \
  -H "Content-Type: application/json" \
  -d '{"adapter":"all"}' | jq .
```

Agent enrollment CLI/API:

```bash
./scripts/agentops enrollment create --agent-id agt_remote_cli_smoke --name "Remote CLI Smoke" --runtime mock --save-token
./scripts/agentops status
./scripts/agentops agent heartbeat --id agt_remote_cli_smoke --status idle
./scripts/agentops task pull --agent-id agt_remote_cli_smoke --limit 1 --status planned
./scripts/agentops enrollment rotate --token-id agtok_...
./scripts/agentops enrollment revoke --token-id agtok_...
python3 scripts/remote_agent_token_worker_smoke.py
python3 scripts/enrollment_rotation_smoke.py
python3 scripts/kb_bot_demo_smoke.py
python3 scripts/kb_bot_workflow_api_smoke.py
python3 scripts/approval_decision_side_effect_smoke.py
python3 scripts/agentops_cli_install_smoke.py
python3 scripts/enrollment_health_state_smoke.py
python3 scripts/agentops_status_smoke.py
```

## Evidence

| Path | Adapter | Task | Run | Result |
| --- | --- | --- | --- | --- |
| CLI | mock | `tsk_worker_debug_create` | `run_gw_a20e5b2eb6e3` | completed |
| CLI | hermes | `tsk_worker_hermes_acceptance_20260617145544` | `run_gw_0d793ed6bbac` | completed |
| CLI | openclaw | `tsk_worker_openclaw_acceptance_20260617145647` | `run_gw_9b2a6550d489` | completed |
| CLI live recheck | hermes | `tsk_worker_hermes_live_20260618065503` | `run_gw_6f995c9de929` | completed |
| CLI live recheck | openclaw | `tsk_worker_openclaw_live_20260618065555` | `run_gw_c274e7d62b61` | completed |
| UI | mock | `tsk_worker_ui_mock_20260617150557_657b7768` | `run_gw_8fae81a1bfa6` | completed |
| daemon | mock | `tsk_daemon_acceptance_20260617231559` | `run_gw_6ad797929084` | completed |
| scoped token worker | mock | `tsk_remote_worker_smoke_20260617162927` | `run_gw_876a7c777841` | completed |

All CLI/live adapter runs produced:

- `runs.status = completed`
- one `tool_calls` row with `agent_worker.{adapter}`
- one `evaluations` row with `pass`
- `audit_logs` entries including `agent_worker.task_processed`
- completed task status

Latest live adapter recheck:

```text
Hermes:   run_gw_6f995c9de929 completed via agent_worker.hermes, evaluation pass
OpenClaw: run_gw_c274e7d62b61 completed via agent_worker.openclaw, evaluation pass
```

The UI-triggered mock worker run was launched from `/workspace/agents` through:

```http
POST /api/workers/local/dispatch-once
```

It produced the same ledger evidence:

```text
runs:        run_gw_8fae81a1bfa6 completed
tool_calls:  agent_worker.mock completed
evaluations: pass
audit_logs:  task.create, worker.dispatch_task.create, task_claim, run.create, run_heartbeat, agent_worker.task_processed, worker.dispatch_once
```

The daemon-triggered mock worker run was not a one-shot dispatch. The sequence was:

```text
POST /api/workers/local/start max_tasks=1
create planned task for agt_worker_daemon_mock
worker loop polls /api/agent-gateway/tasks/pull
worker claims task and writes run/tool/eval/audit
```

Evidence:

```text
tasks:       tsk_daemon_acceptance_20260617231559 completed
runs:        run_gw_6ad797929084 completed
tool_calls:  agent_worker.mock completed
evaluations: pass
audit_logs:  agent_worker.task_processed exists
```

The persistent local daemon smoke also passed:

```text
POST /api/workers/local/start {"adapter":"mock","poll_interval":2,"max_tasks":0}
GET /api/workers/status -> mock daemon running pid=82841
POST /api/workers/local/stop {"adapter":"mock"} -> terminated
```

The daemon resilience smoke also passed:

```text
script: python3 scripts/worker_daemon_resilience_smoke.py
server daemon task: tsk_worker_daemon_resilience_20260617184522
server daemon run: run_gw_9ee54d8e4d95
server daemon state: processed=1 iterations=1 worker_status=completed
daemon log: JSONL worker.iteration present
bad-url direct worker: returncode=1 total_errors=2 consecutive_errors=2 status=failed
token_omitted: true
```

The scoped-token enrollment smoke passed:

```text
HTTP enrollment:
agent_id: agt_remote_enroll_smoke
token_id: agtok_agt_remote_enroll_smoke_local_demo_175054348add
heartbeat: 200 idle
tasks:read pull: 200
runs:start with missing runs:write: forbidden
revoke: revoked=1
post-revoke pull: 401 token revoked

CLI enrollment:
agent_id: agt_remote_cli_smoke
token_id: agtok_agt_remote_cli_smoke_local_demo_db074911c2fa
--save-token wrote only to /tmp test config
heartbeat: 200 idle
tasks:read pull: 200
revoke: revoked=1
post-revoke pull: 401 token revoked
```

The enrollment rotation smoke passed:

```text
script: python3 scripts/enrollment_rotation_smoke.py
api old token: agtok_agt_rotate_api_smoke_20260617180040_local_demo_eb7bbc239f05
api new token: agtok_agt_rotate_api_smoke_20260617180040_local_demo_7cec7f8f8bf2
api old_status_after_rotate: revoked
api new_status_after_rotate: active
cli old token: agtok_agt_rotate_cli_smoke_20260617180040_local_demo_666c67b8c915
cli new token: agtok_agt_rotate_cli_smoke_20260617180040_local_demo_4ea03a4a3a40
token_omitted: true
cleanup_revoked: 1
```

The enrollment heartbeat health-state smoke passed:

```text
script: python3 scripts/enrollment_health_state_smoke.py
agent_id: agt_enroll_health_smoke_20260618064218
token_id: agtok_agt_enroll_health_smoke_20260618064218_local_demo_19b8b6a6325f
states verified: never_seen -> fresh -> stale -> revoked
token_omitted: true
cleanup_revoked: 1
```

The Agent Gateway CLI status smoke passed:

```text
script: python3 scripts/agentops_status_smoke.py
agent_id: agt_status_cli_smoke_20260618064953
token_id: agtok_agt_status_cli_smoke_20260618064953_local_demo_20bc50880c02
states verified: never_seen -> fresh, revoked token rejected
prefix global args supported: true
token_omitted: true
```

The `/workspace/agents` Agent Gateway status card was added and frontend build passed:

```text
npm run build
Agent Gateway card shows ready/auth mode/workspace/scope count/active enrollments/stale heartbeats.
```

The workspace isolation smoke passed:

```text
script: python3 scripts/workspace_isolation_smoke.py
workspace A token pulled only workspace A task: pull_count=1
workspace B task did not leak into pull results
header spoof: forbidden
query spoof: forbidden
cross-workspace claim: forbidden
cross-workspace run start: forbidden
matching workspace run heartbeat: completed
token_omitted: true
latest verified run: run_gw_0b11e7514de6
```

MIS stores token hashes only. Raw token values are shown once at creation time and are not written into audit or runtime events.

The remote-token worker smoke also passed:

```text
script: python3 scripts/remote_agent_token_worker_smoke.py
agent_id: agt_remote_worker_smoke_20260618064228
token_id: agtok_agt_remote_worker_smoke_20260618064228_local_demo_2fd708d4aed4
task_id: tsk_remote_worker_smoke_20260618064228
run_id: run_gw_f61363bdf61d
run_status: completed
tool_calls: 1
evaluations: 1
token_omitted: true
revoked: 1
```

The knowledge-base bot customer task smoke passed:

```text
script: python3 scripts/kb_bot_demo_smoke.py
project_id: 20260617185442
created tasks: 6
created runs: 6
created tool_calls: 6
created evaluations: 6
created memories: 6
created runtime_events: 54
created audit_logs: 55
created artifacts: 1
pending approval: ap_gw_f289a8baafcd
delivery artifact: art_kb_bot_delivery_20260617185442
external_upload_performed: false
credentials_stored: false
raw_documents_stored: false
```

The delivery artifact is written through:

```http
POST /api/agent-gateway/artifacts
```

It stores a customer-readable title, summary, URI, and content hash metadata only. It does not store raw source documents, credentials, or full private transcripts.

The live UI ledger pass also passed:

```text
page: /workspace/approvals
source: GET /api/approvals
rows: 12
latest pending approval: ap_gw_f289a8baafcd
actions: approve/reject buttons call POST /api/approvals/:id/approve|reject

page: /admin/toolcalls
source: GET /api/tool-calls
rows: 6928
latest tool: artifact.delivery_summary

page: /admin/tasks/tsk_kb_bot_20260617185442_06
source: GET /api/tasks/tsk_kb_bot_20260617185442_06
delivery artifacts: 1
artifact: art_kb_bot_delivery_20260617185442
```

These pages no longer use `mockData` for the primary ledger rows.
Task detail now surfaces delivery artifacts and links related runs to Run Detail.

The browser-facing knowledge-base bot workflow API smoke also passed:

```text
script: python3 scripts/kb_bot_workflow_api_smoke.py
endpoint: POST /api/workflows/kb-bot-project
project_id: 20260617190650
steps: 6
final task: tsk_kb_bot_20260617190650_06
final run: run_gw_b365e7e325c6
delivery artifact: art_kb_bot_delivery_20260617190650
pending approval: ap_gw_8002e643f058
```

This is the same path used by Pixel Office's "Generate KB bot project" action.

The approval decision side-effect smoke passed:

```text
script: python3 scripts/approval_decision_side_effect_smoke.py
approved approval: ap_gw_fd2603a88c4f
approved tool: tc_gw_ddbecfc76ebd -> completed
approved run: run_gw_ccf41fbdd066 -> completed
approved task: tsk_kb_bot_20260617191012_03 -> completed
rejected approval: ap_gw_62f7412387d7
rejected tool: tc_gw_f3348b639fa3 -> blocked
rejected run: run_gw_ff3d3fbc5a90 -> blocked
rejected task: tsk_kb_bot_20260617191013_03 -> blocked
reason preservation: passed
```

The local CLI install smoke passed:

```text
script: python3 scripts/agentops_cli_install_smoke.py
installed command: agentops
temporary shim help: passed
token_written: false
```

On this machine, `python3 scripts/install_agentops_cli.py --force` installed:

```text
~/.local/bin/agentops -> repo scripts/agentops shim
```

Latest repeat run after adding the enrollment UI:

```text
script: python3 scripts/remote_agent_token_worker_smoke.py
agent_id: agt_remote_worker_smoke_20260617170534
token_id: agtok_agt_remote_worker_smoke_20260617170534_local_demo_7b3ddaeda24a
task_id: tsk_remote_worker_smoke_20260617170534
run_id: run_gw_4b4e7af5275c
run_status: completed
tool_calls: 1
evaluations: 1
token_omitted: true
revoked: 1
```

Latest repeat run after adding worker fleet telemetry:

```text
script: python3 scripts/remote_agent_token_worker_smoke.py
agent_id: agt_remote_worker_smoke_20260617180040
token_id: agtok_agt_remote_worker_smoke_20260617180040_local_demo_a1a3ca715719
task_id: tsk_remote_worker_smoke_20260617180040
run_id: run_gw_38fe52256f67
run_status: completed
tool_calls: 1
evaluations: 1
token_omitted: true
revoked: 1
```

The `/workspace/agents` enrollment UI was verified in the in-app browser:

```text
url: http://127.0.0.1:19001/workspace/agents
visible labels:
  AI 员工
  本地 Worker 循环
  远程 Agent 接入
  创建接入 token
  最近接入记录
```

The UI reads:

```http
GET /api/agent-gateway/enrollments
```

and can call:

```http
POST /api/agent-gateway/enrollment/create
POST /api/agent-gateway/enrollment/revoke
POST /api/agent-gateway/enrollment/rotate
```

Raw tokens are displayed only in the create/rotate response panel and are not persisted in frontend state beyond the current page session.

The `/workspace/agents` worker fleet telemetry UI was verified in the in-app browser:

```text
url: http://127.0.0.1:19001/workspace/agents
visible labels:
  Worker Fleet 观测
  Daemon 日志
  最近网关事件
  mock
  hermes
  openclaw
```

The log API also returned daemon log evidence:

```text
GET /api/workers/local/logs?adapter=mock
adapter: mock
status: stopped
log_tail_lines: 80
log_path_present: true
```

`python3 scripts/demo_acceptance.py` also passed after this UI change.

## What This Proves

The v1.5 worker loop can process normal MIS tasks, not just connector probes:

```text
planned MIS task
  -> Agent Gateway task pull
  -> claim
  -> run start
  -> adapter execution
  -> tool call record
  -> run heartbeat completed/failed
  -> evaluation submit
  -> audit emit
  -> optional memory proposal
```

## Boundaries

- Hermes/OpenClaw live execution requires `--confirm-run`.
- The worker does not call Dify or Notion.
- The worker does not store full prompts or raw responses.
- The worker is repo-local; it is not yet a launchd service, pip package, npm package, or signed binary.
- The UI worker panel now supports one-shot dispatch, local daemon start/stop, daemon state counters, daemon log tails, and recent gateway events; it is not a production fleet manager.
- Remote enrollment token issuance/revocation/rotation, endpoint-level scope enforcement, scope presets, a first enrollment UI, and minimal Agent Gateway workspace isolation now exist. Full RBAC, hosted multi-tenant isolation, short-lived sessions, and production enrollment workflows remain future work.
