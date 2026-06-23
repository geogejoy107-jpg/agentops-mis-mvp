# AgentOps MIS v1.5 Eight Product Closure Spec

## One-Sentence Goal

AgentOps MIS v1.5 should prove that a normal MIS task can be assigned to a local or external AI worker, executed through a real adapter loop, and written back into the MIS ledger with run, tool, evaluation, memory, approval, and audit evidence, excluding Dify and Notion live-sync tracks.

## Scope Boundary

This spec covers the eight non-Dify/Notion product gaps identified during v1.5 planning.

Excluded from this closure spec:

- Dify live dataset upload and deployed chatbot hosting.
- Notion bidirectional sync.
- Future SaaS billing, hosted multi-tenant deployment, and marketplace
  connectors are excluded from this local closure spec.

## Product Objective

Move AgentOps MIS from a dashboard/mock demo into a usable local control plane where AI workers can:

1. Register or enroll.
2. Pull real MIS tasks.
3. Claim work.
4. Execute through mock, Hermes, or OpenClaw adapters.
5. Write run/tool/evaluation/audit evidence.
6. Be started, stopped, or observed by a human operator.
7. Use scoped tokens when running outside the browser or on another machine.

The product boundary is deliberate: humans use the browser workspace/admin
console to create goals, supervise status, approve risky actions, and review
artifacts; AI workers use Agent Gateway CLI/API/MCP to execute. A dogfood run
must not prove value by having an agent click the UI. It must prove that a
normal customer task can be dispatched through the machine-facing contract and
then become visible in the human-facing ledger, approvals, evaluations, audit,
and artifact views.

Open-source projects can accelerate the tool layer but cannot replace the MIS
authority layer. v1.5 follows `docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md`:
SQLite, GitHub Actions, FTS5, secret scanners, SBOM tooling, Git worktrees and
protocol SDKs may be adopted directly; Spec Kit, Aider, LangGraph, OPA/Cedar,
SWE-agent, Agentless, Mem0/Zep/Letta and virtual-office projects are
reference-only unless wrapped behind Agent Gateway/runtime/connector boundaries.
Agent Plan, Run, Tool Call, Approval Wall, Workspace Scope, Memory Governance,
Customer Delivery and Audit remain first-party MIS modules.

v1.5 also makes the human operator role explicit as a commander-style async
management loop. The commander does not need to hold a single synchronous
request open while Hermes, OpenClaw, or a remote worker finishes. Instead, the
product exposes:

- Local readiness through `GET /api/local/readiness` and `agentops local
  readiness`.
- Lightweight operator runtime doctor through `GET /api/operator/runtime-doctor`
  and `agentops operator runtime-doctor`, so a human/Codex/Hermes/OpenClaw
  operator can check MIS API reachability, adapter readiness, remote worker
  fleet state, launch-packet availability, handoff evidence counts,
  `--confirm-run`, prepared-action walls, redaction boundaries, and copyable
  full-health/handoff commands before dispatching live work.
- A commander project board through `GET /api/commander/project-board` with
  readiness, worker health, recent work packages, pending approvals, artifacts,
  memory candidates, workflow jobs, integration gates, and recommended next
  actions.
- A commander work-package planner through
  `POST /api/commander/work-packages/plan` and
  `agentops commander plan`, with safe preview by default and confirmed task
  creation only when `confirm_create:true` / `--confirm-create` is provided.
- Persisted commander work-package readback through
  `GET /api/commander/work-packages` and `agentops commander packages`, so a
  customer can refresh the app and still see lane status, latest run, evidence
  counts, dependencies, verification commands, repo-map localization artifacts,
  and next actions.
- Read-only coding-task localization through `GET /api/commander/repo-map` and
  `agentops commander repo-map`, so an agent or operator can identify relevant
  repo files, symbols, redacted snippets, content hashes, and source
  provenance within a token budget before changing code. This is a planning and
  retrieval aid only; it does not mutate the ledger or replace Agent Plan,
  Approval Wall, test, or merge gates.
- Async workflow job submission, polling, listing, stuck-job detection, and
  operator mark-failed recovery for customer worker and template jobs.
- An async integration inbox at `GET /api/commander/integration-inbox` for
  returned worker results, running lanes, blocked work, stale work and memory
  review.
- Operator action receipts through `GET/POST /api/operator/action-receipts`,
  embedded back into `operator action-plan` and `operator loop-audit`, so copied
  recovery commands can be paired with VERIFY commands and preserved in the
  audit/runtime ledger.
- Knowledge search now carries workspace/project/access metadata. Repo doctrine
  is indexed as `global/internal`, scoped Agent Gateway tokens can only retrieve
  `global` plus their own workspace documents, and redaction happens before FTS
  indexing or snippet return.
- Local readiness now surfaces Knowledge Index evidence alongside memory
  governance: `GET /api/local/readiness` and `agentops local readiness` expose
  knowledge document/chunk/FTS counts, workspace-visible knowledge counts, and a
  `knowledge_memory` next action that routes to `agentops knowledge search` when
  indexed knowledge exists. Retrieval quality remains proven by the dedicated
  smoke instead of inferred from counts alone.
- CLI/API-first execution for agents, with browser pages reserved for command,
  supervision, approval, and review.
- Real Hermes/OpenClaw dogfood evidence in the ledger, cited by run ID and
  summarized metadata only.

Parallel product work should use
`docs/PARALLEL_PRODUCT_DELIVERY_BRANCH_PLAN.md` as the branch ownership and
handoff map. It keeps remote worker, customer task flow, RBAC, fleet console,
and demo/documentation workstreams separated while preserving the same
CLI/API-first agent execution contract.

The current hardening overlay is
`docs/V1_5_AGENT_GATEWAY_HARDENING_OBJECTIVE.md`. It captures the P0 gates from
the first `audit/v1-5-agent-gateway-hardening` review: immutable Agent Plan
binding, approval role separation, prepared-action Approval Wall, redaction,
workspace/knowledge visibility, SQLite reliability, CI, and public-claim
limits. Treat that file as the release-candidate blocker list before adding
more horizontal product features.

## Product Validation Rule

