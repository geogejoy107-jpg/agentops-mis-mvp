# Project Operating Rules

> Version: 1.0  
> Effective date: 2026-06-21  
> Repository: `geogejoy107-jpg/agentops-mis-mvp`

## Purpose

The project needs continuity across long conversations, multiple agents, changing branches, and external knowledge tools. Memory is useful for recall, but it is not sufficient for project governance. This document defines the durable workflow used to decide what is current, what is only proposed, and what must happen next.

## Authority Map

| Information | Canonical source |
|---|---|
| Code, branch, commit, PR, tests, workflow checks | GitHub |
| Run, tool call, approval, artifact, evaluation, memory review, audit | AgentOps MIS SQLite/API ledger |
| Approved project decisions, requirements, risks, backlog, handoff | Notion MIS Project Ledger plus versioned files under `docs/project/` |
| Raw discussion history and brainstorming | ChatGPT Project conversations |
| Candidate ideas and unreviewed lessons | Ledger `Inbox` / `Proposed` |

A source is authoritative only for the information it owns. Notion cannot prove which code was executed. GitHub cannot prove which external tool action was approved. Chat history cannot silently override an approved decision.

## Canonical Status Model

```text
Inbox -> Proposed -> Approved -> In Progress -> Implemented
```

Side states:

```text
Rejected | Superseded | Blocked
```

Rules:

- `Inbox`: captured but not reviewed.
- `Proposed`: coherent proposal awaiting an explicit decision.
- `Approved`: accepted project direction, but not proof of implementation.
- `In Progress`: approved work is actively being executed.
- `Implemented`: acceptance evidence exists.
- `Rejected`: considered and declined.
- `Superseded`: replaced by a newer item; preserve the history and link the successor.
- `Blocked`: cannot progress without a named dependency or permission.
- Only `Approved` and `Implemented` items may be marked canonical.
- An Agent may propose project memory but may not make its own high-risk proposal canonical.

## Project Delta

A Project Delta is the durable change produced by one discussion or work cycle. It is not a transcript or a copy of the final answer.

Allowed types:

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

Minimum fields:

```yaml
type:
title:
status:
priority:
module:
summary:
source:
repository:
branch:
commit:
duplicate_of:
supersedes:
conflicts_with:
owner:
next_action:
```

Before creating an item, search the ledger and versioned project files. Choose one relationship:

- `duplicate_of`: no new durable information; update the existing item or do nothing.
- `updates`: adds evidence or scope without replacing the existing decision.
- `supersedes`: the new item replaces an older proposal or decision.
- `conflicts_with`: the conflict must be resolved before either item becomes canonical.

If a substantive exchange produces no durable change, record:

```text
No canonical project-state change.
```

## Start-of-Work Preflight

Before coding, architecture, prioritization, or project planning:

1. Read `PROJECT_STATE.md`.
2. Read accepted entries in `DECISIONS.md`.
3. Read active P0/P1 work in `BACKLOG.md`.
4. Read the latest `HANDOFF.md`.
5. Verify repository, branch, and exact commit from GitHub.
6. Read `PROJECT_SPEC.md`, `AGENT_WORKFLOW.md`, `BASE_INDEX.md`, and task-specific specs.
7. Search the implementation before proposing a new subsystem.
8. Identify any mismatch between project memory and current code.

Required preflight output:

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

If branch or commit is not verifiable, stop implementation work and mark it `Unknown`.

## Execution and Evidence

Every meaningful implementation should maintain this chain:

```text
Project Spec / Decision
-> Agent Plan
-> Task
-> Run
-> Tool Call / Prepared Action
-> Approval when required
-> Artifact
-> Evaluation
-> Audit
-> reviewed Memory Candidate
```

A status transition is not execution evidence. An implementation is complete only when its acceptance criteria and relevant verification have been recorded.

## End-of-Work Handoff

At the end of a substantive work cycle:

1. state the exact branch and commit;
2. summarize what changed and what did not;
3. list verification performed and failures still open;
4. update backlog status with evidence links;
5. update decisions only when a real decision was made;
6. update project state only when a current fact changed;
7. write the next single recommended action;
8. emit the Project Delta.

A handoff should let a new agent continue without rereading the entire conversation.

## Notion Ledger

- Control Center: https://app.notion.com/p/3866adfdd920816096a0ef9bd4a58801
- Project Ledger: https://app.notion.com/p/24467ea0d1764e40957cdcc1ca55db53

Recommended views:

- `Inbox`
- `Proposed Review`
- `Approved Canon`
- `Decisions`
- `P0`
- `Risks`
- `Tasks`
- `Handoffs`

## GitHub Workflow

- Use feature or hardening branches; do not write directly to `main` for project-governance or production changes.
- Open a PR with a precise base branch and acceptance criteria.
- Keep technical tasks and implementation evidence in GitHub Issues/PRs.
- Keep architectural reasoning and cross-cutting project decisions in the Project Ledger.
- Do not add Asana while Notion plus GitHub are sufficient; adding another task authority would create drift.

## Information That Must Not Be Stored

Do not commit or copy into the project ledger:

- credentials or tokens;
- raw private transcripts;
- raw customer content unless explicitly approved;
- raw model prompts or responses by default;
- generated databases, FTS indexes, caches, or runtime logs;
- unsupported claims presented as current implementation facts.

Store redacted summaries, stable IDs, hashes, evidence URLs, and approved conclusions instead.

## Review Cadence

- Per substantive conversation: capture and deduplicate the Project Delta.
- Per code cycle: update branch, commit, acceptance evidence, backlog, and handoff.
- Per milestone: reconcile Notion canon with `PROJECT_STATE.md`, `DECISIONS.md`, `BACKLOG.md`, and `HANDOFF.md`.
- Weekly: process Inbox, resolve conflicts, merge duplicates, and mark superseded items.
