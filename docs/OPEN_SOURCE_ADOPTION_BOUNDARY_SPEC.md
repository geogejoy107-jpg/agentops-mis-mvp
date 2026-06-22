# Open Source Adoption Boundary Spec

## Purpose

AgentOps MIS may borrow open-source tools, protocols, research patterns, UI
references, and local runtimes. It must not delegate the MIS authority model to
those projects.

The operating rule:

> Tooling, protocols, retrieval, CI, and security scanning can borrow heavily
> from open source. Anything involving the MIS authority ledger, permissions,
> approvals, state transitions, evidence chain, or business objects must remain
> first-party AgentOps MIS code.

## Product Boundary

AgentOps MIS is the control plane and ledger. External runtimes and frameworks
can execute or observe work, but they are not the source of truth for:

- workspaces
- agents
- tasks
- runs
- tool calls
- approvals
- prepared actions
- artifacts
- evaluations
- memories
- audit logs
- delivery reports

If an external tool produces a trace, transcript, plan, vector result, status
event, or workflow checkpoint, MIS may ingest a redacted summary, stable ID,
hash, and provenance metadata. The raw external state does not become canonical
until it is represented in MIS tables with scope, approval, evaluation, and
audit evidence.

## Directly Adoptable Tools

These can be used as implementation tools because they do not own the MIS
business state:

| Area | Adoptable tools | MIS boundary |
| --- | --- | --- |
| Storage reliability | SQLite WAL, busy timeout, JSON1 | MIS still owns schema, migrations, transaction discipline and evidence rows. |
| Search | SQLite FTS5 | MIS owns document metadata, workspace/access policy, provenance and authority rules. |
| CI | GitHub Actions | CI proves checks; it does not define product truth. |
| Secret scan | Gitleaks or equivalent | Scanners are release gates; redaction and no-raw-storage rules stay in MIS. |
| SBOM | Syft or equivalent | SBOM supports release evidence; license/provenance decisions stay in MIS docs. |
| Git isolation | Git worktree | Worktrees can isolate branches; MIS owns work packages, scope deviation and merge approvals. |
| API docs | OpenAPI later | The API contract reflects MIS authority; it does not replace it. |
| Agent interface | MCP SDK later | MCP can expose tools/resources; Agent Gateway scopes remain the authority boundary. |

## Reference-Only Methods

These projects and methods can shape design, but should not become the runtime
source of truth:

| Reference | Useful idea | Do not import as |
| --- | --- | --- |
| GitHub Spec Kit | spec / plan / tasks workflow | The canonical Agent Plan engine. |
| OpenAI AGENTS.md / Skills | repo rules and reusable task methods | The MIS task ledger or approval system. |
| Aider Repo Map | compact codebase localization | Workspace/agent memory authority. |
| LangGraph interrupt/checkpoint | durable pause and resume pattern | The approval ledger or delivery gate. |
| OPA / Cedar | policy model vocabulary | v1.5 policy runtime dependency. |
| SWE-agent / Agentless | bounded software repair workflow | The MIS product UI or task authority. |
| Mem0 / Zep / Letta | memory governance concepts | Automatic memory authority. |
| CrewAI / LangGraph / JiuwenSwarm | multi-agent orchestration ideas | Workspace, run, approval or audit authority. |
| Star-Office / pixel-office references | visual operating-map inspiration | Product assets, commercial art, or canonical state. |

## First-Party MIS Modules

These must be implemented and tested inside AgentOps MIS:

- Agent Plan to Run binding:
  - `agent_plan_id` on runs
  - immutable `plan_hash`
  - verification hash/timestamp
  - approval role separation
  - plan/run/task/agent/workspace matching
  - plan-evidence manifest verification
- Workspace, agent and scope authorization:
  - token/session scope
  - exact collaborator membership
  - task ownership
  - artifact visibility
  - review queue visibility
  - knowledge visibility
- Approval Wall:
  - `prepared_actions`
  - normalized args
  - `action_hash`
  - policy version
  - checkpoint
  - idempotency key
  - one-time consume/resume
  - provider side-effect evidence
- Runtime governance:
  - runtime capability manifests
  - trust status
  - live-run confirmation gates
  - runtime-event ingestion
  - opaque-runtime commercial restrictions
  - secret boundary evidence
- Customer delivery:
  - internal evidence vs customer-facing report split
  - report artifact hashes
  - delivery approval gates
  - no raw prompt/response/customer body leakage
- Review and command center:
  - human review queue
  - Commander inbox
  - delivery board
  - operator action-plan
  - action receipts and verification receipts
- Memory governance:
  - candidate/approved/rejected lifecycle
  - non-authoritative candidate memory
  - failure-case promotion only after review
- Local coding/project template:
  - work package
  - branch/worktree workspace
  - repo localization artifact
  - patch artifact
  - test result artifact
  - independent verifier
  - merge approval
  - scope deviation check

## v1.5 Implementation Priority

The v1.5 goal remains product closure, not broad framework integration. The
current order is:

1. Fix execution and permission correctness.
2. Keep Agent Gateway, Worker, Approval Wall, Knowledge, Runtime and Audit
   boundaries verifiable.
3. Establish deterministic CI and release evidence.
4. Form a clean local RC.
5. Only then expand adapter/framework integrations.

The preferred split is:

```text
30% direct open-source tools
40% open-source methods adapted into first-party code
30% fully native MIS authority logic
```

## Agent Instructions

When using an open-source reference, the agent must state:

```text
Reference:
Borrowed idea:
First-party MIS module touched:
Authority boundary preserved:
Verification:
```

Do not add a framework dependency unless it improves a tool/protocol/search/CI
layer and does not move authority out of MIS. If a dependency would own
workspace, task, approval, run, memory, audit, delivery or identity state, reject
it or wrap it as a runtime/connector adapter.