Product-readiness and dogfood claims must use real Hermes/OpenClaw execution
when the local runtimes are available and explicitly authorized. Mock adapter
evidence is allowed for deterministic CI, offline development, and safety
fallbacks only; it must be labeled as mock/offline evidence and must not be
presented as product-level completion. Real Hermes/OpenClaw validation still
uses the MIS safety contract: explicit `confirm_run`, prepared-action approval
where required, summary/hash ledger storage, and no raw prompt, raw response,
credential, private-message, or full-transcript persistence.

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
- Worker state records `consecutive_idle`, `last_sleep_sec`, `next_sleep_sec`, `last_sleep_reason`, and `session_refresh_count`.
- `--use-session` workers refresh short-lived Agent Gateway sessions before expiry in loop mode.
- Uses Agent Gateway HTTP API instead of direct SQLite writes.
- Local daemon supervisor APIs:
  - `GET /api/workers/status`
  - `GET /api/workers/local/logs`
  - `POST /api/workers/local/start`
  - `POST /api/workers/local/stop`
  - `POST /api/workers/local/restart`
- Operator restart controls are exposed through `agentops worker restart` and
  `/workspace/agents`; Hermes/OpenClaw restart still requires explicit
  `confirm_run` before any live daemon is stopped or started.

Acceptance evidence:

- Daemon auto-pull run: `run_gw_6ad797929084`
- Persistent daemon smoke: `max_tasks=0` showed running status and stopped cleanly.
- Resilience smoke: `python3 scripts/worker_daemon_resilience_smoke.py`
  - latest server daemon processed task `tsk_worker_daemon_resilience_20260618091145`
  - wrote run `run_gw_29d23509f62e`
  - exposed `processed=1`, `iterations=1`, JSONL `worker.iteration`, and local state path
  - direct bad-URL worker recorded two errors and exited after `max_errors`
  - direct bad-URL worker exposed `last_sleep_reason=error_backoff` and `last_sleep_sec=0.1`.
- Restart smoke: `python3 scripts/agentops_worker_restart_smoke.py`
  - Hermes restart without `confirm_run` failed closed.
  - Mock restart returned running daemon metadata through CLI/API.
  - Restart output omitted token/session/secret-like strings.
  - Cleanup stopped the mock daemon.

Remaining product work:

- OS-managed relaunch path is available but still explicit-operator controlled:
  v1.5 has safe template generation through `agentops-worker service-template`
  with launchd `KeepAlive=true` and systemd `Restart=always`, dry-run-by-default
  file installation through `agentops-worker service-install`, read-only
  machine-readable relaunch diagnostics through `agentops-worker service-check`,
  and preview-first OS service load/unload/restart through
  `agentops-worker service-control` / `agentops worker service-control`; real
  launchd/systemd mutation requires `--confirm-control`.
- Full hosted/production service orchestration after process death remains out
  of v1.5; local/BYOC operators get safe service templates plus explicit load
  controls.
- Full production log management. v1.5 now rotates repo-local worker daemon logs on daemon start/restart using `AGENTOPS_WORKER_LOG_MAX_BYTES` and `AGENTOPS_WORKER_LOG_BACKUPS`; external launchd/systemd service logs still depend on the host log system.
- Production fleet manager remains out of scope. v1.5 now has safe local/BYOC
  fleet hygiene through API/CLI and `/workspace/workers`: operators can preview
  stuck task release plus stale remote enrollment/session cleanup, then apply it
  only after explicit cleanup confirmation. It never executes Hermes/OpenClaw
  live work and keeps token/session ids omitted.

### 2. OpenClaw / Hermes Adapter Loop

Goal:

- A normal MIS task should execute through local adapters and write results back into MIS.

Current v1.5 implementation:

- Worker adapter choices:
  - `mock`
  - `hermes`
  - `openclaw`
- Runtime connectors now include a minimal trust registry:
  - `trust_status`: `trusted`, `review_required`, or `blocked`
  - `trust_note`
  - `trust_updated_at`
  - `POST /api/runtime-connectors/:id/trust`
  - `/admin/connectors` trust controls
- Runtime connectors now carry a `runtime-capability-manifest-v1`:
  - `observation_level`
  - `capability_manifest_json`
  - `capability_policy_hash`
  - per-connector filesystem, shell, network, Git, external-write, secret,
    confirmation, trust-policy, and tool-event-ingestion declarations
  - Agent Gateway, OpenClaw, Hermes, Agnesfallback CLI, and Agnesfallback
    OpenAI-compatible gateway connector manifests through
    `GET /api/runtime-connectors` and `agentops runtime connectors`
  - Hermes/OpenClaw are intentionally marked `ledger_summary_only` and
    `restricted_until_runtime_tool_events` until internal tool events are
    ingested or risky external writes are routed through prepared actions.
- Hermes/OpenClaw real execution requires explicit `--confirm-run`.
- Hermes/OpenClaw customer worker live execution is blocked when the linked runtime connector has `trust_status=blocked`.
- Confirmed Hermes/OpenClaw customer worker tasks that declare or clearly imply
  external-write intent are paused before runtime invocation. MIS creates a
  waiting-approval task/run/tool call, an immutable prepared action, and a human
  approval, then returns `external_write_prepared_action_required` with a
  precise resume command instead of starting the opaque live runtime.
- Hermes adapter timeout is configurable through `--hermes-timeout` / `HERMES_TIMEOUT`; customer worker live dogfood uses a 300s Hermes window.
- Retryable adapter failures can be retried with `--adapter-max-attempts` and `--adapter-retry-delay-sec`.
- Non-retryable safety failures such as `ConfirmRunRequired` do not retry.
- Tool-call args, evaluation rubric, and audit metadata record `attempt_count`, `max_attempts`, and retry history summaries.
- Worker tool-call risk now respects adapter capability manifests: mock remains
  low risk, while Hermes/OpenClaw have a medium `risk_floor` and record
  `observation_level`, `commercial_readiness`, and
  `requires_prepared_action_for_external_write` in tool-call args, evaluation
  rubric, and audit metadata.
- Adapter output is summarized and hashed; raw prompt/response is not stored.
- `GET /api/runtime-connectors`, `agentops runtime connectors`,
  `GET /api/workers/adapter-readiness`, and `agentops worker readiness` expose
  these manifests to operators and external agents without executing live work.

