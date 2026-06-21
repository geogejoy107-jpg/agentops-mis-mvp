# AgentOps MIS Current Project State

> Status date: 2026-06-21  
> Repository: `geogejoy107-jpg/agentops-mis-mvp`  
> Development line: `codex/agent-gateway-kb-demo`  
> Latest observed development commit: `9d47f0e1bcdc3da9f9b8e37733b4ae12c96507cf`  
> Last full audit baseline: `8d1827e00629bdca4779794121ca4a31dfa3f1e1`  
> Governance branch: `ops/project-governance-ledger`  
> Audit PR: `#5`

## Product Position

AgentOps MIS is a local-first control plane for supervising a small AI workforce across runtimes. Humans create goals, supervise, approve, review delivery, and curate memory. Agents use CLI/API and future MCP paths to pull tasks, execute work, and write structured evidence back to MIS.

It is not an LLM runtime or an agent builder. It governs runtimes such as Codex, Hermes, OpenClaw, LangGraph, CrewAI, Dify, and future adapters.

## Authority Chain

```text
Project Spec / Approved Decision
-> Knowledge Retrieval
-> Agent Plan
-> Task
-> Run
-> Tool Call / Prepared Action
-> Approval
-> Artifact
-> Evaluation
-> Memory Candidate
-> Audit
```

- GitHub is authoritative for code, branch, commit, PR, and test facts.
- AgentOps MIS SQLite/API is authoritative for execution and audit facts.
- Notion MIS Project Ledger and the versioned project files are authoritative for approved project state and decisions.
- Chat history is source material, not canonical state.

## Verified Capability Baseline

The full audit at `8d1827e` verified a credible local-first control-plane candidate with:

- scoped Agent Gateway enrollment and sessions;
- task pull/claim and run/tool/artifact/evaluation/audit writeback;
- installable `agentops` and `agentops-worker` CLIs;
- Mock, Hermes, and OpenClaw adapters;
- commander, review queue, delivery board, and evidence-ledger flows;
- Agent Work Method Block v0;
- Markdown plus SQLite FTS5 Knowledge Index v0;
- Agent Plan API/CLI and verification v0.

The development line advanced after that audit. Observed post-audit work includes customer local-deployment and SQLite backup/restore tooling, followed by the Commander Work Package Planner at `9d47f0e1`. These later commits have not yet received the same complete audit as `8d1827e`; historical blocker status must not be assumed resolved.

## Current Deployment Truth

Appropriate now: loopback local use, course demonstration, controlled dogfood, and single-customer validation with explicit confirmation.

Not yet approved as a canonical claim: shared production deployment, multi-tenant SaaS, unattended high-impact actions, or enterprise-grade multi-workspace ACL.

## Current Milestone

```text
establish durable project governance
-> re-verify latest development HEAD
-> close execution and permission correctness gaps
-> establish CI, security, concurrency, and performance gates
-> produce a clean v1.5 release candidate
-> merge through a reviewed PR
```

Horizontal feature expansion remains secondary until this sequence is complete.

## P0 Items Requiring Current-HEAD Verification

The last full audit found these areas. Each must be checked against the latest development commit before changing code:

1. Agent Plan approval roles and self-approval prevention.
2. Immutable Plan hash and verified Plan hard-binding to Run and Delivery.
3. Reference provenance and existence checks during Plan verification.
4. Prepared Action, action hash, checkpoint, exact resume, idempotency, and execute-once behavior.
5. Runtime-internal tool visibility and per-action governance.
6. Unified server, worker, and CLI redaction.
7. Fail-closed shared-deployment authentication guards.
8. Exact collaborator and workspace visibility checks.
9. Knowledge workspace/ACL isolation and retrieval provenance.
10. SQLite WAL, busy timeout, short transactions, and concurrency baseline.
11. Automated CI status, secret scanning, SBOM, license, and provenance.

## Project Governance Added in This Workstream

- Notion `MIS Project Control Center`.
- Notion `MIS Project Ledger` with dedicated review and status views.
- Root `AGENTS.md` repository instructions.
- Versioned `PROJECT_STATE`, `DECISIONS`, `BACKLOG`, `HANDOFF`, and operating rules.
- Repo-local `.agents/skills/project-ledger/SKILL.md`.
- Ready-to-paste ChatGPT Project Instructions template.

## Known Unknowns

- The development branch can continue moving while governance work is in review.
- Historical smoke records are not a substitute for checks on the exact PR head.
- ChatGPT Project Instructions cannot be edited through the available connector.
- Automatic capture must remain candidate-only until deduplication and approval are enforced.

## Next Single Recommended Action

After this governance PR is ready, re-audit the exact latest development head, reconcile the P0 list with changes after `8d1827e`, and implement the first unresolved correctness gate: approval-role separation plus verified Plan-to-Run hard binding.
