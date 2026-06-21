---
name: mis-context-engineer
description: Build an auditable, authority-aware, scope-safe context manifest and candidate-only memory writeback proposals for AgentOps MIS.
version: 0.1.0
status: prototype
---

# MIS Context Engineer Skill

Use this skill when an Agent must assemble trustworthy project context, reconcile competing memories, localize repository evidence, or propose durable lessons without silently changing canonical project state.

This skill exposes a **decision trace**—sources consulted, gates applied, inclusions, exclusions, conflicts, and writeback proposals. It must not expose or persist private chain-of-thought, raw prompts, raw model responses, secrets, or private transcripts.

## Goals

- give multiple Agent conversations the same verifiable project context;
- distinguish authority from relevance;
- enforce workspace, project, task, and access boundaries before ranking;
- preserve source, version/hash, time, and relationship provenance;
- fit the smallest sufficient context inside a token budget;
- make every inclusion, exclusion, conflict, and candidate writeback reviewable;
- keep all automatically generated memory candidate-only until human review.

## Non-goals

- replacing GitHub, AgentOps MIS SQLite/API, or the Notion Project Ledger as authority;
- automatically approving or promoting memory;
- storing complete conversations or hidden reasoning;
- requiring embeddings, a vector database, or a graph database in v0;
- changing runtime, database, or project-governance state by itself.

## Authority Order

Use the repository's accepted authority split:

1. GitHub repository, exact branch/commit, PR, diff, and test evidence for code facts.
2. AgentOps MIS SQLite/API for runs, tool calls, approvals, artifacts, evaluations, memory review, and audit facts.
3. Notion MIS Project Ledger plus `docs/project/` for reviewed decisions, requirements, risks, backlog, and handoff.
4. Approved MIS memory for reusable reviewed lessons.
5. Candidate memory, external research, and chat history only as source material.

A lower authority source may improve recall but must not silently override a higher authority source.

## Required Inputs

```yaml
objective: string
repository: owner/repo
branch: exact branch or Unknown
commit: exact SHA or Unknown
workspace_id: string
project_id: string | null
task_id: string | null
agent_id: string | null
token_budget: integer
allowed_sources:
  - github
  - mis_ledger
  - project_docs
  - approved_memory
  - candidate_memory
  - external_research
writeback_mode: none | candidate_only
semantic_retrieval: false
historical_as_of: ISO-8601 timestamp | null
```

Defaults:

```yaml
writeback_mode: candidate_only
semantic_retrieval: false
token_budget: 8000
```

## TRACE Workflow

### T — Truth and Scope

1. Read in order:
   - `docs/project/PROJECT_STATE.md`
   - `docs/project/DECISIONS.md`
   - `docs/project/BACKLOG.md`
   - `docs/project/HANDOFF.md`
   - `AGENTS.md`
   - `PROJECT_SPEC.md`
   - `AGENT_WORKFLOW.md`
   - `BASE_INDEX.md`
   - task-specific specs, code, tests, PRs, and audit evidence.
2. Verify exact repository, branch, and commit.
3. Establish `workspace_id`, `project_id`, `task_id`, identity, and allowed sources.
4. Apply visibility and redaction policy **before** retrieval scoring.
5. If branch or commit is `Unknown`, block code-state claims and emit an unresolved question.

Required preflight output:

```text
Repository:
Branch:
Commit:
Current milestone:
Objective:
Relevant approved decisions:
Open P0/P1 items:
Workspace / project scope:
Risks / unknowns:
```

### R — Retrieve

Retrieve in two passes.

**Pass 1: mandatory authority context**

- current Project State;
- relevant approved decisions;
- active backlog and handoff;
- exact task/spec acceptance criteria;
- exact Git branch/commit and touched implementation evidence.

**Pass 2: supporting context**

- SQLite FTS5/BM25 results from visible knowledge documents;
- approved project memory;
- task/run/artifact/evaluation/audit summaries;
- repository symbols and tests selected by a Repo Map backend;
- optional semantic, entity, or graph results when configured;
- candidate memory and external research, clearly marked non-authoritative.

Every retrieved candidate must retain:

```yaml
source_ref:
source_hash_or_commit:
source_type:
authority_class:
workspace_id:
project_id:
task_id:
access_tags:
observed_at:
valid_from:
valid_to:
```

Do not retain raw secret-bearing payloads merely because a retriever returned them.

### A — Assess

Apply hard gates before soft ranking.

#### Hard gates

Reject or quarantine an item when:

- the source does not exist or its version/hash cannot be verified;
- workspace/project/access scope is not visible to the requesting identity;
- the item contains unredacted secrets or prohibited private content;
- a candidate memory is being used as canonical authority;
- a newer item supersedes it for a current-state question;
- a conflict with an equal or higher authority source is unresolved;
- the requested historical time does not overlap the item's validity window.