Acceptance evidence:

- Mock run: `run_gw_a20e5b2eb6e3`
- Hermes run: `run_gw_0d793ed6bbac`
- OpenClaw run: `run_gw_9b2a6550d489`
- Live recheck on 2026-06-18:
  - Hermes worker task `tsk_worker_hermes_live_20260618065503` completed as `run_gw_6f995c9de929`.
  - OpenClaw worker task `tsk_worker_openclaw_live_20260618065555` completed as `run_gw_c274e7d62b61`.
- Customer worker live dogfood on 2026-06-20:
  - Hermes completed customer worker run `run_gw_4b92508d1e33` with artifact `art_customer_worker_task_run_gw_4b92508d1e33`.
  - OpenClaw completed customer worker run `run_gw_328d56c280fa` with artifact `art_customer_worker_task_run_gw_328d56c280fa`.
  - Both runs wrote run/tool/evaluation/runtime/audit/artifact evidence.
- Customer worker live dogfood on 2026-06-21:
  - `python3 scripts/customer_worker_live_dogfood.py --adapter openclaw --adapter hermes --request-timeout 720 --hermes-timeout 600`
  - OpenClaw completed `run_gw_7ede8c8cc5c9` with artifact `art_customer_worker_task_run_gw_7ede8c8cc5c9`.
  - Hermes completed `run_gw_1e864c5f6b18` with artifact `art_customer_worker_task_run_gw_1e864c5f6b18`.
  - Both runs used Agent Gateway CLI/API execution, not browser automation, and wrote tool/evaluation/runtime/audit/artifact/memory/approval evidence.
- Latest commander-management live proof on 2026-06-21:
  - OpenClaw completed `run_gw_5f4a3320a4d3` from task `tsk_worker_ui_openclaw_20260621114057_4f5cbc75`.
  - Hermes completed `run_gw_f7fe3a78cadb` from task `tsk_worker_ui_hermes_20260621114203_9e6cc64a`.
  - The local ledger shows completed status plus tool/evaluation/audit/artifact evidence for both runs.
  - These are real live run IDs, not hard-coded fixtures; docs cite IDs and counts only, without raw prompts, raw responses, credentials, or private transcripts.
- Latest normal customer-worker live acceptance on 2026-06-23:
  - Current-code combined evidence command: `python3 scripts/v1_5_current_code_product_evidence.py --base-url http://127.0.0.1:<current-code-port> --db-path /tmp/<current-code-agentops>.db --confirm-live`; this covers knowledge indexing, Commander synthesis, real Hermes/OpenClaw customer-worker runs, live readiness readback, remote/scoped worker mock fallback, and final non-live local acceptance.
  - `python3 scripts/customer_worker_real_runtime_acceptance.py --base-url http://127.0.0.1:8787 --confirm-live --adapter hermes --adapter openclaw --request-timeout 900 --hermes-timeout 480`
  - `python3 scripts/v1_5_live_product_readiness_smoke.py --require-adapter hermes --require-adapter openclaw`
  - Hermes completed `run_gw_ee70f20c021c` from task `tsk_worker_ui_hermes_20260623062626_2fc8c2b3`, with artifact `art_customer_worker_task_run_gw_ee70f20c021c`, approval `ap_customer_worker_delivery_run_gw_ee70f20c021c`, plan `plan_a1c439e073775da1`, and manifest `pem_daf7d404a2e9024b`.
  - OpenClaw completed `run_gw_4a58476b7d09` from task `tsk_worker_ui_openclaw_20260623062652_7e64b47f`, with artifact `art_customer_worker_task_run_gw_4a58476b7d09`, approval `ap_customer_worker_delivery_run_gw_4a58476b7d09`, plan `plan_9dd24ddbffbd74a2`, and manifest `pem_1e63d0f6dcd96bf5`.
  - Both runs wrote tool_calls 1, evaluations 1, runtime_events 14, audit_logs 7, artifacts 2, memories 2, approvals 1, and plan_evidence_manifests 1, and CLI readback showed `token_omitted:true`.
- Generic customer worker governance closure on 2026-06-20:
  - Mock completed `run_gw_161d789c4469`.
  - Hermes completed `run_gw_5d998a53e469`.
  - OpenClaw completed `run_gw_4c3b2d5b43ac`.
  - Each customer worker result now includes tool/evaluation/runtime/audit/artifact evidence plus memory candidate and pending delivery approval evidence.
- Runtime connector trust smoke:
  - `python3 scripts/runtime_connector_trust_smoke.py`
  - blocked `rtc_openclaw_local`
  - OpenClaw customer worker live execution returned `runtime_connector_trust_blocked`
  - blocked task `tsk_customer_worker_trust_blocked_30651ba025db2763`
  - restored `rtc_openclaw_local` to `trusted`.
- Runtime capability manifest smoke:
  - `python3 scripts/runtime_capability_manifest_smoke.py --base-url http://127.0.0.1:8787`
  - verifies Agent Gateway, OpenClaw, Hermes, Agnesfallback CLI and Agnesfallback API connector manifests through both API and CLI readback;
  - confirms no live execution and no token/raw prompt/raw response leakage.
- `python3 scripts/worker_adapter_retry_smoke.py` verified adapter retry behavior:
  - mock transient failure succeeded after two attempts in `run_gw_a572f60ec9f4`,
  - Hermes without `--confirm-run` stopped after one non-retryable `ConfirmRunRequired` attempt in `run_gw_9951c583b9a7`,
  - raw token output remained omitted.
- `python3 scripts/worker_prompt_profile_smoke.py` verifies task-to-runtime
  prompt profile v1:
  - worker classifies coding, knowledge-base, review/quality-gate, and general
    customer tasks into distinct profile ids;
  - each profile has a stable `worker_prompt_profiles_v1` version and
    `prompt_profile_hash`;
  - tool calls, evaluation rubrics, audit metadata, external-write
    prepared-action metadata, and worker JSON output carry
    `prompt_profile_id`, `prompt_profile_version`, and `prompt_profile_hash`;
  - raw prompt/raw response/token material remains omitted.
- `python3 scripts/customer_worker_external_write_gate_smoke.py` verifies that
  a confirmed Hermes customer-worker task with `external_write_intent:true`
  returns `202`, writes task/run/tool/prepared-action/approval/runtime/audit
  evidence, keeps `live_execution_performed:false`, and does not leak
  token-like values.

