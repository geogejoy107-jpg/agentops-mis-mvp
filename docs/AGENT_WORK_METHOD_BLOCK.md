# Agent Work Method Block

The Agent Work Method Block is a MIS module, not just documentation. It gives every agent the same execution contract:

READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD

## Implemented Surfaces

- Markdown specs: `PROJECT_SPEC.md`, `AGENT_WORKFLOW.md`, `BASE_INDEX.md`, `secret_registry.md`
- Shared knowledge: `knowledge/shared/`
- Base notes: `knowledge/bases/`
- Runbooks: `knowledge/runbooks/`
- SQLite ledger: `agent_plans`, `plan_evidence_manifests`, `knowledge_documents`, `knowledge_fts`
- API: `GET /api/knowledge/search`, `POST /api/knowledge/index`
- Agent Gateway API: `GET /api/agent-gateway/knowledge/search`, `POST /api/agent-gateway/agent-plans`, `GET /api/agent-gateway/agent-plans/:id/verify`, `POST /api/agent-gateway/plan-evidence-manifests`, `GET /api/agent-gateway/plan-evidence-manifests/:id/verify`
- Operator launch packet: `GET /api/operator/loop-launch-packet` and `agentops operator loop-launch-packet`
- Operator loop self-check: `GET /api/operator/loop-self-check` and `agentops operator loop-self-check`
- Operator runtime doctor: `GET /api/operator/runtime-doctor` and `agentops operator runtime-doctor`
- Operator loop control: `GET /api/operator/loop-control` and `agentops operator loop-control`
- Bounded runner: `agentops operator advance-loop`
- Bounded runner policy: `agentops operator advance-loop-policy`
- Agent loop handoff: `agentops operator agent-loop-handoff`
- CLI: `agentops knowledge search`, `agentops knowledge index`, `agentops commander repo-map`, `agentops agent-plan create/list/get/verify`, `agentops plan-evidence create/list/get/verify`, `agentops operator runtime-doctor`, `agentops operator live-acceptance`, `agentops operator loop-control`, `agentops operator loop-launch-packet`, `agentops operator agent-loop-handoff`, `agentops operator loop-self-check`, `agentops operator advance-loop`, `agentops operator advance-loop-policy`

## Why This Shape

Open-source agent runtimes increasingly have memory, human-in-the-loop, tool use, and observability features, but they usually model execution from inside one runtime. MIS needs the cross-runtime management layer: task, plan, approval, memory review, evidence, audit, and base comparison.

## Research Signals

- LangGraph separates short-term checkpoint persistence from long-term stores, which supports resume, failure recovery, and human-in-the-loop workflows.
- CrewAI and AutoGen show that role/task orchestration and human feedback are runtime features, but cross-agent governance still needs a separate ledger.
- OpenHands emphasizes local or ephemeral workspaces for software agents, reinforcing the need to record runtime and workspace boundaries.
- Langfuse, AgentOps, Braintrust, and OpenTelemetry GenAI work point toward tracing tool calls, retrieval, memory operations, cost, latency, and evaluations as core evidence.
- Mem0, Zep/Graphiti, and Letta show that memory must be explicitly managed; MIS keeps memory candidates reviewable before they become authority.
- Agent Control and GitHub's agent control plane show that centralized policy and audit are becoming first-class enterprise expectations.

## First-Version Decision

Use Markdown plus SQLite first:

1. Human-readable Markdown remains the source for project rules, base notes, runbooks, and operating doctrine.
2. SQLite records authoritative ledger objects.
3. SQLite FTS5 indexes Markdown for retrieval.
4. Embeddings and vector databases are deferred until document volume and recall failures justify them.

## Acceptance

- A new agent can discover specs and base notes through `agentops knowledge search`.
- A new agent can submit an `agent_plan` before execution.
- A new agent can request a read-only launch packet that packages the method phases, plan draft, knowledge retrieval metadata, repo-map localization, intake comparison, verification, and record commands without mutating ledgers.
- That launch packet carries a machine-readable evaluation contract and audit contract, so Hermes, OpenClaw, Codex, or a remote agent can see the minimum exit criteria, required ledgers, bounded-runner policy, receipt expectations, and raw-content omission rules before advancing the loop.
- A lightweight runtime doctor tells Hermes, OpenClaw, Codex, and remote Agents whether the local MIS API, adapter readiness, confirm-run wall, prepared-action wall, worker fleet, handoff evidence counts, launch packet, and redaction boundary look usable before a live runtime is asked to execute; deeper operator health and handoff checks are returned as copyable follow-up commands.
- A local operator can confirm one bounded loop advance that executes a safe allowlisted `agentops` action, verifies it, and records the receipt without approving memory or running live workflows.
- The plan records specs, memories, bases, target files, risk, approvals, steps, verification, and rollback.
- Search and plans are available through Agent Gateway, not only browser UI.
- No secret values are written to the repo or ledger.

