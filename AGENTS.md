# AgentOps MIS Repository Instructions

These rules apply to every human or AI agent working in this repository.

## 1. Authority Order

Use the following sources for different kinds of truth:

1. **GitHub repository, branch, commit, PR, and test output** for code facts.
2. **AgentOps MIS SQLite/API ledger** for runs, tool calls, approvals, artifacts, evaluations, memory review, and audit facts.
3. **Notion MIS Project Ledger** for approved project decisions, risks, requirements, handoffs, and candidate project deltas.
4. **Chat history** only as source material. It is not a canonical project database.

When sources conflict, stop and reconcile them instead of silently choosing the most convenient one.

## 2. Mandatory Preflight

Before analysis, planning, coding, architecture work, or priority changes, state and verify:

```text
repository:
branch:
commit:
current milestone:
current objective:
relevant approved decisions:
open P0/P1 items:
known risks / unknowns:
```

If branch or commit cannot be verified, write `Unknown` and do not infer current implementation from memory.

## 3. Required Reading Order

Read these files before meaningful work:

1. `docs/project/PROJECT_STATE.md`
2. `docs/project/DECISIONS.md`
3. `docs/project/BACKLOG.md`
4. `docs/project/HANDOFF.md`
5. `PROJECT_SPEC.md`
6. `AGENT_WORKFLOW.md`
7. `BASE_INDEX.md`
8. task-specific specs, code, tests, and audit evidence

Search the existing implementation before adding a parallel path.

## 4. Project Delta Rule

Do not preserve entire answers as project memory. Record only the change relative to existing project state.

Classify each durable item as one of:

```text
Decision | Proposal | Requirement | Task | Risk | Evidence | Question | Handoff
```

Before creating a new item, check whether it:

```text
duplicates | updates | supersedes | conflicts_with
```

New ideas start as `Inbox` or `Proposed`. Only human-reviewed `Approved` or verified `Implemented` items may change canonical project state.

## 5. Execution Rules

- Create and verify an Agent Plan before meaningful changes.
- Manage slow live runtimes, CI, browser builds, and subagent work as asynchronous lanes. Do not sit idle waiting for Hermes/OpenClaw/CI/subagents unless their result is on the immediate critical path; while a lane is running, continue non-overlapping implementation, verification, docs/spec updates, or another independent lane.
- Do not let an Agent self-approve its own high-risk plan.
- Keep plan, run, tool, approval, artifact, evaluation, and audit evidence linked.
- Preserve workspace, scope, redaction, confirm-run, and external-write boundaries.
- Never use a status change as a substitute for real execution evidence.
- For AgentOps MIS product-readiness, dogfood, demo, or customer-usefulness claims, use real Hermes/OpenClaw execution whenever the local runtimes are available and explicitly authorized. Mock adapter evidence is CI/offline fallback only, must be labeled as such, and must never be presented as product-level completion.
- Do not commit secrets, raw private transcripts, raw prompts/responses, temporary databases, generated indexes, runtime logs, or caches.

## 6. Verification and Handoff

Run the smallest useful check for the touched surface. Record failures honestly.

At the end of substantive work:

1. update project state only when facts changed;
2. update decisions only for accepted decisions;
3. update backlog status and acceptance evidence;
4. write a concise handoff with exact branch and commit;
5. emit a Project Delta, or explicitly state `No canonical project-state change`.

Detailed operating rules live in `docs/project/PROJECT_OPERATING_RULES.md` and the repo-local skill at `.agents/skills/project-ledger/SKILL.md`.