Remaining product work:

- Rich runtime trust policy beyond the current trusted/review/blocked MVP.
- Prompt profile v1 is ledger-visible; future work can add customer-editable
  profile policies and per-template profile overrides.
- Generalize the same prepared-action entry gate to every high-risk
  external connector/runtime side-effect path before shared/commercial
  deployment.

### 3. Installable CLI Package

Goal:

- Agents and operators should have a stable CLI/API surface without depending on browser clicks.

Current v1.5 implementation:

- `scripts/agentops`
- `agentops_mis_cli/agentops.py`
- `scripts/install_agentops_cli.py` installs a local user shim at `~/.local/bin/agentops`.
- `pyproject.toml` exposes `agentops` as a Python console script through package `agentops-mis-cli`.
- `scripts/agentops` remains a repo-local compatibility wrapper around `python -m agentops_mis_cli`.
- `agentops_mis_cli/_build_backend.py` builds the pure-Python CLI package without downloading setuptools/wheel, which keeps local/remote source installs usable in restricted networks.
- Commands include:
  - `agentops login`
  - `agentops doctor`
  - `agentops status`
  - `agentops enrollment create/list/revoke/rotate`
  - `agentops agent register`
  - `agentops agent heartbeat`
  - `agentops task create`
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
  - `agentops workflow templates`
  - `agentops workflow run-template`
  - `agentops workflow customer-worker-task`
  - `agentops workflow job-status`
  - `agentops workflow run-task`
  - `agentops worker status`
  - `agentops worker preflight`
  - `agentops worker start`
  - `agentops worker logs`
  - `agentops worker stop`
  - `agentops worker stuck`
  - `agentops worker release`

Acceptance evidence:

- CLI enrollment smoke passed with `agt_remote_cli_smoke`.
- Revoked token was rejected.
- Local CLI install smoke passed: `python3 scripts/agentops_cli_install_smoke.py`.
- Pip source-package install smoke passed: `python3 scripts/agentops_pip_install_smoke.py`.
- CLI doctor smoke passed: `python3 scripts/agentops_doctor_smoke.py`.
- CLI status smoke passed: `python3 scripts/agentops_status_smoke.py`.
- CLI worker status smoke passed: `python3 scripts/agentops_worker_status_smoke.py`.
- CLI worker preflight smoke passed: `python3 scripts/agentops_worker_preflight_smoke.py`.
- CLI worker service install smoke passed: `python3 scripts/agentops_worker_service_install_smoke.py`.
- CLI worker service diagnostics smoke passed: `python3 scripts/agentops_worker_service_check_smoke.py`.
- CLI worker daemon controls smoke passed: `python3 scripts/agentops_worker_daemon_cli_smoke.py`.
- CLI customer worker workflow smoke passed: `python3 scripts/agentops_customer_worker_cli_smoke.py`.
- CLI customer template workflow smoke passed: `python3 scripts/agentops_workflow_template_cli_smoke.py`.
- Live adapter confirm gate smoke passed: `python3 scripts/worker_live_confirm_gate_smoke.py`.
- Current machine has `~/.local/bin/agentops` installed as a shim to this repo.

Remaining product work:

- Published pip/Homebrew/npm packaging.
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
- Worker loop session refresh is supported through `agentops-worker --use-session --session-refresh-margin-sec`; `scripts/agent_worker.py` remains a repo-local compatibility wrapper.
- The parent enrollment token stays only in worker process memory for refresh; task/register/writeback calls use the short-lived session token.
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
- Task claim now has a multi-worker guard:
  - multiple agents may see a public pool task before claim,
  - the first claim moves it to `running` and binds `owner_agent_id`,
  - same-agent repeat claim is idempotent,
  - another agent cannot claim or start the already claimed task.
- Worker recovery now has a local operator loop:
  - `GET /api/workers/stuck-tasks` detects stale running worker tasks,
  - `POST /api/workers/tasks/release` returns a stuck task to `planned`,
  - linked running runs are marked `blocked` with `WorkerTaskReleased`,
  - `/workspace/agents` surfaces stuck task count and release controls.
- `GET /api/workers/status` and `agentops worker status` now summarize remote worker fleet health from enrollment/session metadata:
  - active remote worker count,
  - total historical enrollments,
  - fresh/stale/never-seen heartbeat counts,
  - active short-lived session counts,
  - recent remote worker rows with token/session IDs omitted.
- Agent Gateway can now record customer delivery artifacts with `artifacts:write`, so remote workers can submit report summaries without raw customer content.
- `/workspace/agents` exposes a first operator UI for creating, viewing, and revoking scoped enrollment tokens.
- `/workspace/agents` exposes approval-gated enrollment request controls: request approval, approve/reject enrollment requests, and issue approved tokens.
- `/workspace/agents` also exposes scope presets and per-token rotation.
- Enrollment policy preview now exists before token issue:
  - `POST /api/agent-gateway/enrollment/policy-preview`
  - `agentops enrollment policy-preview`
  - `/workspace/agents` renders a live read-only scope policy card.
  - The preview classifies observer / worker / privileged / invalid scope sets, recommends direct create vs approval-gated request, highlights invalid and privileged scopes, and proves no token issuance, ledger mutation, or live execution occurred.
- `/workspace/agents` exposes recent short-lived sessions and can revoke an active session directly.
- `/workspace/agents` surfaces Agent Gateway readiness/auth mode/scope count/active enrollment/stale heartbeat cards for operators.
- `/workspace/agents` now includes an operator readiness strip for self-dogfooding and customer operations. It explains local worker mode, confirmed Hermes/OpenClaw live dispatch, remote agent entry, and stuck-task recovery before the detailed gateway/worker/enrollment panels.
- New/rotated enrollment responses include a safe `next_steps` launch packet for remote machines: package install, env setup, `agentops status`, `agentops-worker preflight`, heartbeat, one-shot `agentops-worker`, loop `agentops-worker`, launchd/systemd template/install/check commands, and repo-local fallback worker commands. Commands use an API-key placeholder rather than embedding the raw token.
- Launch-packet worker commands now use `--use-session --session-ttl-sec 900`, so remote workers mint a short-lived session before processing tasks instead of holding the enrollment token in the worker loop.
- `agentops worker readiness` and `GET /api/workers/adapter-readiness` now
  expose `worker_connection_policy` (`agentops-worker-connection-policy-v1`):
  short-lived session refresh defaults, idle/error backoff caps, adapter retry
  semantics, daemon `continue_on_error` / `max_errors`, state/log fields, and
  copyable verification commands.

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
  - session `[AGENT_GATEWAY_SESSION_REDACTED]`
