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
- CLI: `agentops knowledge search`, `agentops knowledge index`, `agentops agent-plan create/list/get/verify`, `agentops plan-evidence create/list/get/verify`

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
- DELIVERY GATE: customer delivery approvals fail closed until the linked run has a verified `plan_evidence_manifest`; the customer delivery board surfaces the manifest gate status for human review.

## Cleanliness Contract

- Source doctrine lives in reviewed Markdown.
- Runtime state lives in SQLite/runtime storage.
- Generated plans, FTS rows, temporary databases, raw run logs, and cache files must not be committed.
- Knowledge indexing stores redacted text; raw secrets, raw prompts, and raw responses are not valid knowledge documents.

## Next Guardrail

Hermes/OpenClaw loop review flagged the next bypass risk: an agent can create and verify a plan, then execute a different path. The implemented guardrail is `plan_evidence_manifests`: create one with `agentops plan-evidence create --plan-id <id> --run-id <id> --mismatch-policy block` after the run writes tool, evaluation, artifact, and audit evidence. Creation can persist `verified` / `blocked` status; `agentops plan-evidence verify` re-computes the ledger checks without mutating the manifest or writing audit rows. A manifest verifies only when the plan passes, plan/run/task/agent bindings match, tool calls completed, evaluations passed, artifacts are bound, and audit evidence exists. Missing or mismatched evidence is blocked by default. Customer delivery approvals now consume this gate: approving a customer delivery without a verified manifest returns `verified_plan_evidence_manifest_required`.
