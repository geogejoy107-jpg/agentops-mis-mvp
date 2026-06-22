# AgentOps MIS Current Handoff

> Handoff date: 2026-06-22
> Repository: `geogejoy107-jpg/agentops-mis-mvp`
> Development line: `codex/agent-gateway-kb-demo`
> Project-governance integration commit: `5f1706c3afed22156e0bb3dc06ca351f698713d9`
> Current observed HEAD: `1217ab612bf560db9c9bacaeee915285be3e8a43`
> Current release status: `READY_TO_MERGE`
> Governance PR: `#6` merged
> Audit PR: `#5` remains the last full audit package; its P0 findings are incorporated into v1.5 release gates.

Always verify the exact current development HEAD from GitHub before implementation. The integration commit is a stable point showing where governance entered the development line.

## Read First

1. `docs/project/PROJECT_STATE.md`
2. `docs/project/DECISIONS.md`
3. `docs/project/BACKLOG.md`
4. this handoff
5. `AGENTS.md`
6. `PROJECT_SPEC.md`
7. `AGENT_WORKFLOW.md`
8. `BASE_INDEX.md`
9. audit PR `#5`

Then verify repository, branch, commit, and current CI. Do not rely on conversation memory or stale values in a document if the branch has advanced.

## Completed

The project now has a durable, reviewable governance and release-hardening layer:

- Notion `MIS Project Control Center`;
- Notion `MIS Project Ledger` with review and operational views;
- accepted decisions and candidate-memory rules;
- versioned project state, backlog, decision log, operating rules, and handoff;
- root `AGENTS.md` repository instructions;
- extended `AGENT_WORKFLOW.md` with Git preflight, deduplication, Project Delta, and handoff rules;
- repo-local `.agents/skills/project-ledger/SKILL.md`;
- ready-to-paste `docs/project/CHATGPT_PROJECT_INSTRUCTIONS.md`.
- v1.5 hardening objective that maps audit PR #5 findings to P0 gates;
- merge-readiness checklist currently marked `READY_TO_MERGE`;
- required GitHub checks for backend deterministic smokes and UI build.

## Notion Assets

- Control Center: https://app.notion.com/p/3866adfdd920816096a0ef9bd4a58801
- Project Ledger: https://app.notion.com/p/24467ea0d1764e40957cdcc1ca55db53
- Docs SOP entry is registered in the existing `Docs｜项目文档库`.

The ledger contains accepted decisions, current risks, audit evidence, tasks, and a baseline handoff. It includes Status Board, Inbox, Proposed Review, Approved Canon, Decisions, P0, Risks, Tasks, and Handoffs views.

## Code-Line Facts

- Last full static audit baseline: `8d1827e00629bdca4779794121ca4a31dfa3f1e1`.
- Post-audit development includes customer local-deployment backup/restore, Commander Work Package Planner work, Agent Plan hard gating, prepared-action Approval Wall coverage, redaction/auth hardening, workspace/knowledge visibility gates, SQLite reliability gates, release evidence gates, and loop-launch contract UI/readback work.
- Governance was merged into `codex/agent-gateway-kb-demo` at `5f1706c3afed22156e0bb3dc06ca351f698713d9`.
- Historical P0 findings are reconciled through `docs/V1_5_AGENT_GATEWAY_HARDENING_OBJECTIVE.md` and `docs/V1_5_MERGE_READINESS_CHECKLIST.md`; treat them as keep-green release gates after every new commit.
- Current PR #1 at `1217ab6` has green `Backend deterministic smokes` and `UI build` checks.

## Current Decision

Do not start another horizontal feature line on this release branch unless it is release-hardening, evidence, rollback, docs, or a required fix. Keep the exact-head release gates green and merge through the reviewed PR while `READY_TO_MERGE` remains true.

## Remaining Manual Dependency

The current connectors cannot edit ChatGPT Project Instructions. The project owner must paste `docs/project/CHATGPT_PROJECT_INSTRUCTIONS.md` into the ChatGPT Project settings and run the included installation check.

## Verification Performed

- Confirmed the ten intended governance files were present in PR `#6`.
- Confirmed the PR targeted `codex/agent-gateway-kb-demo`.
- Confirmed GitHub reported the PR mergeable before merge.
- Squash-merged PR `#6`; resulting development integration commit is `5f1706c3afed22156e0bb3dc06ca351f698713d9`.
- Confirmed the Notion Control Center, Project Ledger, views, seed entries, and Docs SOP exist.
- Current PR #1 head `1217ab6` has green required checks: `Backend deterministic smokes` and `UI build`.

## Next Single Action

After any new commit, re-run strict exact-head release gates and keep the PR in `READY_TO_MERGE`. The remaining manual dependency is still to paste `docs/project/CHATGPT_PROJECT_INSTRUCTIONS.md` into ChatGPT Project settings.

## Project Delta

```yaml
type: Handoff
title: Durable project governance and v1.5 hardening gates are merge-ready
status: ReadyToMerge
priority: P0
module: Project Governance
repository: geogejoy107-jpg/agentops-mis-mvp
branch: codex/agent-gateway-kb-demo
commit: 1217ab612bf560db9c9bacaeee915285be3e8a43
source: Notion Control Center, merged GitHub PR #6, audit PR #5 findings, and PR #1 release-readiness checks
supersedes: ad-hoc conversation-only continuity
next_action: keep strict release gates green after any new commit; merge through reviewed PR while READY_TO_MERGE remains true
```