- 2026-06-22 revalidation of the remote worker product path passed
  `python3 scripts/remote_worker_product_acceptance.py`:
  - direct remote token worker run `run_gw_c65670dafaf8`
  - launch-packet short-lived-session run `run_gw_860a79aee458`
  - both stayed on the mock adapter, performed no live runtime execution, and
    omitted token/session secrets.
  - the smoke pins its just-created task with `--task-id` and uses
    `--no-enforce-intake` for the first self-planning worker execution; the
    worker still creates/verifies an Agent Plan before `run_start` and then
    writes a verified plan-evidence manifest after execution evidence.
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
- `python3 scripts/task_claim_conflict_smoke.py` verified multi-worker claim safety:
  - two agents initially saw the same public pool task,
  - the first claim won,
  - repeat claim by the same agent was idempotent,
  - the second worker could not claim or start the claimed task,
  - proof run `run_gw_f3766b73044d`.
- `python3 scripts/worker_stuck_recovery_smoke.py` verified stuck worker recovery:
  - stale running worker task was detected,
  - release returned task `tsk_worker_stuck_20260618152538` to `planned`,
  - linked run `run_gw_988eb825e20e` was marked `blocked`.
- `python3 scripts/worker_session_refresh_smoke.py` verified loop-mode short-lived session refresh:
  - worker `agt_session_refresh_worker_20260618153329` processed two tasks,
  - runs `run_gw_1a886228c52d` and `run_gw_d43859ff81e3` completed,
  - sessions refreshed from `[AGENT_GATEWAY_SESSION_REDACTED]` through `[AGENT_GATEWAY_SESSION_REDACTED]`,
  - `session_refresh_count=2`,
  - raw token output remained omitted.
- `python3 scripts/worker_remote_fleet_status_smoke.py` verified `agentops worker status` shows a remote worker through `never_seen -> fresh -> stale`, counts active sessions, and omits raw token/session identifiers.
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
- `python3 scripts/enrollment_policy_preview_smoke.py` verified read-only enrollment policy:
  - OpenClaw worker scopes are classified as `worker` and recommend approval.
  - Local observer scopes are classified as `observer` and can use direct create.
  - Invalid scopes are blocked before token issue.
  - CLI output omits token/session/secret-like strings.
- `python3 scripts/enrollment_hosted_policy_ui_smoke.py` verifies deployment-aware enrollment policy UI:
  - local low-risk observer scopes can use direct token creation,
  - hosted/shared mode forces approval request and admin-issued token flow,
  - `/workspace/agents` shows the deployment gate and disables direct create when policy blocks it.

Remaining product work:

- Full hosted enrollment administration remains future SaaS work: customer org enrollment pages, token issuance audit review by workspace owner, and production-grade RBAC administration.

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
- Runtime connector trust registry can block a live Hermes/OpenClaw customer worker before adapter execution.
- `.agentops_runtime/`, local DB, node modules, and build output are gitignored.

Acceptance evidence:

- DB check confirmed no `agtok_` raw token in audit metadata.
- `agent_gateway_tokens` table has `token_hash`, not raw token.
- `python3 scripts/redaction_policy_smoke.py` passed.
- HTTP write/read proof `run_gw_dc141fcaab51` preserved `127.0.0.1:8642` and task id text without `[PHONE_REDACTED]`.

Remaining product work:

- Full RBAC.
- Future multi-tenant hosted isolation beyond this local SQLite MVP.
- Secret manager.
- Rich connector trust policy UI beyond the current local trusted/review/blocked controls.

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
- `/workspace/agents` also surfaces local readiness, adapter route readiness,
  async workflow jobs, stuck workflow-job recovery, and the async integration
  inbox for commander review of work that returns at different speeds.
- `/workspace/agents`, `GET /api/operator/execution-mode`, and
  `agentops operator execution-mode` share a read-only execution-mode contract:
  selected adapter path, dry-run/mock vs live-confirmed vs confirmation-missing
  vs adapter-blocked state, confirm-run wall, prepared-action wall, pending
  approval count, active async jobs, and copyable next commands.
- `/workspace/workers` provides the dedicated Worker Control Console: it reads
  real worker status, fleet health, adapter readiness, and operator
  execution-mode state, then exposes focused one-shot dispatch, local daemon
  start/restart/stop controls, ledger links, safety badges, and an explicit
  live-confirm wall for Hermes/OpenClaw.
- `/workspace/approvals` reads live approvals from the backend and can approve/reject through the real API.
- `/admin/toolcalls` reads live tool-call evidence from the backend instead of mock data.
- `/admin/tasks/:id` shows delivery artifacts and links related runs to their Run Detail pages.
- Approval decisions preserve the original approval reason and synchronize linked tool/run/task status: approval completes the tool without overwriting completed run output; rejection blocks the tool, run and task.
- Browser verification confirmed the controls render.
- The Agent Gateway card shows gateway readiness, auth mode, workspace, scope count, active enrollments, and stale heartbeats.
- `/admin/connectors` shows runtime trust controls for trusted/review/blocked decisions.

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
- `python3 scripts/operator_execution_mode_smoke.py` verifies the execution-mode
  API and CLI are scoped, read-only, non-mutating, and redacted.
- `python3 scripts/worker_console_ui_smoke.py` verifies `/workspace/workers`,
  sidebar/home entry points, live Worker API wiring, dispatch/daemon controls,
  fleet hygiene preview/apply controls, ledger links, and the live-confirm
  safety wall.
- `python3 scripts/customer_dispatch_desk_ui_smoke.py` verifies
  `/workspace/dispatch`, sidebar/home entry points, live workflow API wiring,
  template/worker dispatch controls, delivery board visibility, and the
  live-confirm/prepared-action safety language.
