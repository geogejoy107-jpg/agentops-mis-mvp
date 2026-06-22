# Open Source Base Index v1.1 — Async Parallel Research Plan

> Repository: `geogejoy107-jpg/agentops-mis-mvp`  
> Branch: `research-open-source-base-index-v1-1`  
> Branch base: `codex/agent-gateway-kb-demo`  
> Frozen starting commit: `169924acdb6a301c1c870f48449aedc76bf6fb5a`  
> Started: 2026-06-22  
> Work type: documentation, evidence collection, code-to-base mapping, and integration proposals only

## Preflight

```text
Repository: geogejoy107-jpg/agentops-mis-mvp
Branch: research-open-source-base-index-v1-1
Commit: 169924acdb6a301c1c870f48449aedc76bf6fb5a (branch starting point)
Current milestone: current-head verification -> correctness hardening -> CI/security/concurrency/performance gates -> v1.5 RC
Current objective: research Open Source Base Index v1.1 without displacing the active P0 hardening line
Relevant approved decisions: D-001 authority split; D-002 candidate memory is not authority; D-003 mandatory Git preflight; D-004 Project Delta only; D-005 Notion + GitHub; D-006 hardening before horizontal expansion
Open P0/P1 items: P0-00 through P0-09 current-head reconciliation and release gates; P1 Repo Map, Local Coding Template, Command Center BFF, Runtime Capability Manifest, module split, retrieval evaluation
Risks / unknowns: development branch is moving; prior 80-base index was produced outside the repository; research conclusions are not implementation facts; licenses and project maturity require point-in-time verification
```

## Purpose

Create a reviewed, code-aware Open Source Base Index that answers, for every relevant project or method:

1. what capability it provides;
2. which AgentOps MIS subproblem it maps to;
3. whether it should be adopted, piloted, referenced, watched, or rejected;
4. whether it is already implemented, partially implemented, only proposed, or not integrated;
5. which MIS authority boundary must remain native;
6. what license, provenance, security, performance, and maintenance risks apply;
7. what evidence would be required before any implementation decision.

This lane is research-only. It does not change the current release priority and does not authorize horizontal feature implementation.

## Relationship to Existing Work

- **updates:** the previously delivered external Open Source Base Index v1.0 and its 80-base registry;
- **updates:** the repository's short `BASE_INDEX.md` by producing a detailed research appendix, not by changing authority rules;
- **supports:** P0-00 current-head re-audit and P0-09 license/provenance evidence;
- **supports later:** P1-01 Repo Map, P1-04 Runtime Capability Manifest, P1-06 retrieval evaluation;
- **does not supersede:** `docs/project/PROJECT_STATE.md`, `DECISIONS.md`, `BACKLOG.md`, or `HANDOFF.md`;
- **does not conflict with D-006:** work is documentation/evidence only and must not displace hardening, CI, or RC work.

## Agent Plan

```yaml
task_understanding: >-
  Reconcile the existing Open Source Base Index with the exact current code line,
  split the research into asynchronous evidence lanes, and produce implementation-aware
  recommendations without integrating new runtimes or changing canonical project state.
referenced_specs:
  - docs/project/PROJECT_STATE.md
  - docs/project/DECISIONS.md
  - docs/project/BACKLOG.md
  - docs/project/HANDOFF.md
  - AGENTS.md
  - PROJECT_SPEC.md
  - AGENT_WORKFLOW.md
  - BASE_INDEX.md
referenced_memories:
  - Notion MIS Project Ledger entries for the v1.5 audit, Knowledge ACL risk, Approval Wall risk, and hardening-first decision
referenced_bases:
  - base_local_tasks
  - base_local_memory
  - base_local_templates
  - Hermes
  - OpenClaw
  - Codex
  - Notion
  - JiuwenSwarm
  - LangGraph
  - CrewAI
proposed_files_to_change:
  - docs/research/OPEN_SOURCE_BASE_INDEX_V1_1_ASYNC_RESEARCH_PLAN.md
  - docs/research/OPEN_SOURCE_BASE_INDEX_V1_1.md
  - docs/research/OPEN_SOURCE_BASE_REGISTRY_V1_1.yaml
  - docs/research/evidence/*.md
risk_level: medium
approval_required: false
execution_steps:
  - freeze and record the exact research baseline
  - inventory current implementation and existing ledger items
  - run independent research lanes
  - record source, version, license, maturity, and code mapping evidence
  - reconcile findings into one index and one machine-readable registry
  - mark every recommendation separately from integration status
  - open a draft documentation PR for review
verification_plan: >-
  Validate links and repository identities, check all claims against primary sources,
  confirm no private attachment or credential is committed, run git diff checks,
  and verify the final registry parses as YAML.
rollback_plan: >-
  Close the draft PR and delete the research branch if the lane duplicates another active
  research branch or if its evidence cannot be separated from unreviewed/private material.
```

## Parallel Research Lanes

