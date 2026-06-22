# AgentOps MIS Parallel Product Delivery Branch Plan

## Purpose

This plan lets multiple Codex threads work in parallel without rewriting each
other's files. The base branch is `codex/agent-gateway-kb-demo` unless the
operator explicitly chooses a newer integration branch.

This thread's integration/commander responsibilities are defined in
`docs/INTEGRATION_COMMANDER_RUNBOOK.md`.

The product contract stays fixed:

- Humans use the browser workspace/admin console to create tasks, supervise
  status, approve risk, and review delivery.
- Agents use Agent Gateway CLI/API/MCP to execute work.
- Hermes/OpenClaw live execution must go through readiness, trust, and
  `confirm_run` gates.
- No branch may commit credentials, local DBs, `.env`, generated service files,
  raw prompts, raw model responses, private transcripts, `dist`, or
  `node_modules`.

## Recommended Branches

| Branch | Owner Focus | Primary Files | Avoid Editing |
| --- | --- | --- | --- |
| `codex/local-first-ops` | Open-source local-first usable product profile | `docs/REMOTE_WORKER_OPERATIONS_RUNBOOK.md`, `docs/V1_5_EIGHT_PRODUCT_CLOSURE_SPEC.md`, `README.md`, `scripts/*smoke.py`, `ui/start-building-app/src/app/components/pages/AIEmployees.tsx`, `ui/start-building-app/src/app/components/pages/MemoryLibrary.tsx` | Hosted/SaaS, billing, Notion/Dify live sync |
| `codex/remote-worker-deploy` | Remote agent daemon deployment and server handoff | `docs/REMOTE_WORKER_OPERATIONS_RUNBOOK.md`, `docs/AGENT_GATEWAY_CLI_SPEC.md`, `scripts/remote_*`, `scripts/*service*`, `agentops_mis_cli/worker.py` | Pixel Office UI pages unless needed for status display |
| `codex/customer-task-flow` | Customer task creation, async job status, delivery review | `ui/start-building-app/src/app/components/pixel/CustomerDispatchPanel.tsx`, `ui/start-building-app/src/app/components/pages/CustomerProjectReport.tsx`, `ui/start-building-app/src/app/data/liveApi.ts`, workflow smoke scripts | Enrollment/session internals |
| `codex/rbac-workspace-hardening` | Workspace isolation, token scopes, approval policy | `server.py` Agent Gateway auth helpers, `docs/AGENT_GATEWAY_CLI_SPEC.md`, scope/security smoke scripts | Pixel map visual design |
| `codex/worker-fleet-console` | Worker fleet UI, readiness, health, stuck recovery | `/workspace/agents` UI files, `GET /api/workers/status`, `GET /api/workers/adapter-readiness`, worker status smoke scripts | Customer report content model |
| `codex/product-docs-demo` | Demo script, classroom recording, product packaging docs | `docs/DEMO_*`, `docs/V1_5_*`, `README.md`, runbooks | Runtime execution code except doc fixes |

If a thread must touch a file outside its primary files, it should write the
reason in its final summary and keep the edit small.

## Merge Order

1. `codex/local-first-ops`
2. `codex/rbac-workspace-hardening`
3. `codex/remote-worker-deploy`
4. `codex/worker-fleet-console`
5. `codex/customer-task-flow`
6. `codex/product-docs-demo`

The local-first branch defines the practical open-source baseline and should
merge first. RBAC and remote worker changes affect the base contract, so merge
them before UI polish and demo documentation. Product docs should merge last so
screenshots and scripts reflect the final behavior.

## Shared Verification Baseline

Every branch should run the checks that match its blast radius.

Core backend or CLI changes:

```bash
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_runtime/*.py scripts/*.py
git diff --check
python3 scripts/worker_adapter_readiness_smoke.py
python3 scripts/agentops_worker_status_smoke.py
python3 scripts/agentops_doctor_smoke.py
```

Agent Gateway, enrollment, token, or workspace changes:

```bash
python3 scripts/agent_gateway_scope_matrix_smoke.py
python3 scripts/agent_gateway_session_smoke.py
python3 scripts/workspace_isolation_smoke.py
python3 scripts/enrollment_approval_workflow_smoke.py
python3 scripts/remote_agent_token_worker_smoke.py
```

Worker loop or adapter changes:

```bash
python3 scripts/worker_daemon_resilience_smoke.py
python3 scripts/worker_adapter_retry_smoke.py
python3 scripts/customer_worker_adapter_not_ready_smoke.py
python3 scripts/customer_worker_async_adapter_not_ready_smoke.py
python3 scripts/template_worker_async_adapter_not_ready_smoke.py
```

Customer workflow changes:

```bash
python3 scripts/agentops_customer_worker_cli_smoke.py
python3 scripts/customer_worker_task_workflow_smoke.py
python3 scripts/agentops_workflow_async_job_smoke.py
python3 scripts/customer_project_report_smoke.py
python3 scripts/customer_project_report_artifact_smoke.py
```

Frontend changes:

```bash
cd ui/start-building-app
npm install
npm run build
```

Live Hermes/OpenClaw dogfood is optional for most branches and should only run
on a machine where the operator confirms local runtimes are intended to execute:

```bash
python3 scripts/customer_worker_live_dogfood.py \
  --adapter openclaw \
  --adapter hermes \
  --request-timeout 720 \
  --hermes-timeout 600
```

## Handoff Prompts

### Local-First Ops