- `python3 scripts/task_detail_evidence_ui_smoke.py` verifies task detail
  now exposes an execution-posture strip for runtime mode, approval wall, and
  delivery gate. The strip distinguishes Hermes/OpenClaw live evidence from
  mock/offline evidence, shows pending approval state, and keeps customers from
  inferring delivery readiness only from raw run tables.
- `python3 scripts/run_detail_evidence_ui_smoke.py` verifies run detail now
  exposes a run evidence-chain strip across tool calls, evaluations, artifacts,
  approvals, audit references, benchmark cases and live/mock runtime posture.
  This gives operators a single readback for whether a run has enough evidence
  to support delivery review.

Remaining product work:

- Further polish for live/dry-run/approval state indicators across secondary
  customer-facing task flows beyond Dispatch Desk, Worker Console, Task Detail
  and Run Detail.

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
- Customer task templates are available through `GET /api/workflows/customer-task-templates`.
- A selected template can be launched through `POST /api/workflows/customer-task-templates/run`.
- `tpl_local_coding_project` launches a local coding-project workflow that
  creates Commander work packages with task-bound repo-map localization,
  branch/worktree constraints, patch/test/verifier requirements and merge-gate
  commands, without creating a worktree, storing raw source, merging, pushing,
  or running live Hermes/OpenClaw by default.
- Commander coding work packages now have an explicit local coding evidence
  checkpoint: after a worker dispatch produces a run, `agentops commander
  coding-evidence --confirm-record` writes summary/hash-only worktree, patch,
  test, verifier, merge-gate, evaluation, runtime and audit evidence back into
  MIS. `agentops commander coding-workspace` and
  `coding-workspace-cleanup` are preview-first, with real worktree creation or
  cleanup requiring explicit confirmation.
- External agents and operators can list and launch those templates through
  `agentops workflow templates` and `agentops workflow run-template`, which
  keeps machine-facing dispatch on CLI/API instead of browser UI clicks.
- `agentops workflow run-template --adapter mock|hermes|openclaw` maps a
  selected template into the Agent Worker loop. Hermes/OpenClaw require
  `--confirm-run`; long live runs use `--request-timeout` or
  `AGENTOPS_REQUEST_TIMEOUT`.
- Long customer template runs can be submitted asynchronously with
  `agentops workflow run-template --async-job` and polled through
  `agentops workflow job-status --wait`, avoiding brittle long-lived HTTP
  requests while preserving ledger evidence.
- Pixel Office surfaces recent async workflow jobs in the customer dispatch
  panel, including job status, adapter/template id, final task/run links, and
  artifact id.
- Pixel Office's customer dispatch panel loads local templates, applies their default title/brief/acceptance criteria, and can run the selected template.
- Customer projects can export a safe ledger-backed delivery report through `GET /api/workflows/customer-projects/:project_id/report`.
- Pixel Office surfaces the report link after template-backed project generation.
- Pixel Office can persist the generated customer project report back into the MIS ledger through the `Archive report to ledger` / `归档报告到账本` action.
- The report link routes to `/workspace/customer-projects/:project_id/report`, a customer-facing page that renders report metrics, safety boundaries, ledger ids, and markdown content instead of raw JSON.
- Reports can list recent customer projects through `GET /api/workflows/customer-projects`, so users can return to previous delivery reports and archive status.
- `/workspace/dispatch` is the first-class customer task intake page: it loads
  live agents through `loadDashboard()` + `loadAgents(metrics)`, reuses the
  `CustomerDispatchPanel`, links back to Pixel Office and Worker Console, and
  explains the CLI/API/MCP agent boundary plus Hermes/OpenClaw `confirm_run`
  and prepared-action gates.
- The same worker loop is now used for product dogfooding: Hermes/OpenClaw reviewed AgentOps MIS itself from a customer/one-person-company owner perspective and wrote run/tool/evaluation evidence.
- Task creation now returns a clear `400 owner_agent_not_found` when an administrator assigns work to an unregistered agent, instead of surfacing a database foreign-key failure.

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
- Customer task template smoke: `python3 scripts/customer_task_template_smoke.py`
  - historical template count at that time: `3`
  - template: `tpl_customer_kb_qa_bot`
  - project: `20260618154535`
  - final task: `tsk_kb_bot_20260618154535_06`
  - final run: `run_gw_cfde4c4822b1`
  - delivery artifact: `art_kb_bot_delivery_20260618154535`
  - pending external-upload approval: `ap_gw_956174266d1a`
- Customer Dispatch Desk UI smoke:
  `python3 scripts/customer_dispatch_desk_ui_smoke.py`
  - route: `/workspace/dispatch`
  - static-only safety proof: no live execution, no token material
  - verifies live workflow API markers and explicit real-runtime confirmation
    boundaries.
- Customer template workflow CLI smoke:
  `python3 scripts/agentops_workflow_template_cli_smoke.py`
  - commands: `agentops workflow templates`, `agentops workflow run-template`
  - historical template count at that time: `3`
  - project: `20260620165509944069`
  - final task: `tsk_kb_bot_20260620165509944069_06`
  - final run: `run_gw_5efecc40662f`
  - delivery artifact: `art_kb_bot_delivery_20260620165509944069`
  - pending external-upload approval: `ap_gw_63ba94be6f35`
  - report URL: `/api/workflows/customer-projects/20260620165509944069/report`
  - secret leakage check: `false`
- Live customer template worker dogfood:
  `python3 scripts/template_worker_live_dogfood.py --adapter openclaw`
  and manual Hermes run with `--request-timeout 420`
  - OpenClaw: `run_gw_f564c767fa0b`, artifact `art_customer_worker_task_run_gw_f564c767fa0b`
  - Hermes: `run_gw_99c4e69cae16`, artifact `art_customer_worker_task_run_gw_99c4e69cae16`
  - both wrote tool/evaluation/audit/artifact/memory/approval evidence
- Async customer template workflow smoke:
  `python3 scripts/agentops_workflow_async_job_smoke.py`
  - job: `wfjob_6cfffb10338d`
  - run: `run_gw_8eb6ebe95392`
  - artifact: `art_customer_worker_task_run_gw_8eb6ebe95392`
  - evidence: tool/evaluation/audit/artifact/memory/approval rows present