#### Relationship classification

For each durable claim, classify exactly one primary relationship:

```text
new | duplicate_of | updates | supersedes | conflicts_with | derived_from
```

Do not create a new memory proposal when `duplicate_of` is sufficient. Do not silently resolve `conflicts_with` without an approved decision or evidence.

#### Soft ranking

After hard gates, a backend may compute:

```text
score =
    0.30 * task_relevance
  + 0.20 * lexical_score
  + 0.10 * semantic_score
  + 0.10 * entity_or_graph_score
  + 0.15 * authority_score
  + 0.10 * freshness_score
  + 0.05 * evidence_quality
```

These are v0 starting weights, not canonical constants. Tune them only through named evaluation cases. Permission, authority eligibility, and explicit conflict are gates—not weights that similarity may overcome.

### C — Compose

Construct the smallest sufficient context in this order:

1. reserve budget for objective, acceptance criteria, current branch/commit, and safety rules;
2. include mandatory authority context;
3. include implementation evidence needed to answer or act;
4. add diverse supporting items by marginal task utility per token;
5. avoid near-duplicates and repeated summaries;
6. retain unresolved conflicts and questions explicitly;
7. stop before the token limit and record every budget exclusion.

The packer should optimize for:

```text
coverage + authority + evidence diversity + task utility - redundancy - staleness
```

For repository work, prefer symbols, signatures, relevant tests, and dependency edges over dumping complete files. For ordinary documents, prefer contextual chunks that retain their document and section provenance.

### E — Explain and Emit

Emit three bounded artifacts.

#### 1. Context Manifest

Must include:

- exact input scope and Git context;
- policy and token budget;
- included items with reasons and token estimates;
- excluded items with reason codes;
- conflicts and unresolved questions;
- budget usage and a deterministic output hash.

Conform to `schemas/context-manifest.schema.json`.

#### 2. Memory Write Proposals

May contain only candidate records. Each proposal must include source references, relationship classification, confidence, access tags, review requirement, and redaction proof.

Conform to `schemas/memory-write-proposal.schema.json`.

#### 3. Evaluation Summary

Report at least:

```yaml
authority_precision:
retrieval_coverage:
scope_violations:
stale_memory_selected:
conflicts_detected:
duplicate_proposals:
token_budget_used:
manifest_valid:
```

## Memory Lifecycle

```text
Observed source
-> extracted candidate
-> scope/redaction/provenance checks
-> duplicate/conflict analysis
-> Memory Write Proposal
-> human review
-> approved / rejected / superseded
-> later TTL or evidence review
```

This skill may create `candidate` proposals. It must never set `Approved`, `Implemented`, or canonical project state on its own.

## Failure Behavior

- Missing repository/branch/commit for code work: stop code-state assumptions.
- Missing visibility proof: exclude the item and record `scope_denied`.
- Missing source/version: exclude the item and record `missing_source`.
- Conflicting canonical sources: emit `conflict_unresolved`; do not choose silently.
- Token budget too small for mandatory context: emit `insufficient_budget`; do not truncate safety rules.
- Optional retriever unavailable: continue with FTS5/lexical retrieval and record the degraded mode.
- Validation failure: do not publish the manifest as verified.

## Safety

Never emit or persist:

- credentials, tokens, private keys, passwords, or connection strings;
- raw customer/private transcripts;
- arbitrary raw prompts or model responses;
- hidden chain-of-thought;
- cross-workspace content without visibility proof;
- unsupported claims phrased as current facts.

Prefer stable IDs, hashes, bounded summaries, redaction markers, and evidence links.

## Minimum Evaluation Set

Before runtime integration, pass the named cases in `evals/cases.yaml`, including:

- candidate memory contradicting an approved decision;
- cross-workspace retrieval leakage;
- stale and superseded memory;
- unresolved equal-authority conflict;
- missing Git commit;
- strict token budget;
- duplicate memory proposal;
- historical `as_of` retrieval;
- repository localization with relevant tests;
- secret-bearing source redaction.

## Example Invocation

```yaml
objective: Design the first async Codex worktree slice without contradicting the current release milestone.
repository: geogejoy107-jpg/agentops-mis-mvp
branch: codex/agent-gateway-kb-demo
commit: 4dd4d1a49e499675fe13ec72b915553669f12d3c
workspace_id: local-demo
project_id: agentops-mis
task_id: null
agent_id: codex-context-worker
token_budget: 6000
allowed_sources: [github, project_docs, approved_memory, candidate_memory, external_research]
writeback_mode: candidate_only
semantic_retrieval: false
historical_as_of: null
```

Expected behavior:

- current milestone and accepted decisions are mandatory;
- candidate research may support but not override them;
- code claims are pinned to the named commit;
- all inclusions and exclusions are visible in a Context Manifest;
- any durable lesson is proposed for review, never auto-promoted.
