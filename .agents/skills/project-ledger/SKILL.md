---
name: project-ledger
description: Maintain durable AgentOps MIS project continuity by verifying Git context, reading canonical state, deduplicating new ideas, emitting Project Delta records, and updating project state, decisions, backlog, and handoff only when evidence warrants it.
---

# Project Ledger Skill

Use this skill for any substantive AgentOps MIS discussion or work cycle that can change project direction, code, architecture, priority, risk, delivery, or durable knowledge.

## Goals

- prevent branch and commit confusion;
- prevent duplicate or contradictory proposals;
- separate candidate memory from canonical project facts;
- preserve a compact, reviewable handoff;
- connect decisions and plans to implementation evidence.

## Inputs

Required when available:

- repository;
- branch;
- commit;
- user objective;
- current milestone;
- relevant project files;
- relevant Notion Project Ledger entries;
- related PR, issue, run, artifact, evaluation, or audit evidence.

## Authority Order

1. GitHub for code and version-control facts.
2. AgentOps MIS SQLite/API for execution and audit facts.
3. Notion MIS Project Ledger plus `docs/project/` for reviewed project state.
4. Conversation history only for source context.

Never use one source to make a claim owned by another source.

## Workflow

### 1. PREFLIGHT

Read in order:

1. `docs/project/PROJECT_STATE.md`
2. `docs/project/DECISIONS.md`
3. `docs/project/BACKLOG.md`
4. `docs/project/HANDOFF.md`
5. `AGENTS.md`
6. `PROJECT_SPEC.md`
7. `AGENT_WORKFLOW.md`
8. `BASE_INDEX.md`
9. task-specific specs and current code

Verify exact repository, branch, and commit. Output:

```text
Repository:
Branch:
Commit:
Milestone:
Objective:
Relevant decisions:
Active P0/P1:
Risks / unknowns:
```

If Git context cannot be verified, mark the value `Unknown` and stop code-level assumptions.

### 2. RETRIEVE AND DEDUPLICATE

Search canonical project files and the Notion ledger for the core nouns and intended outcome.

For each possible durable item, classify the relationship:

```text
duplicate_of
updates
supersedes
conflicts_with
new
```

- `duplicate_of`: do not create a new record unless it adds evidence; update the existing item instead.
- `updates`: preserve the existing item and append the new evidence or scope.
- `supersedes`: mark the old item `Superseded` and link both directions.
- `conflicts_with`: do not promote either item to canonical until a decision resolves the conflict.
- `new`: create only when the item is materially distinct.

### 3. CLASSIFY

Choose exactly one durable type:

```text
Decision
Proposal
Requirement
Task
Risk
Evidence
Question
Handoff
```

Default model-generated content to `Inbox` or `Proposed`.

Canonical eligibility:

- `Approved`: explicitly accepted by an authorized human.
- `Implemented`: acceptance evidence exists on the named branch and commit.
- `Canonical = true`: allowed only for `Approved` or `Implemented`.

### 4. EXECUTE WITH EVIDENCE

Before meaningful repository or runtime changes:

- create and verify an Agent Plan;
- preserve workspace and scope boundaries;
- require explicit approval for high-impact actions;
- retain links among plan, task, run, tool/prepared action, approval, artifact, evaluation, and audit;
- record failures instead of hiding them.

### 5. EMIT PROJECT DELTA

Use this schema:

```yaml
type: Decision | Proposal | Requirement | Task | Risk | Evidence | Question | Handoff
title: concise durable title
status: Inbox | Proposed | Approved | In Progress | Implemented | Rejected | Superseded | Blocked
priority: P0 | P1 | P2 | P3
module: project module
canonical: false
summary: what changed relative to existing state
source: stable URL or evidence ID
repository: owner/repo
branch: exact branch or Unknown
commit: exact SHA or Unknown
duplicate_of: null
updates: null
supersedes: null
conflicts_with: null
owner: responsible actor
next_action: one concrete next step
```

Do not paste the complete answer into `summary`.

When nothing durable changed, output:

```text
No canonical project-state change.
```

### 6. UPDATE VERSIONED STATE

Update only the files whose facts changed:

- `PROJECT_STATE.md`: current verified facts and milestone.
- `DECISIONS.md`: accepted decisions and consequences.
- `BACKLOG.md`: priority, status, acceptance evidence, dependencies.
- `HANDOFF.md`: latest branch/commit, verification, open risks, next action.

A newer discussion is not enough reason to rewrite priority. State the evidence and displaced work whenever priority changes.

### 7. HANDOFF

End with:

```text
Branch:
Commit:
Changed:
Not changed:
Verification:
Open risks:
Next action:
Project Delta:
```

A new agent should be able to continue from the handoff without reading the full conversation.

## Notion Targets

- Control Center: `https://app.notion.com/p/3866adfdd920816096a0ef9bd4a58801`
- Project Ledger: `https://app.notion.com/p/24467ea0d1764e40957cdcc1ca55db53`

Use the ledger views appropriate to the work: `Inbox`, `Proposed Review`, `Approved Canon`, `Decisions`, `P0`, `Risks`, `Tasks`, and `Handoffs`.

## Safety and Privacy

Do not store:

- credentials or tokens;
- raw private or customer transcripts;
- raw prompts or model responses by default;
- unredacted customer data;
- generated databases, indexes, caches, or runtime logs;
- unsupported claims stated as current facts.

Prefer stable IDs, hashes, redacted summaries, evidence links, and reviewed conclusions.
