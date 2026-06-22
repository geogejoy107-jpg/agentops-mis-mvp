# Open Source Base Index v1.1 — Current-Head Completion Plan

> Repository: `geogejoy107-jpg/agentops-mis-mvp`  
> Branch: `research-osbi-v1-1-current-head`  
> Base branch: `codex/agent-gateway-kb-demo`  
> Frozen starting commit: `3fe3c6376f914ecd275786978d8d1e6df3037f98`  
> Started: 2026-06-22  
> Canonical: false

## Preflight

```text
Repository: geogejoy107-jpg/agentops-mis-mvp
Branch: research-osbi-v1-1-current-head
Commit: 3fe3c6376f914ecd275786978d8d1e6df3037f98 (starting point)
Current milestone: READY_TO_MERGE v1.5 release candidate; keep exact-head gates green
Current objective: complete Open Source Base Index v1.1 as a non-production, evidence-only research package
Relevant approved decisions: D-001 through D-006
Open P0/P1 items: P0 keep-green gates; P0-11 manual ChatGPT instructions; P1-05 module split in progress; P1-06 knowledge chunking/retrieval evaluation ready
Risks / unknowns: development branch can move; research recommendations do not authorize integration; old research PR #12 is based on a stale head; licenses and upstream maturity are point-in-time facts
```

## Relationship

- `updates`: Notion Ledger task `T-OSBI-001` and external Open Source Base Index v1.0.
- `supersedes`: GitHub research branch `research-open-source-base-index-v1-1` and Draft PR #12 for final integration purposes, because the product branch advanced from `169924ac...` to `3fe3c637...`.
- `does_not_supersede`: the historical R1 evidence or R2-R4 research notes; those are migrated and reconciled, not erased.
- `supports`: P1-06 knowledge/retrieval evaluation, future P2 runtime adapters, Research Lab template, and marketplace design.
- `conflicts_with`: none, provided no production dependency or priority change is made.

## Agent Plan

```yaml
task_understanding: >-
  Finish the code-aware Open Source Base Index using the latest verified product head,
  migrate and update R1-R4 research, complete R5-R11, publish a human-readable index
  and machine-readable registry, and synchronize a concise Project Delta to GitHub and Notion.
referenced_specs:
  - docs/project/PROJECT_STATE.md
  - docs/project/DECISIONS.md
  - docs/project/BACKLOG.md
  - docs/project/HANDOFF.md
  - AGENTS.md
  - PROJECT_SPEC.md
  - AGENT_WORKFLOW.md
  - BASE_INDEX.md
  - docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md
referenced_memories:
  - Notion T-OSBI-001
  - Notion v1.5 audit and hardening entries
referenced_bases:
  - base_local_tasks
  - base_local_memory
  - base_local_templates
  - Codex
  - Hermes
  - OpenClaw
  - MCP
  - A2A
  - Agent Skills
  - JiuwenSwarm
proposed_files_to_change:
  - docs/research/OSBI_V1_1_CURRENT_HEAD_PLAN.md
  - docs/research/OPEN_SOURCE_BASE_INDEX_V1_1.md
  - docs/research/OPEN_SOURCE_BASE_REGISTRY_V1_1.yaml
  - docs/research/evidence/*.md
  - docs/research/OSBI_V1_1_HANDOFF.md
risk_level: medium
approval_required: false
execution_steps:
  - verify latest product head and governance state
  - migrate and reconcile R1-R4 research
  - complete R5-R11 using primary upstream sources
  - separate research_decision from integration_status
  - validate YAML and source metadata
  - open a replacement Draft PR and update Notion memory
verification_plan: >-
  Parse YAML, check required fields and unique IDs, inspect all files for secret-like strings,
  confirm no uploaded private source file is committed, verify branch/commit/PR facts, and record
  current CI status without claiming a pass that did not occur.
rollback_plan: >-
  Close the replacement Draft PR and retain the prior research package as historical evidence if
  the current-head package introduces conflicts, unverifiable claims, or private material.
```

## Deliverables

1. Consolidated human-readable Base Index v1.1.
2. Machine-readable Base Registry v1.1.
3. Evidence notes for current-code delta, Harness, Loop, Swarm, protocols, knowledge/memory, approval/security, evaluation/observability, performance/UX, Research Lab/GPU, and license/provenance.
4. Current-head handoff and Project Delta.
5. Notion Project Ledger update, `Canonical=false`.

## Acceptance

- Exact repository, branch, and starting commit are stated.
- Recommendations and integration facts remain separate.
- Native MIS authority boundaries match `docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md`.
- Current AgentOps capabilities are reconciled against `3fe3c637...`, not the older `169924ac...` baseline.
- No raw user upload, secret, prompt/response, private transcript, runtime DB, or generated index enters GitHub.
- The replacement PR remains Draft until reviewed.