## Evidence Contract

- READ: referenced specs are recorded in `agent_plans.referenced_specs_json`.
- PLAN: the submitted `agent_plans` row is the pre-execution contract.
- PLAN VERIFY: `agentops agent-plan verify` checks the plan before execution.
- RETRIEVE: knowledge search results and memory IDs should be referenced in the plan or run evidence.
- COMPARE: referenced bases and risk/approval decisions are recorded in the plan.
- EXECUTE: tool calls and runtime events record the execution path.
- VERIFY: evaluations record rule, smoke, human, or mock-LLM gates.
- RECORD: artifacts, audit logs, and memory candidates close the loop.
- EVIDENCE BINDING: `plan_evidence_manifests` links a verified `agent_plan` to the exact run, tool calls, evaluations, artifacts, and audit evidence before a delivery can be treated as closed.
- START CHECK: `GET /api/operator/start-check` and `agentops operator start-check --adapter hermes|openclaw|mock` are the first pre-task reads for Hermes/OpenClaw/Codex. They compose local readiness, worker readiness, runtime doctor, live product-readiness, compact launch brief, bounded `loop_driver_entry`, `agent_loop_packet`, `local_run_path`, service-control preview, Agent Plan boundary, and next commands into one copy-only packet. The loop-driver entry includes preview/confirm-loop/review commands plus a compact RECORD review snapshot, with raw item summaries/content omitted. `agent_loop_packet` gives API and CLI callers the same READ/PLAN/RETRIEVE/COMPARE/PREFLIGHT/EXECUTE/VERIFY/RECORD phase map without executing shell or live work, plus `phase_commands` and `method_gates` so callers can programmatically enforce `plan_agent_plan`, `retrieve_knowledge`, `compare_base_reference`, `preflight_adapter`, `execute_bounded_loop`, `verify_loop`, and `record_memory_candidate` before treating local loop work as ready. They may return `attention` when live binaries, credentials, review pressure, or ledger proof are missing, but they still stay useful because they name the next safe command without starting runtimes, executing server shell, mutating ledgers, or exposing raw prompts/responses/tokens.
- LOCAL LOOP ADMISSION: the same start-check response also returns `local_loop_admission_packet`, a compact read-only admission packet for local or remote agents. It binds the Method Block gate ids, phase commands, worker-start command, service-control preview, customer-worker dispatch template, ledger verification, and first safe commands into one copy-only payload. It never executes server shell or live work; Hermes/OpenClaw commands still carry explicit confirmation boundaries and read back ledger evidence before delivery is treated as ready.
- CUSTOMER-WORKER INTAKE: live Hermes/OpenClaw customer-worker workflow responses also echo the same `local_loop_admission_packet` on confirm-required, adapter/trust/prepared-action blocks, and final readback. This makes the real dispatch entry point carry the Method Block contract, not only the operator UI.
- ENFORCED TASK PULL: `agentops task pull --enforce-intake` and worker daemon intake now add a `local_loop_admission_packet` gate for Hermes/OpenClaw-owned tasks. Pull is blocked if the Method Block admission commands or no-server-shell / `--confirm-run` proofs are missing.
- WORKER DAEMON START/RESTART: `POST /api/workers/local/start` and `/restart` include `local_loop_admission_summary` when intake blocks a Hermes/OpenClaw daemon. The summary counts live adapter tasks checked, passed/missing admission packets, required Method Block gates, next safe commands, and safety proofs (`read_only`, no ledger mutation, no live execution, no server shell, token omitted), so local OpenClaw/Hermes can see why a worker was stopped before doing live work.
- REMOTE LAUNCH PACKET: Agent Gateway enrollment `next_steps` now includes `start_check`, `loop_launch_brief`, and `method_gate_contract`. A remote machine that receives a one-time token should run `agentops operator start-check` before worker preflight so it sees the same Method Block gates as the local operator console. The launch packet still uses a token placeholder in commands and marks `token_omitted:true`.
- AGENT LOOP HANDOFF: `agentops operator agent-loop-handoff` is the compact multi-consumer intake read for Hermes/OpenClaw/Codex. It aggregates local current-code readiness, live Hermes/OpenClaw ledger proof, per-adapter `start-check`, compact `loop-launch-packet --brief`, Method Block `phase_commands`, `method_gate_ids`, and Codex supervisor commands into one JSON matrix. It is read-only, never executes server shell or live runtimes, never mutates ledgers, and marks raw prompt/response/content/token omission. A consumer can be `attention` while review or memory pressure exists, but `ready_for_handoff` remains the structural proof that the agent can continue by copying the named commands instead of guessing the loop protocol.
- RUNTIME DOCTOR: `agentops operator runtime-doctor` is the first lightweight local loop diagnostic inside start-check or direct operator inspection for Hermes/OpenClaw/Codex. It samples worker readiness, worker fleet state, and ledger evidence counts into gates for local MIS API reachability, Hermes/OpenClaw runtime availability, `--confirm-run`, prepared actions for external writes, remote worker freshness, launch packet availability, handoff/evidence-chain status, Codex supervision, and token/raw-content redaction. It returns copyable commands only, including the deeper `operator health` and `operator handoff` checks; it never starts runtimes, executes tasks, writes ledgers/connectors, or exposes tokens.
- WORKER READINESS REMEDIATION: `agentops worker readiness` is the authority for Hermes/OpenClaw local setup status and copy-only remediation commands. Agents must read per-adapter `remediation.primary_next_action`, missing checks, and command phases before asking for live dispatch; read-only inspect/preflight/doctor phases may be copied directly, while worker starts and live task templates still require `--confirm-run` and any prepared-action approval.
- LIVE ACCEPTANCE: `agentops operator live-acceptance` is the read-only freshness check for real local Hermes/OpenClaw acceptance runs. It derives `fresh/stale/missing/latest_failed/latest_incomplete` from run/tool/evaluation/runtime/audit/artifact/memory/approval/plan-evidence ledger rows, surfaces `active_attempt` for in-flight `agt_customer_worker_*` worker runs before delivery artifacts exist, and returns explicit manual `--confirm-live` commands without calling runtimes or mutating ledgers.
- LAUNCH PACKET: `agentops operator loop-launch-packet` produces the next agent's machine-readable READ/PLAN/RETRIEVE/COMPARE/EXECUTE/VERIFY/RECORD packet from intake, safe knowledge metadata, repo-map localization, operator control state, and an agent-plan draft; it omits snippets and raw content to avoid leaking secret-like strings. Default control uses lightweight `operator loop-control`, while `--handoff-mode full` / `--full-handoff` opts into deeper `operator handoff` diagnostics. The RETRIEVE phase includes `agentops commander repo-map` plus a sanitized `sources.repo_map` block with paths, symbols, hashes, provenance, ranking proof, and no raw file bodies, so the draft's proposed files are grounded before execution. The packet also includes `evaluation_contract`, `audit_contract`, and `execution_chain` blocks covering Agent Plan verification, intake, targeted checks, bounded advance preview/confirm, verified plan-evidence manifests, loop-audit, memory candidate review, Action Queue receipts, receipt evaluations, tamper-chain expectations, bounded runner policy, denied live/approval/worker actions, and required ledgers including `memories` and `memory_review`. Each execution-chain step carries current `step_status`, `blocked_reason` or `ready_reason`, `next_safe_command`, and `receipt_state`; `control_summary` then selects the current recommended step, command, verify command, receipt command, control mode, human/receipt requirement, and copy-only proof so Hermes/OpenClaw/Codex can decide whether to read, copy, verify, or wait for an explicit receipt without guessing from prose. In `--brief` mode, the CLI also folds in a compact `local_run_path` from `agentops local readiness`, including service-control preview, so live local agents see boot/readiness/worker/service/dispatch/ledger commands without receiving raw payloads or any server-shell capability.
- LOOP CONTROL: `agentops operator loop-control` is the lightweight next-step read model for real local ledgers. It uses bounded counts, recent receipt state, optional `loop://...` readback, and the shared bounded-runner policy without calling full `handoff`, `action-plan`, or `evidence-report`. Unscoped calls select `runtime-doctor` as the first local readiness check, then advance to `handoff`, `action-plan`, and review queue as each step receives a verified receipt; scoped loop calls select the next safe RECORD/VERIFY step such as review queue, `memory propose --type loop_record`, or blocked evidence inspection. Use `agentops operator advance-loop --fast-control` when Hermes/OpenClaw/Codex need one bounded step plus receipt/control-readback proof without waiting on the heavier handoff graph.
- LOOP DRIVER: `agentops operator loop-driver --adapter hermes|openclaw` is the compact local multi-step driver for Hermes/OpenClaw/Codex. Without `--confirm-loop` it is read-only and returns the start-check `acceptance_gate`, a machine-readable `agent_loop_packet` for READ/PLAN/RETRIEVE/COMPARE/PREFLIGHT/EXECUTE/VERIFY/RECORD, adapter readiness/preflight evidence, the compact launch brief, a compact RECORD review snapshot, and policy. `GET /api/operator/start-check` also returns the same `agent_loop_packet`, and `/workspace/agents` reads Hermes/OpenClaw start-check packets into a supervised loop-driver panel with current phase, confirm readiness, copyable phase commands, and server-shell proof. With `--confirm-loop` it reads the start-check `acceptance_packet` before execution and before each step, advances only when `can_confirm_bounded_loop=true` and `server_executes_shell=false`, delegates execution to `advance-loop --fast-control --confirm-advance`, records receipts/control-readback through the existing bounded runner, caps execution at five steps, re-reads the review snapshot after each step, returns final/initial `agent_loop_packet` readbacks, and still refuses live/workflow/approval/external-write commands.
- LOOP SELF-CHECK: `agentops operator loop-self-check` is the pre-advance read-only check for Hermes/OpenClaw/Codex. It aggregates bounded policy decisions, handoff loop health, receipt coverage, receipt evaluations, audit ledger proof, `control_summary`/`loop_control`, and server-shell safety without executing commands or mutating ledgers.
- LOOP HEALTH CONTROL: `agentops operator handoff` now mirrors the copy-only control view into `loop_health.gates.loop_control`, and `agentops operator health` exposes the same `control_summary`/`loop_control` as a health component. The loop-audit RECORD evidence includes handoff, self-check, and advance preview commands plus the `advance-loop --confirm-advance` control-readback source, so post-receipt recommendation changes are auditable outside the CLI output.
- BOUNDED ADVANCE: `agentops operator advance-loop --confirm-advance` consumes the handoff action package, runs at most one allowlisted local command, executes the verify command, records a `verified` or `failed` Action Queue receipt, then returns and persists `control_readback` with pre-action control plus post-receipt handoff/self-check control summaries fetched with `refresh_cache=true`. The persisted readback is attached to the Action Queue receipt ledger so the next recommendation change remains auditable after the CLI exits. It may run read-only evidence remediation previews after the evidence-report work order is receipted, but refuses approval decisions, memory approval, worker lifecycle, workflow dispatch, live/confirm flags, close-gap, remediation `--confirm-create`, and external-write paths.
- BOUNDED POLICY: `agentops operator advance-loop-policy` exposes the shared local-runner policy id/version, allowlists, denylists, and sample decisions; CLI execution, backend handoff, UI display, and smoke tests must reference this same policy contract.
- DELIVERY GATE: customer delivery approvals fail closed until the linked run has a verified `plan_evidence_manifest`; the customer delivery board surfaces the manifest gate status for human review.
- AUTOMATIC WORKER PATH: normal AgentOps worker pulls create an `agent_plan`, write tool/evaluation/artifact/audit evidence, and persist a verified or blocked `plan_evidence_manifest` before returning the worker result.
- CUSTOMER WORKER PATH: `POST /api/workflows/customer-worker-task` now reuses a verified worker manifest or creates one before generating the customer delivery approval; if verification fails, no delivery approval is created.

## Cleanliness Contract

- Source doctrine lives in reviewed Markdown.
- Runtime state lives in SQLite/runtime storage.
- Generated plans, FTS rows, temporary databases, raw run logs, and cache files must not be committed.
- Knowledge indexing stores redacted text; raw secrets, raw prompts, and raw responses are not valid knowledge documents.

## Next Guardrail

Hermes/OpenClaw loop review flagged the next bypass risk: an agent can create and verify a plan, then execute a different path. The implemented guardrail is `plan_evidence_manifests`: create one with `agentops plan-evidence create --plan-id <id> --run-id <id> --mismatch-policy block` after the run writes tool, evaluation, artifact, and audit evidence. Creation can persist `verified` / `blocked` status; `agentops plan-evidence verify` re-computes the ledger checks without mutating the manifest or writing audit rows. A manifest verifies only when the plan passes, plan/run/task/agent bindings match, tool calls completed, evaluations passed, artifacts are bound, and audit evidence exists. Missing or mismatched evidence is blocked by default. Customer delivery approvals now consume this gate: approving a customer delivery without a verified manifest returns `verified_plan_evidence_manifest_required`, and the customer-worker workflow does not generate a delivery approval until this gate passes.
