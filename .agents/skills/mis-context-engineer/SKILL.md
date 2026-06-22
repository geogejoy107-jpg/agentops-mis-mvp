---
name: mis-context-engineer
description: Build an auditable, authority-aware and token-efficient project Context Manifest with a versioned Harness and bounded Loop.
version: 0.2.0
status: prototype
---

# MIS Context Engineer

This read-only Skill assembles trustworthy project context for AgentOps MIS. It records sources, scope checks, inclusions, exclusions, conflicts, iteration results, token estimates and latency estimates. Memory output remains a candidate for human review.

## Operating model

```text
MIS authority + HarnessProfile + LoopPolicy
-> gated retrieval
-> bounded evaluation and refinement
-> Context Manifest
-> candidate memory proposal
-> human review
```

- **Harness Engineering** defines the reproducible context environment: authority order, source scope, retrievers, stable prefix, cache policy, token budgets, metrics and validation.
- **Loop Engineering** defines bounded iteration: phases, checkpoints, evaluation, refinement, budgets and stop reasons.
- **AgentOps MIS** remains authoritative for project state, execution evidence, review and audit.

## Authority order

1. GitHub exact repository, branch, commit, PR, diff and test evidence for code facts.
2. AgentOps MIS SQLite/API for run, artifact, evaluation, memory-review and audit facts.
3. Notion Project Ledger plus `docs/project/` for reviewed decisions, risks, backlog and handoff.
4. Approved MIS memory.
5. Candidate memory, external research and chat history as non-authoritative support.

Lower-authority material cannot silently replace higher-authority evidence.

## Inputs

```yaml
objective: string
project_context:
  repository: owner/repo
  branch: exact branch or Unknown
  commit: exact SHA or Unknown
  workspace_id: string
  project_id: string | null
  task_id: string | null
  agent_id: string | null
harness_profile: object | path
loop_policy: object | path
candidates: list
previous_manifest: object | path | null
historical_as_of: timestamp | null
```

## HarnessProfile

The HarnessProfile is versioned and content-addressed. It defines:

```text
authority and source order
workspace / project / task scope
retriever order and escalation
stable-prefix and cache policy
total and tier token budgets
observability and validation
candidate-only memory policy
```

Harness invariants:

- scope and source checks run before ranking;
- repository facts require an exact commit;
- a short stable prefix points to deeper project knowledge;
- task-specific context follows the stable prefix;
- local lexical retrieval runs before optional retrieval;
- source, policy, Harness and cache hashes are deterministic;
- optional retrieval failure falls back to the local lexical path;
- candidate memory cannot act as canonical authority;
- every result contains bounded summaries and evidence references.

Conform to `schemas/harness-profile.schema.json`.

## LoopPolicy

```text
PREPARE -> RETRIEVE -> ASSESS -> PACK -> EVALUATE -> REFINE or STOP
```

Every iteration records:

```yaml
iteration:
retrieval_mode:
candidates_considered:
included_count:
excluded_count:
full_tokens:
delta_tokens:
coverage:
authority_precision:
scope_violations:
marginal_gain:
latency_ms:
checkpoint_hash:
decision:
```

Stop with a block when exact Git context is missing for a code claim, visibility cannot be proven, an authority conflict blocks the objective or mandatory context cannot fit.

Stop successfully when mandatory authority and acceptance evidence are included, coverage passes, scope/authority checks pass and the manifest validates.

Stop economically when marginal gain is below threshold, token/latency budget is exhausted, maximum iterations are reached or no useful source remains.

Optional retrieval may be used only when the Harness allows it and the current evaluation has a named coverage gap.

Conform to `schemas/loop-policy.schema.json`.

## TRACE workflow

### T — Truth and Scope

Read `PROJECT_STATE`, `DECISIONS`, `BACKLOG`, `HANDOFF`, `AGENTS.md`, `PROJECT_SPEC.md`, `AGENT_WORKFLOW.md`, `BASE_INDEX.md`, then task-specific specs, code and tests. Verify repository, branch, commit and workspace/project/task scope.

### R — Retrieve

Use progressive disclosure:

```text
Tier 0: stable map and rules
Tier 1: mandatory project/task authority
Tier 2: implementation, tests and evidence
Tier 3: approved reusable memory
Tier 4: candidate memory and external research
```

Start with mandatory plus lexical retrieval. Escalate only when evaluation requires it.

### A — Assess

Apply hard gates before soft ranking. Exclude missing sources, invisible scope, candidate-as-authority, stale or superseded facts, unresolved authority conflicts and historical mismatches.

Classify relationships as:

```text
new | duplicate_of | updates | supersedes | conflicts_with | derived_from
```

### C — Compose

Reserve capacity for output and mandatory authority, add the stable prefix, exact acceptance and implementation evidence, then diverse supporting items by marginal utility per token. Record every budget exclusion.

Optimize:

```text
coverage + authority + evidence diversity + task utility
- redundancy - staleness - token cost - latency cost
```

For repository work, prefer symbols, signatures and relevant tests over complete-file inclusion.

### E — Explain and Emit

Emit:

1. Context Manifest conforming to `schemas/context-manifest.schema.json`;
2. candidate Memory Write Proposal conforming to `schemas/memory-write-proposal.schema.json`;
3. evaluation metrics for coverage, authority precision, scope, conflicts, full/delta tokens, cache reuse, token efficiency, latency, iterations and stop reason.

## Speed and token controls

1. gate invalid candidates before expensive work;
2. keep an exact stable prefix and append task context;
3. reuse items only when source, scope and policy hashes match;
4. pass project/task/evidence deltas instead of full conversation history;
5. use tier budgets so optional context cannot replace mandatory context;
6. use lexical-first adaptive retrieval;
7. exit early when coverage passes or marginal utility reaches zero;
8. use deterministic code for scope, hashing, dedupe and budgeting;
9. parallelize only independent reads and evaluation dimensions;
10. report estimated and provider-reported metrics separately.

See `references/LOOP_HARNESS_ENGINEERING.md` and `references/PERFORMANCE_TOKEN_EFFICIENCY.md`.

## Verification

```bash
python3 scripts/mis_context_engineer_smoke.py
python3 scripts/mis_context_engineer_cli.py validate --manifest .agents/skills/mis-context-engineer/examples/sample-manifest.json
python3 scripts/mis_context_engineer_cli.py benchmark --cases .agents/skills/mis-context-engineer/evals/performance_cases.json
```

The suite covers authority conflicts, cross-workspace isolation, history, missing Git context, strict budgets, deduplication, repository localization, stable cache keys, delta reuse, early exit and bounded iterations.
