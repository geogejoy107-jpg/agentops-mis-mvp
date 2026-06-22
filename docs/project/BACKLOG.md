# AgentOps MIS Prioritized Backlog

> Status date: 2026-06-22  
> Development line: `codex/agent-gateway-kb-demo`  
> Latest verified development head for this update: `9fc10a67694013c277a30847d72917c6845016c5`

## Status Vocabulary

```text
Next | Verify Current Head | Ready | In Progress | Blocked | Done | Superseded
```

## P0 — Release and Authority Correctness

| ID | Work item | Status | Acceptance evidence |
|---|---|---|---|
| P0-00 | Re-audit the exact latest development head | Next | Current branch/commit stated; each historical blocker marked open, partially resolved, or closed with file/test evidence |
| P0-01 | Separate Agent Plan authoring from approval | Verify Current Head | Agent may create only draft/submitted plans; only human/admin path can approve/reject; audit records actor and transition |
| P0-02 | Hard-bind a verified immutable Agent Plan to Run and Delivery | Verify Current Head | `plan_id`, version/hash, verification and approval checked at run start; delivery proves plan/run/tool/eval/artifact consistency |
| P0-03 | Validate plan reference provenance and visibility | Verify Current Head | Referenced specs, files, memories, bases, and decisions exist and are visible in the same workspace/project scope |
| P0-04 | Close Prepared Action approval and exact resume | Verify Current Head | Approval is bound to one action hash and checkpoint; approve resumes once; reject blocks; retries do not duplicate side effects |
| P0-05 | Unify redaction and shared-deployment authentication guards | Verify Current Head | Server, worker, and CLI use one redaction contract; non-local production mode fails closed without configured authentication |
| P0-06 | Replace approximate collaborator and workspace visibility checks | Verify Current Head | Exact relationship or structured membership checks; negative cross-workspace tests pass |
| P0-07 | Add Knowledge workspace/ACL isolation and retrieval provenance | Verify Current Head | Search filters by workspace/project/access tags; result carries source, version/hash, authority class, and visibility proof |
| P0-08 | Establish SQLite concurrency baseline | Verify Current Head | Central connection factory uses foreign keys, WAL, busy timeout, short transactions; concurrent benchmark reports lock/error rates |
| P0-09 | Establish CI, secret scan, SBOM, license, and release evidence | Verify Current Head | PR head receives automated checks; safe smoke/build commands pass; Gitleaks/SBOM/license/provenance evidence attached |
| P0-10 | Install durable project governance in repository and Notion | In Progress | `AGENTS.md`, project state/decision/backlog/handoff files, Project Ledger views, repo-local skill, and governance PRs exist |
| P0-11 | Install the prepared ChatGPT Project Instructions | Blocked | Project owner pastes the versioned template into ChatGPT Project Instructions and confirms a new project chat follows it |

## P1 — Productization After P0

| ID | Work item | Status | Acceptance evidence |
|---|---|---|---|
| P1-01 | Aider-style repository map and task localization | Ready after P0 | Relevant symbols/files selected within token budget with source provenance and reproducible ranking |
| P1-02 | Local Coding Project Template | Ready after P0 | WorkPackage, worktree/branch workspace, localization artifact, patch, tests, verifier, and merge gate linked in MIS |
| P1-03 | Command Center BFF | Ready after P0 | One stable operator read model for projects, blocked runs, approvals, deliveries, stale workers, and next actions |
| P1-04 | Runtime Capability Manifest | Ready after P0 | Each adapter declares file, shell, network, Git, secret, external-write, confirmation, and trust capabilities |
| P1-05 | Split oversized horizontal modules | Ready after P0 | Strangler-style module boundaries; no big-bang rewrite; existing contracts preserved and tested |
| P1-06 | Knowledge chunking, retrieval evaluation, Repo Map, then hybrid search | Ready after P0 | FTS baseline measured first; chunking/Repo Map improves named retrieval cases; vectors remain optional |
| P1-07 | Governed External Base Manager and Notion Project Ledger integration | In Progress (v0 contract only) | Notion registry/policy and Project Ledger governance fields exist; versioned manifest, knowledge entry, validator, runbook, and Draft PR #19 exist; live connector ingestion/writeback remains separately planned and approval-gated |

P1-07 does not displace any P0 item. Runtime ingestion, writeback, polling/webhooks, and bidirectional synchronization remain blocked behind the current authority, ACL, approval-resume, redaction, and CI correctness gates.

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

A backlog item is `Done` only when acceptance evidence exists on the exact relevant branch and commit. Documentation that an older revision once passed is not completion evidence for a newer head.
