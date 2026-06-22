# AgentOps MIS Prioritized Backlog

> Status date: 2026-06-22
> Development line: `codex/agent-gateway-kb-demo`
> Current release status: `READY_TO_MERGE`
> Exact release SHA source: `git rev-parse HEAD` plus strict release scripts.

## Status Vocabulary

```text
Next | Verify Current Head | Ready | In Progress | Blocked | Done | Keep Green | Superseded
```

## P0 — Release and Authority Correctness

| ID | Work item | Status | Acceptance evidence |
|---|---|---|---|
| P0-00 | Re-audit the exact latest development head | Done | `docs/V1_5_MERGE_READINESS_CHECKLIST.md` is `READY_TO_MERGE`; strict gates read the current `git rev-parse HEAD` at runtime |
| P0-01 | Separate Agent Plan authoring from approval | Keep Green | Guarded by `scripts/agent_plan_integrity_smoke.py` and `scripts/approval_semantics_boundary_smoke.py` |
| P0-02 | Hard-bind a verified immutable Agent Plan to Run and Delivery | Keep Green | Guarded by `scripts/run_start_plan_gate_smoke.py`, `scripts/operator_evidence_report_smoke.py`, and release checklist plan-evidence gates |
| P0-03 | Validate plan reference provenance and visibility | Keep Green | Guarded by `scripts/agent_plan_integrity_smoke.py`, `scripts/knowledge_scope_policy_smoke.py`, and `scripts/agent_gateway_knowledge_scope_smoke.py` |
| P0-04 | Close Prepared Action approval and exact resume | Keep Green | Guarded by prepared-action and external connector/runtime inventory smokes listed in `docs/V1_5_AGENT_GATEWAY_HARDENING_OBJECTIVE.md` |
| P0-05 | Unify redaction and shared-deployment authentication guards | Keep Green | Guarded by redaction, secret scan, doctor, and shared-mode local-write guard smokes |
| P0-06 | Replace approximate collaborator and workspace visibility checks | Keep Green | Guarded by workspace isolation and scoped reviewable-list smokes |
| P0-07 | Add Knowledge workspace/ACL isolation and retrieval provenance | Keep Green | Guarded by knowledge scope, retrieval quality, and search policy smokes |
| P0-08 | Establish SQLite concurrency baseline | Keep Green | Guarded by `scripts/sqlite_pragmas_smoke.py` and `scripts/sqlite_concurrency_smoke.py` |
| P0-09 | Establish CI, secret scan, SBOM, license, and release evidence | Keep Green | Required PR checks `Backend deterministic smokes` and `UI build` must be green on the exact current HEAD; strict release evidence gates remain required after any new commit |
| P0-10 | Install durable project governance in repository and Notion | Done | `AGENTS.md`, project state/decision/backlog/handoff files, Project Ledger views, repo-local skill, and governance PR #6 exist |
| P0-11 | Install the prepared ChatGPT Project Instructions | Blocked | Project owner pastes the versioned template into ChatGPT Project Instructions and confirms a new project chat follows it |

## P1 — Productization After P0

| ID | Work item | Status | Acceptance evidence |
|---|---|---|---|
| P1-01 | Aider-style repository map and task localization | Done | `GET /api/commander/repo-map`, `agentops commander repo-map`, `operator loop-launch-packet`, Commander work-package `commander_repo_map_localization` artifacts, and CI-backed `commander_repo_map` / `commander_work_package_plan` / `commander_work_package_dispatch` release commands provide deterministic file/symbol candidates, task-bound localization artifacts, dispatch-time restoration, provenance, redaction, and merge-gate evidence |
| P1-02 | Local Coding Project Template | Done | `GET /api/commander/coding-project-template`, `agentops commander coding-template`, `tpl_local_coding_project`, `agentops commander coding-workspace`, `agentops commander coding-evidence`, `scripts/commander_coding_project_template_smoke.py`, `scripts/commander_coding_workspace_smoke.py`, and `scripts/local_coding_project_template_smoke.py` now expose the WorkPackage/worktree/patch/tests/verifier/merge-gate contract, create Commander packages with repo-map localization artifacts, execute an isolated worktree loop, write summary/hash-only coding evidence back to MIS, and clean branch/worktree residue |
| P1-03 | Command Center BFF | Ready | One stable operator read model for projects, blocked runs, approvals, deliveries, stale workers, and next actions |
| P1-04 | Runtime Capability Manifest | Ready | Each adapter declares file, shell, network, Git, secret, external-write, confirmation, and trust capabilities |
| P1-05 | Split oversized horizontal modules | Ready after P0 | Strangler-style module boundaries; no big-bang rewrite; existing contracts preserved and tested |
| P1-06 | Knowledge chunking, retrieval evaluation, Repo Map, then hybrid search | Ready after P0 | FTS baseline measured first; chunking/Repo Map improves named retrieval cases; vectors remain optional |

## P2 — Differentiation

- Research Lab Template and experiment/evidence workflow.
- GPU, server, dataset, model, experiment, and paper objects.
- JiuwenSwarm, LangGraph, CrewAI, and other runtime adapters.
- Agent/Skill/Template marketplace, hiring, evaluation, and billing.
- SaaS, BYOC, private deployment, and enterprise audit.

## Priority Change Rule

A new idea does not change priority merely because it is newly discussed. Any priority change must name:

1. the decision or evidence that changed;
2. the item it displaces;
3. the consequence of delaying the displaced item;
4. the owner who approved the change.

## Completion Rule

A backlog item is `Done` only when acceptance evidence exists on the exact relevant branch and commit. A `Keep Green` item is implemented but remains a release invariant: any new commit must keep its guard scripts and required CI checks passing.
