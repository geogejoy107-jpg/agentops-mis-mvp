# Open Source Base Index v1.1 — Evidence Compendium

> Repository: `geogejoy107-jpg/agentops-mis-mvp`  
> Baseline: `codex/agent-gateway-kb-demo` @ `4a4a96dc079d7d178894902626728648e73441b2`  
> Research branch: `research-osbi-v1-1-final`  
> Verified: 2026-06-22  
> Canonical: false

## R1 — Current-code delta

The old research baselines `169924ac...` and `3fe3c637...` are stale. At `4a4a96dc079d7d178894902626728648e73441b2` the project state is `READY_TO_MERGE`; P0-01
through P0-09 are keep-green release invariants. Repo Map, Local Coding Project Template, Command Center BFF and
Runtime Capability Manifest are Done. Module splitting has reached slices 1–10 and remains in progress; P1-06 retrieval evaluation is ready.

This changes the research from “build missing fundamentals” to “choose adapters and differentiation without
duplicating native authority.” Exact-head GitHub Actions run 326 succeeded.

## R2 — Harness engineering

A harness is the governed execution envelope around a runtime:

```text
Approved Plan → immutable Harness Manifest → runtime/sandbox/tools
→ normalized events/artifacts → MIS Evaluation/Delivery/Memory/Audit
```

The manifest binds workspace/task/plan/agent, context references, runtime capability manifest, read/write/network/
secret scope, model route, budgets, stop/approval/checkpoint policy and redaction version. Material scope changes
create a new version. OpenAI Agents SDK, PydanticAI, LangGraph, SWE-agent and OpenHands are adapter/reference
candidates; none may own MIS Task/Run/Approval/Memory state.

## R3 — bounded Loop engineering

A Loop is a finite state machine:

```text
INTAKE → PLAN → RETRIEVE → ACT → OBSERVE → EVALUATE
                     ↖ REVISE / RETRY ↙
          WAIT_APPROVAL | COMPLETE | BLOCKED | FAILED
```

Required bounds: turns, time, cost, tool calls, repeated action hash, no-progress, retries, approval expiry and
terminal rubric. Reflection text is not proof; improvement requires a changed Artifact and Evaluation. External
checkpoint replay must obey MIS PreparedAction consume-once semantics.

## R4 — Swarm coordination

Capability ladder: supervisor-worker → handoff team → dynamic team → distributed Swarm → reviewed evolving ecosystem.
The current Hermes/OpenClaw/operator path is supervised and bounded, not distributed. JiuwenSwarm is the staged PoC
candidate; upstream leader/team/subtask/run/tool/skill concepts must map to AgentPlan/Agent/Task/Run/ToolCall/
PreparedAction/Evaluation/Artifact/Audit. Dynamic scope expansion requires a new plan or approval.

## R5 — protocols and adapters

- **Agent Skills** packages methods and progressive disclosure.
- **MCP** connects an LLM host to tools/resources/prompts.
- **A2A** supports peer-agent discovery, tasks, artifacts and async collaboration.
- **Agent Gateway** remains identity, scope, plan, run, approval and audit authority.
- **ACP** is superseded by A2A and should not receive a separate integration.
- OpenAPI describes current HTTP contracts; CloudEvents/AsyncAPI are optional event envelopes.

MCP consent/tool-safety guidance is not a policy engine; every tool still passes Agent Gateway scope and
PreparedAction governance.

## R6 — knowledge and memory

Current baseline: Markdown + SQLite FTS5, workspace/access metadata, retrieval provenance and native Repo Map.

Evolution ladder:

1. approved Markdown/reviewed memory;
2. FTS5 ranking/snippets;
3. heading-aware chunks and bilingual evaluation;
4. Repo Map/symbol localization;
5. hybrid sparse+dense retrieval only after measured need;
6. reranking/temporal graph retrieval;
7. external vector/graph service only after local limits are proven.

Mem0, Letta and Graphiti are pattern/sidecar candidates; their state never becomes reviewed organizational memory
automatically. P1-06 must record Recall@5, MRR, p95, index time and disk size.

## R7 — approval, sandbox and security

Native flow:

```text
normalized action → capability/trust policy
→ allow | deny | require approval
→ PreparedAction(action_hash, checkpoint, idempotency)
→ human decision → exact resume once → provider side-effect evidence
```

OPA and Cedar are policy references, not Approval authority. gVisor is the first hosted-sandbox PoC candidate;
Firecracker is later. Knowledge stores secret references only. Syft/Gitleaks/Trivy can strengthen existing custom
release gates; SOPS can be piloted for encrypted local configuration.

## R8 — evaluation and observability

Telemetry and authority are separate planes. OpenTelemetry/OpenInference may export traces, metrics and logs; sampled
telemetry cannot prove a business action. MIS stores compact evidence. Promptfoo is the leading near-term CI
experiment; Inspect AI is a research harness. Langfuse, MLflow and Phoenix are optional sidecars and must not create
a second Run/Evaluation authority.

## R9 — performance and UX

Keep the existing Command Center BFF, read-model cache, pagination, responsiveness tests, SQLite WAL and Vite UI.
Measure before adding TanStack Query/Virtual. Target p95: ordinary reads <150 ms, scoped queue/knowledge <200 ms,
accepted workflow/approval <300 ms, first useful command center <1 s. Lazy-load logs, isolate panel failures and keep
Pixel Office as a visualizer only.

## R10 — Research Lab and GPU

Proposed flow:

```text
Research question → Experiment Plan → data/code/config versions
→ approved Compute Job → metrics/checkpoints/artifacts
→ Evaluation → report/paper candidate → reviewed Memory
```

First-party objects should include ResearchProject, Dataset, Experiment, Trial, ComputeResource, ComputeJob,
ModelVersion, MetricSeriesRef, Paper and ReproductionCase. MLflow, DVC, Ray/SkyPilot/Slurm, DCGM, Optuna, Hydra,
JupyterHub and OpenLineage remain adapters/specialized bases. First MVP: one local GPU/server, one versioned dataset,
MLflow tracking, DCGM metrics and a governed training task.

## R11 — license and provenance

Each base records canonical repo, pinned version/commit, license and file exceptions, adoption mode, copied/modified
files, notices, SBOM, maintenance/security signal and verification date. Reference-only never authorizes copying.
Commercial builds exclude unclear/non-commercial visual assets. Recommended sequence: current license/notices →
Syft SPDX/CycloneDX SBOM → Gitleaks/Trivy → upstream Scorecard signal → Cosign/SLSA when distributable artifacts exist.

## MIS lifecycle crosswalk

Information-system work remains distinct:

| Phase | AgentOps evidence |
|---|---|
| Strategy/planning | Approved Decision, Project, priority, budget and risk |
| Analysis (“what”) | Requirement, stakeholder, acceptance, process/data model |
| Design (“how”) | AgentPlan, architecture, interface and capability/workspace manifest |
| Implementation | WorkPackage, Task, Run, ToolCall, PreparedAction, Artifact |
| Evaluation | test/evaluation artifact, delivery gate, experiment comparison |
| Operation | health, checkpoint, incident, candidate memory and audit |
| Transformation | template adoption, ROI/risk and organizational outcome |

The acquisition principle is the same: self-build differentiating authority and business logic; adopt mature
standard tools for generic capabilities.
