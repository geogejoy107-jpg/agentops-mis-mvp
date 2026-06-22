# Open Source Base Index v1.1 — Final Handoff

> Repository: `geogejoy107-jpg/agentops-mis-mvp`  
> Branch: `research-osbi-v1-1-final`  
> Product baseline: `codex/agent-gateway-kb-demo` @ `4a4a96dc079d7d178894902626728648e73441b2`  
> Handoff date: 2026-06-22  
> Canonical: false

## Completed

- Rebased the research delivery onto the latest verified product head.
- Reconciled current project truth: `READY_TO_MERGE`; exact-head CI run 326 succeeded; P0 invariants are keep-green; P1-01 through P1-04 are Done; P1-05 remains In Progress; P1-06 is Ready.
- Delivered a consolidated human-readable index for 66 bases.
- Delivered a machine-readable registry with independent recommendation and integration status.
- Consolidated R1-R11 evidence covering code delta, Harness, bounded Loop, Swarm, protocols, knowledge/memory, approval/security, evaluation/observability, performance/UX, Research Lab/GPU and license/provenance.
- Preserved the first-party MIS authority boundary.
- Kept all uploaded course PDFs, transcripts, credentials, raw prompts/responses and runtime state out of GitHub.

## Deliverables

```text
docs/research/OSBI_V1_1_FINAL_PLAN.md
docs/research/OPEN_SOURCE_BASE_INDEX_V1_1.md
docs/research/OPEN_SOURCE_BASE_REGISTRY_V1_1.yaml
docs/research/evidence/OSBI_V1_1_EVIDENCE_COMPENDIUM.md
docs/research/OSBI_V1_1_HANDOFF.md
```

## Verification

- Product baseline and current project state read from GitHub at `4a4a96dc...`.
- GitHub Actions run 326 concluded `success` on that product commit.
- YAML parses and contains 66 unique IDs with source, recommendation and integration status.
- Research package contains no production code or dependency changes.
- No canonical decision, backlog priority or approved state was changed.

## Supersession

This final branch/PR supersedes the following as the final integration vehicle:

```text
research-open-source-base-index-v1-1 / PR #12
research-osbi-v1-1-current-head / PR #15
```

Their useful evidence is preserved in the consolidated compendium.

## Open risks

- Upstream licenses and maturity must be rechecked before adoption.
- `ADOPT_NOW` is not merge authorization.
- JiuwenSwarm remains `PILOT / NOT_INTEGRATED` until adapter code and tests exist.
- MCP/A2A remain protocol proposals; Agent Gateway remains authority.
- Research PR stays Draft until human review and its own CI result are recorded.

## Next single action

Review the Draft PR and, after the v1.5 merge, approve one P1 experiment. The recommended first experiment is P1-06: FTS5 baseline plus heading-aware chunking and bilingual Recall@5/MRR/p95 evaluation.

## Project Delta

```yaml
type: Handoff
title: Open Source Base Index v1.1 final current-head research delivery
status: Proposed
priority: P1
module: Research
summary: Completed a 66-base current-head index and R1-R11 evidence package without production or canonical-state changes.
source: GitHub final research PR and Notion T-OSBI-001
repository: geogejoy107-jpg/agentops-mis-mvp
branch: research-osbi-v1-1-final
commit: runtime-derived from Draft PR head
updates: T-OSBI-001; external Open Source Base Index v1.0
supersedes: PR #12 and PR #15 as final integration vehicles
conflicts_with: null
owner: Project Owner + Research Agents
next_action: review Draft PR; then choose one post-merge P1 experiment
canonical: false
```
