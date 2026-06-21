# AgentOps MIS Current Handoff

> Handoff date: 2026-06-21  
> Repository: `geogejoy107-jpg/agentops-mis-mvp`  
> Development line: `codex/agent-gateway-kb-demo`  
> Latest development head observed at governance start: `6305b2533f7219ecdeb1fc3763e1196a25a38272`  
> Governance branch: `ops/project-governance-ledger`  
> Governance PR: pending creation

## Read First

1. `docs/project/PROJECT_STATE.md`
2. `docs/project/DECISIONS.md`
3. `docs/project/BACKLOG.md`
4. this handoff
5. `PROJECT_SPEC.md`
6. `AGENT_WORKFLOW.md`
7. `BASE_INDEX.md`
8. Draft audit PR `#5`

Then verify the current GitHub branch and commit. Do not rely on the values in this file if the branch has advanced.

## What This Workstream Is Doing

The project previously relied too heavily on conversation memory and scattered documents. This workstream installs a durable, reviewable project-governance layer:

- a Notion Control Center;
- a structured Notion Project Ledger;
- accepted decisions and candidate-memory rules;
- versioned project state, backlog, decision log, and handoff;
- root repository instructions;
- a repo-local Project Ledger skill;
- a ready-to-paste ChatGPT Project Instructions template.

## What Has Been Completed Outside GitHub

- Created `MIS Project Control Center｜项目操作台` under the existing MIS Knowledge Hub.
- Created `MIS Project Ledger｜项目账本`.
- Added Status Board, Inbox, Proposed Review, Approved Canon, Decisions, P0, Risks, Tasks, and Handoffs views.
- Seeded accepted decisions, current risks, audit evidence, the governance task, the manual ChatGPT-instruction task, and a baseline handoff.
- Registered the SOP in the existing Notion `Docs｜项目文档库`.

Notion links:

- Control Center: https://app.notion.com/p/3866adfdd920816096a0ef9bd4a58801
- Project Ledger: https://app.notion.com/p/24467ea0d1764e40957cdcc1ca55db53

## Current Code-Line Facts

- The last full static audit froze `8d1827e00629bdca4779794121ca4a31dfa3f1e1`.
- The development line continued after that audit.
- The latest head observed at the start of this governance branch was `6305b2533f7219ecdeb1fc3763e1196a25a38272`, which adds the customer local-deployment backup runbook and tooling.
- Therefore, the historical blocker list must be reconciled against the current head before implementation begins.

## Current Decision

Do not start another horizontal feature line. Finish governance, re-verify current HEAD, then close the first unresolved correctness gate: Agent Plan approval-role separation and verified Plan-to-Run binding.

## Manual Dependency

The available integrations can write to Notion and GitHub, but cannot edit ChatGPT Project Instructions. The project owner must paste `docs/project/CHATGPT_PROJECT_INSTRUCTIONS.md` into the Project settings.

## Next Single Action

Open the governance PR against `codex/agent-gateway-kb-demo`, verify its exact head and base, update this handoff with the PR and commit, then run a documentation consistency check before requesting review.

## Project Delta

```yaml
type: Handoff
title: Durable project governance installed for AgentOps MIS
status: In Progress
priority: P0
module: Project Governance
repository: geogejoy107-jpg/agentops-mis-mvp
branch: ops/project-governance-ledger
commit: pending final governance head
source: Notion Control Center and governance PR
supersedes: ad-hoc conversation-only continuity
next_action: create and verify the governance PR
```