| Lane | Scope | Main questions | Output |
|---|---|---|---|
| R1 — Current-code delta | Exact latest AgentOps MIS code and tests | What from v1.0 is now implemented, partial, stale, or still absent? | `evidence/current-code-delta.md` |
| R2 — Harness engineering | Agent harnesses, context engineering, tool boundaries, self-improvement | Which harness patterns improve reliability without replacing MIS authority? | `evidence/harness-engineering.md` |
| R3 — Loop engineering | ReAct, plan/execute, reflection, checkpoint/resume, bounded loops | Which loop primitives map to Task/Run/Approval/Evaluation and what stop conditions are required? | `evidence/loop-engineering.md` |
| R4 — Swarm and coordination | JiuwenSwarm, AutoGen, CrewAI, LangGraph, distributed agent teams | What is true Swarm capability versus supervised multi-agent review, and how should an adapter report evidence? | `evidence/swarm-coordination.md` |
| R5 — Protocols and adapters | MCP, A2A, ACP, Agent Skills, OpenAI-compatible APIs | Which protocol belongs at machine interface, runtime adapter, tool, or marketplace boundaries? | `evidence/protocols-adapters.md` |
| R6 — Knowledge and memory | FTS5, Repo Map, hybrid retrieval, GraphRAG, Mem0, Letta, Graphiti | What should remain Markdown/SQLite, what needs provenance/ACL, and when vectors become justified? | `evidence/knowledge-memory.md` |
| R7 — Approval and security | prepared action, policy engines, sandboxing, secret use, supply chain | Which parts can use OPA/Cedar/sandbox tools and which state machine must remain native MIS? | `evidence/approval-security.md` |
| R8 — Evaluation and observability | OTel/OpenInference, Langfuse, prompt/eval suites, regression gates | What normalized evidence schema and CI gates are needed? | `evidence/eval-observability.md` |
| R9 — Performance and UX | local-first response time, async jobs, caching, UI request fan-out, virtualized views | Which open-source patterns improve speed without rewriting the product? | `evidence/performance-ux.md` |
| R10 — Research Lab and GPU | MLflow, DVC, W&B, Ray, SkyPilot, Slurm, DCGM | What later Research Lab Template objects and adapters are justified? | `evidence/research-lab-gpu.md` |
| R11 — License and provenance | source license, dependencies, UI/art provenance, SBOM | What can be embedded, adapted, invoked externally, or only referenced? | `evidence/license-provenance.md` |

## Recommendation Vocabulary

Each base must carry two independent states.

### Research decision

```text
ADOPT_NOW | PILOT | REFERENCE | WATCH | REJECT
```

### Integration status

```text
IMPLEMENTED | PARTIAL | PROPOSED | NOT_INTEGRATED | SUPERSEDED
```

An `ADOPT_NOW` research decision never implies `IMPLEMENTED`.

## Native MIS Boundary

Open source may provide runtimes, protocols, libraries, evaluation tools, indexing, CI, security scanning, and UI primitives. The following remain AgentOps MIS authority and must not be silently delegated:

```text
Workspace and identity
Task and Work Package
Agent Plan and approval role separation
Run and Tool Call ledger
Prepared Action and exact-resume state
Approval and policy decision evidence
Artifact and customer delivery evidence
Evaluation and memory-review status
Audit and authority-chain relationships
```

## Evidence Rules

- Prefer project repositories, official documentation, standards, and primary papers.
- Record repository, exact version or commit when available, license, last verified date, and source URL.
- Separate a project's advertised capability from code-confirmed capability.
- Separate framework runtime state from MIS canonical state.
- Do not copy large source sections or vendor documentation into the repository.
- Do not commit the user's uploaded course PDFs, architecture transcripts, private prompts, raw customer content, or credentials.
- Uploaded MIS analysis/design/implementation course material may inform taxonomy privately; only original summaries and traceable public-source evidence may enter the repository.

## Deliverables

1. `OPEN_SOURCE_BASE_INDEX_V1_1.md` — reviewed human-readable index.
2. `OPEN_SOURCE_BASE_REGISTRY_V1_1.yaml` — machine-readable registry.
3. Evidence note per lane under `docs/research/evidence/`.
4. Current-code delta table for commit-aware implementation status.
5. Adoption map: direct dependency, adapter, sidecar, protocol, reference pattern, or reject.
6. Risk map: license, security, privacy, telemetry, performance, lock-in, maturity, and maintenance.
7. A final Project Delta that updates only what changed.

## Acceptance Criteria

- The exact repository, branch, and starting commit appear in every consolidated deliverable.
- Existing Notion Ledger items are linked rather than duplicated.
- Every base has both a research decision and an integration status.
- JiuwenSwarm is not described as integrated unless code and tests prove an adapter exists.
- The current Hermes/OpenClaw supervised loop is not mislabeled as a distributed Swarm.
- No proposal changes P0/P1 priority without naming displaced work and owner approval.
- No private upload, credential, raw prompt/response, or generated runtime state is committed.
- The final PR remains draft until evidence and licensing fields are reviewed.

## Project Delta

```yaml
type: Task
title: Open Source Base Index v1.1 async parallel research
status: In Progress
priority: P1
module: Research
summary: >-
  Start a non-blocking documentation and evidence lane to reconcile the external
  80-base index with the latest AgentOps MIS code and deepen Harness, Loop, Swarm,
  protocol, knowledge, security, evaluation, performance, Research Lab, and license research.
source: user-approved GitHub and Notion write request on 2026-06-22
repository: geogejoy107-jpg/agentops-mis-mvp
branch: research-open-source-base-index-v1-1
commit: 169924acdb6a301c1c870f48449aedc76bf6fb5a
duplicate_of: null
updates: external Open Source Base Index v1.0; repository BASE_INDEX.md research coverage
supersedes: null
conflicts_with: null
owner: project owner + research agents
next_action: execute R1 current-code delta and R2/R3/R4 Harness-Loop-Swarm evidence lanes
canonical: false
```