```text
You are working on geogejoy107-jpg/agentops-mis-mvp branch codex/local-first-ops.
Goal: make AgentOps MIS useful as an open-source local-first app that the founder can use today for real project management, local OpenClaw/Hermes worker execution, memory/knowledge accumulation, approvals, run ledger, and management UI.
Start from docs/PARALLEL_PRODUCT_DELIVERY_BRANCH_PLAN.md, docs/V1_5_EIGHT_PRODUCT_CLOSURE_SPEC.md, and docs/REMOTE_WORKER_OPERATIONS_RUNBOOK.md.
Keep the product local-first: no SaaS billing, hosted multi-tenant work, Notion live sync, or Dify live sync.
Preserve the core contract: humans supervise in the browser; agents execute through Agent Gateway CLI/API/MCP; Hermes/OpenClaw live execution requires readiness/trust/confirm_run.
Focus on clarifying the local workflow, readiness checks, memory review, worker management, and demo runbook. Make small product improvements only if they make the local system easier to use.
Verify with py_compile, git diff --check, worker_adapter_readiness_smoke.py, agentops_worker_status_smoke.py, customer_worker_task_workflow_smoke.py, and npm run build if UI changes.
Do not commit credentials, local DB, .env, node_modules, dist, runtime logs, generated service files, raw prompts, raw responses, private messages, or full transcripts.
```

### Remote Worker Deploy

```text
You are working on geogejoy107-jpg/agentops-mis-mvp branch codex/remote-worker-deploy.
Goal: make remote Agent Worker deployment customer-handoff ready without changing the browser UI.
Start from docs/PARALLEL_PRODUCT_DELIVERY_BRANCH_PLAN.md and docs/REMOTE_WORKER_OPERATIONS_RUNBOOK.md.
Improve server/remote worker launch packet docs or scripts only where needed.
Verify with py_compile, git diff --check, remote_agent_token_worker_smoke.py, remote_launch_packet_worker_smoke.py, worker_remote_fleet_status_smoke.py.
Do not commit credentials, local DB, generated service files, node_modules, dist, or runtime logs.
```

### Customer Task Flow

```text
You are working on geogejoy107-jpg/agentops-mis-mvp branch codex/customer-task-flow.
Goal: make the customer-facing task -> AI worker -> async status -> delivery report path clearer and more usable.
Agents must still execute through Agent Gateway CLI/API; browser UI is only for customer/admin dispatch, supervision, approval, and review.
Focus on PixelOffice, customer project report UI, liveApi, and workflow smoke tests.
Verify with npm run build plus customer workflow smoke scripts.
Do not rewrite Agent Gateway auth or worker internals unless a bug blocks the task flow.
```

### RBAC / Workspace Hardening

```text
You are working on geogejoy107-jpg/agentops-mis-mvp branch codex/rbac-workspace-hardening.
Goal: harden workspace isolation, scoped token enforcement, session behavior, and approval policy without UI redesign.
Focus on server.py Agent Gateway auth helpers, AGENT_GATEWAY_CLI_SPEC.md, and scope/workspace smoke scripts.
Verify with agent_gateway_scope_matrix_smoke.py, agent_gateway_session_smoke.py, workspace_isolation_smoke.py, enrollment_approval_workflow_smoke.py.
Keep raw tokens omitted from responses, logs, docs, and tests.
```

### Worker Fleet Console

```text
You are working on geogejoy107-jpg/agentops-mis-mvp branch codex/worker-fleet-console.
Goal: improve the operator's worker fleet view: readiness, remote heartbeat/session health, daemon state, stuck recovery, and recommended actions.
Do not change the agent execution contract; agents use CLI/API, browser supervises.
Focus on /workspace/agents UI, worker status/readiness APIs only if the UI lacks required fields, and worker status smoke tests.
Verify with npm run build, worker_adapter_readiness_smoke.py, agentops_worker_status_smoke.py, worker_remote_fleet_status_smoke.py.
```

### Product Docs Demo

```text
You are working on geogejoy107-jpg/agentops-mis-mvp branch codex/product-docs-demo.
Goal: make the classroom/demo narrative match the real product: customer dispatches work, OpenClaw/Hermes agents execute through CLI/API, MIS records run/tool/eval/audit/artifact/memory/approval evidence.
Focus on README, demo scripts, v1.5 acceptance docs, and runbooks.
Do not edit runtime code unless documentation verification exposes a concrete bug.
Verify docs mention the latest live runs run_gw_7ede8c8cc5c9 and run_gw_1e864c5f6b18 only as evidence, not as required future test fixtures.
```

## Conflict Rules

- Do not reformat unrelated files.
- Do not rename API endpoints on a side branch.
- Do not move shared UI components unless the branch owns all affected pages.
- If two branches need `server.py`, prefer adding narrow helper functions and
  smoke tests rather than broad refactors.
- If a branch changes database schema, it must include a repeatable smoke test
  that starts from the existing local SQLite migration path.
- If a branch changes CLI output shape, it must update both CLI docs and at
  least one smoke test that checks token omission.

## Integration Checklist

Before merging a branch back into the integration branch:

- `git status --short` is clean except intended changes before commit.
- No secret-like strings are added: raw `agtok_`, `agtsess_`, `sk-`, `ntn_`,
  `Authorization: Bearer`, or private transcript text.
- Branch-specific smoke tests pass.
- `git diff --check` passes.
- The final summary lists touched files, verification commands, and remaining
  product gaps.