- Local coding project template evidence:
  - `python3 scripts/commander_coding_project_template_smoke.py`
  - `python3 scripts/local_coding_project_template_smoke.py`
  - verifies `tpl_local_coding_project`, repo-map localization artifacts,
    workspace dry-run preview, mock worker dispatch, coding evidence
    `confirm_record:true`, five coding evidence artifact types, evaluation,
    readback `coding_evidence_gate=recorded`, no live runtime execution, and no
    raw source/patch/token leakage.
- Pixel Office async job UI build/snapshot:
  - `cd ui/start-building-app && npm run build`
  - Playwright snapshot on `/workspace/pixel-office` shows `异步 Workflow Jobs`
    with job `wfjob_6cfffb10338d`, run link `run_gw_8eb6ebe95392`, and artifact id
- Customer project report smoke: `python3 scripts/customer_project_report_smoke.py`
  - project: `20260618155050`
  - report: `/api/workflows/customer-projects/20260618155050/report`
  - counts: 6 tasks, 6 runs, 6 tool calls, 1 pending approval, 1 artifact
  - delivery artifact: `art_kb_bot_delivery_20260618155050`
  - pending external-upload approval: `ap_gw_3d9c930d4a92`
- Customer project report artifact smoke: `python3 scripts/customer_project_report_artifact_smoke.py`
  - project: `20260618180442453801`
  - report artifact: `art_customer_project_report_20260618180442453801`
  - delivery artifact remains `art_kb_bot_delivery_20260618180442453801`
  - report artifact writes `runtime_events` and `audit_logs` with raw report omitted and content hash stored
  - concurrent report/report-artifact smokes passed after changing KB bot project IDs from second-level to microsecond-level timestamps
- Delivery approval manifest gate smoke:
  `python3 scripts/delivery_approval_manifest_gate_smoke.py`
  - starts an isolated local MIS server and SQLite database;
  - proves customer delivery approval returns
    `verified_plan_evidence_manifest_required` before a verified manifest
    exists;
  - records tool/evaluation/artifact evidence, creates a verified
    `plan_evidence_manifest`, then approves the delivery review;
  - confirms the customer delivery board surfaces the verified manifest and
    omits token-like material.
- Pixel Office report-archive UI build: `cd ui/start-building-app && npm run build`
- Customer report page UI build: `cd ui/start-building-app && npm run build`
- Customer project index smoke: `python3 scripts/customer_project_index_smoke.py`
  - project: `20260619050143610862`
  - status: `waiting_approval`
  - total projects: `23`
- Task owner validation smoke: `python3 scripts/task_owner_validation_smoke.py`
  - missing owner agent returns `400 owner_agent_not_found`
- Product dogfooding worker runs:
  - Hermes: `tsk_selfdev_ux_review_hermes_20260619045910757742` -> `run_gw_eb4df4e82235`
  - OpenClaw: `tsk_selfdev_ux_review_openclaw_20260619045910757742` -> `run_gw_8160a11a2323`
- Dogfooding follow-up UI build:
  - Workspace Home direct start strip: customer project, worker readiness, delivery reports
  - Pixel Office owner guide: choose template, dispatch AI team, approve/deliver
  - verified by `cd ui/start-building-app && npm run build`

Remaining product work:

- Better task result page polish beyond the first Run Detail evidence-chain
  strip.

### 8. Productization Track

Goal:

- Preserve a clear path from local MVP to a real product.

Current v1.5 implementation:

- Product usage model exists.
- Agent Gateway CLI/API spec exists.
- Worker daemon spec exists.
- Scoped remote-token entry exists.
- Customer local deployment runbook exists.
- Local SQLite backup/verify/explicit-restore utility exists:
  - `python3 scripts/agentops_local_backup.py create`
  - `python3 scripts/agentops_local_backup.py verify`
  - `python3 scripts/agentops_local_backup.py restore --confirm-restore`
  - Backup manifests store hashes, counts and integrity status only; table rows,
    prompts, raw responses and token material are not printed.
- GitHub PR has implementation history and acceptance docs.

Acceptance evidence:

- `docs/PRODUCT_USAGE_AND_ACTOR_MODEL.md`
- `docs/AGENT_GATEWAY_CLI_SPEC.md`
- `docs/V1_5_AGENT_WORKER_LOOP_SPEC.md`
- `docs/V1_5_AGENT_WORKER_ACCEPTANCE.md`
- `docs/CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md`
- `python3 scripts/agentops_local_backup_smoke.py`
- This closure spec.

Remaining product work:

