# Open Source Base Index v1.1 — Handoff

> Repository: `geogejoy107-jpg/agentops-mis-mvp`  
> Branch: `research-osbi-v1-1-current-head`  
> Product baseline: `codex/agent-gateway-kb-demo` @ `3fe3c6376f914ecd275786978d8d1e6df3037f98`  
> Last content commit before this handoff: `863d302c43d57b803c665ca6e5010eba5809f0e6`  
> Handoff date: 2026-06-22  
> Canonical: false

## Completed

- Rebased the research lane on the latest verified product head rather than the stale `169924ac...` baseline.
- Reconciled current implementation truth: product state `READY_TO_MERGE`; exact-head CI success; P0 invariants keep-green; P1 Repo Map, Local Coding Project Template, Command Center BFF and Runtime Capability Manifest Done.
- Produced a consolidated human-readable Open Source Base Index with 66 bases.
- Produced a machine-readable YAML registry with independent `decision` and `status` fields.
- Consolidated R1–R11 evidence: current-code delta, Harness, bounded Loop, Swarm, protocols, knowledge/memory, approval/security, evaluation/observability, performance/UX, Research Lab/GPU and license/provenance.
- Added an MIS lifecycle crosswalk from planning and analysis through design, implementation, evaluation and operation.
- Preserved the first-party MIS authority boundary from `docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md`.
- Kept all user-uploaded course PDFs and architecture transcripts out of the repository; only original synthesis was committed.

## Deliverables

```text
docs/research/OSBI_V1_1_CURRENT_HEAD_PLAN.md
docs/research/OPEN_SOURCE_BASE_INDEX_V1_1.md
docs/research/OPEN_SOURCE_BASE_REGISTRY_V1_1.yaml
docs/research/evidence/OSBI_V1_1_EVIDENCE_COMPENDIUM.md
docs/research/OSBI_V1_1_HANDOFF.md
```

## Verification

- Product baseline verified from GitHub PR #1 at `3fe3c6376f914ecd275786978d8d1e6df3037f98`.
- Product-baseline GitHub Actions run 307 concluded `success`.
- YAML source was parsed locally and contains 66 unique base IDs.
- Registry entries contain recommendation, actual integration status and source URL.
- Research documents were checked for raw credentials, private transcripts and uploaded-file paths before synchronization.
- No production code, dependency, schema, priority or approved canonical decision was changed.

## Supersession

For final integration and review, this current-head branch supersedes the stale research integration vehicle:

```text
branch: research-open-source-base-index-v1-1
Draft PR: #12
old research head: 1cc65332196dd4d2b7f35b74892e3286b55ca4d9
```

The historical R1 and R2–R4 findings are not discarded; they are reconciled into the new compendium.

## Open risks

- Every upstream license and maturity judgment is point-in-time and must be rechecked before code adoption.
- `ADOPT_NOW` is a research recommendation, not permission to merge a dependency.
- JiuwenSwarm remains `PILOT / NOT_INTEGRATED` until an adapter and evidence tests exist.
- MCP and A2A remain proposed/pilot protocol bridges; Agent Gateway remains identity, scope and audit authority.
- P1-05 module splitting is still in progress; P1-06 retrieval evaluation is ready but not completed by this research lane.
- The research PR must remain Draft until reviewed and its own CI status is recorded.

## Next single action

Human-review the Draft PR and approve only one first implementation experiment after the v1.5 merge. The recommended first experiment is P1-06: FTS5 baseline plus heading-aware chunking and bilingual Recall@5/MRR/p95 evaluation. MCP, JiuwenSwarm, vector stores and Research Lab adapters should not displace it without an explicit priority decision.

## Project Delta

```yaml
type: Handoff
title: Open Source Base Index v1.1 current-head research delivery
status: Proposed
priority: P1
module: Research
summary: >-
  Completed a current-head, 66-base Open Source Base Index and R1-R11 evidence
  compendium while preserving native MIS authority and making no production change.
source: GitHub research branch and Notion T-OSBI-001
repository: geogejoy107-jpg/agentops-mis-mvp
branch: research-osbi-v1-1-current-head
commit: runtime-derived from the Draft PR head
updates: T-OSBI-001; external Open Source Base Index v1.0
supersedes: research-open-source-base-index-v1-1 and Draft PR #12 as final integration vehicle
conflicts_with: null
owner: Project Owner + Research Agents
next_action: review the Draft PR and choose one post-merge P1 experiment
canonical: false
```