- Hosted server mode.
- Multi-workspace and user accounts.
- RBAC and workspace isolation.
- Future billing/plan model.
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
python3 scripts/agentops_pip_install_smoke.py
python3 scripts/agentops_worker_package_smoke.py
python3 scripts/agentops_doctor_smoke.py
python3 scripts/agentops_worker_status_smoke.py
python3 scripts/v1_5_product_closure_evidence_smoke.py
python3 scripts/open_source_adoption_boundary_smoke.py
python3 scripts/agentops_worker_daemon_cli_smoke.py
python3 scripts/agentops_status_smoke.py
python3 scripts/remote_agent_token_worker_smoke.py
python3 scripts/workspace_isolation_smoke.py
python3 scripts/enrollment_health_state_smoke.py
python3 scripts/redaction_policy_smoke.py
python3 scripts/enrollment_launch_steps_smoke.py
python3 scripts/remote_launch_packet_worker_smoke.py
python3 scripts/agent_gateway_scope_matrix_smoke.py
python3 scripts/agent_gateway_session_smoke.py
python3 scripts/task_claim_conflict_smoke.py
python3 scripts/worker_stuck_recovery_smoke.py
python3 scripts/worker_session_refresh_smoke.py
python3 scripts/worker_adapter_retry_smoke.py
python3 scripts/worker_prompt_profile_smoke.py
python3 scripts/customer_task_template_smoke.py
python3 scripts/agentops_workflow_template_cli_smoke.py
python3 scripts/agentops_workflow_async_job_smoke.py
python3 scripts/commander_repo_map_smoke.py
python3 scripts/commander_coding_project_template_smoke.py
python3 scripts/commander_coding_workspace_smoke.py
python3 scripts/local_coding_project_template_smoke.py
python3 scripts/commander_work_package_plan_smoke.py
python3 scripts/commander_work_package_dispatch_smoke.py
python3 scripts/operator_action_queue_ui_smoke.py
python3 scripts/customer_dispatch_desk_ui_smoke.py
python3 scripts/operator_advance_loop_smoke.py
python3 scripts/operator_loop_control_smoke.py
cd ui/start-building-app && npm run build
# Optional live/local-runtime evidence, not part of default CI because it can take several minutes:
python3 scripts/template_worker_live_dogfood.py --adapter openclaw
python3 scripts/template_worker_live_dogfood.py --adapter hermes
python3 scripts/customer_project_report_smoke.py
python3 scripts/customer_project_report_artifact_smoke.py
python3 scripts/task_detail_evidence_ui_smoke.py
```

## Current Status Summary

Implemented and verified:

- Local worker loop.
- Installable Python `agentops` CLI package through `pyproject.toml`.
- Read-only `agentops doctor` setup diagnostic for local/remote agent machines.
- Local daemon start/stop/status.
- CLI worker fleet status through `agentops worker status`.
- Remote worker fleet health is included in `agentops worker status` without token/session ID leakage.
- Read-only CLI worker preflight through `agentops worker preflight`.
- Dry-run-by-default worker service file installation through `agentops worker service-install`.
- Read-only CLI worker service diagnostics through `agentops worker service-check`.
- CLI worker daemon controls through `agentops worker start|stop|logs`.
- Live adapter daemon starts fail closed without `--confirm-run`.
- Customer-facing worker task workflow through `POST /api/workflows/customer-worker-task`.
- Async customer-facing worker task workflow through
  `POST /api/workflows/customer-worker-task/submit` plus
  `GET /api/workflows/jobs/:job_id`.
- Workflow job recovery through `GET /api/workflows/jobs/stuck`,
  `POST /api/workflows/jobs/:job_id/mark-failed`, `agentops workflow
  stuck-jobs`, and `agentops workflow job-mark-failed`.
- Local readiness through `GET /api/local/readiness` and
  `agentops local readiness`.
- Commander project board through `GET /api/commander/project-board`.
- Async integration inbox through `GET /api/commander/integration-inbox`,
  `agentops commander inbox`, and the `/workspace/agents` commander panel.
- Customer-facing worker task CLI through `agentops workflow customer-worker-task`.
- Long customer worker tasks can use `agentops workflow customer-worker-task
  --async-job` and `agentops workflow job-status --wait`, which keeps Hermes
  and OpenClaw runs observable without holding a brittle synchronous request
  open.
- Customer-facing template list/run CLI through `agentops workflow templates`
  and `agentops workflow run-template`.
- Customer-facing template worker dispatch through
  `agentops workflow run-template --adapter mock|hermes|openclaw`, with
  OpenClaw/Hermes live proof runs recorded in the ledger.
- Async customer template jobs through
  `agentops workflow run-template --async-job` and
  `agentops workflow job-status --wait`.
- Pixel Office customer dispatch panel can display recent async workflow jobs
  and link to their final task/run evidence.
- One-command scoped task create + worker execution through `agentops workflow run-task`.
- Customer/API-facing normal task creation through `POST /api/tasks`, scoped Gateway task creation through `POST /api/agent-gateway/tasks`, and CLI `agentops task create`, followed by worker pull/claim/writeback.
- Scoped Gateway task creation requires `tasks:create` and binds remote tokens to their own `agent_id`/`workspace_id`.
- Pixel Office customer dispatch can run a task through mock/Hermes/OpenClaw worker adapters and show evidence counts.
- Mock/Hermes/OpenClaw adapter loop.
- Adapter retry handling with non-retry safety gate behavior.
- UI one-shot worker dispatch.
- UI daemon controls.
- UI worker fleet telemetry.
- Live Approvals Inbox.
- Live Tool Call Ledger.
- Scoped token enrollment.
- Agent Gateway safe status check via `GET /api/agent-gateway/status` and `agentops status`.
- Agent Gateway status surfaced in `/workspace/agents`.
- Operator readiness strip surfaced in `/workspace/agents`.
- Remote enrollment launch packet surfaced in `/workspace/agents` after token creation/rotation.
- Remote enrollment launch packet worker path now uses the installable `agentops-worker` command, read-only adapter preflight, dry-run-by-default service file installation, read-only service diagnostics, preview-first service control, and short-lived sessions before task processing; repo-local `scripts/agent_worker.py` is shown only as a fallback. Long-running worker setup can render, write, check, and preview load/unload/restart for launchd/systemd templates, while actual service mutation remains explicit operator-confirmed BYOC behavior through `--confirm-control`.
- Loop-mode workers can refresh short-lived sessions before expiry while continuing to process tasks.
- Remote enrollment UI.
- Token revocation.
- Token rotation.
- Enrollment heartbeat states: `never_seen`, `fresh`, `stale`, and `revoked`.
- Short-lived session list/revoke API, CLI, and `/workspace/agents` panel.
- Endpoint-level scope enforcement.
- Scoped RBAC matrix smoke for observer-vs-worker permissions.
- Multi-worker claim conflict guard.
- Stuck worker task detection and release controls.
- Short-lived Agent Gateway sessions, including metadata listing, direct revocation, and parent-token revoke cascade.
- Minimal workspace isolation for token-auth Agent Gateway pull/claim/run/write paths.
- Remote-token worker end-to-end smoke.
- Remote launch-packet worker end-to-end smoke.
- Customer-style knowledge-base bot project smoke with delivery artifact.
- Customer task template API/UI path with KB bot template smoke.
- Customer project report export from MIS ledger evidence.
- Local readiness knowledge proof: `python3 scripts/local_readiness_smoke.py`
  verifies knowledge document/chunk/FTS counters and the knowledge CLI next
  action; `python3 scripts/knowledge_retrieval_quality_smoke.py` verifies the
  heading-aware FTS5 retrieval baseline.

Not yet product-complete:

- Published global CLI distribution.
- Future full RBAC and hosted multi-tenant isolation.
- Production worker fleet manager.
- Future hosted SaaS/commercial deployment layer.
