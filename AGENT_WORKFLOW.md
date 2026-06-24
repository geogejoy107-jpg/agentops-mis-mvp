# Agent Workflow

Every agent must follow this protocol before and during execution:

READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD

## Project Preflight

Before code, architecture, project planning, or priority changes:

1. Read `docs/project/PROJECT_STATE.md`.
2. Read `docs/project/DECISIONS.md`.
3. Read `docs/project/BACKLOG.md`.
4. Read `docs/project/HANDOFF.md`.
5. Verify the exact GitHub repository, branch, and commit.
6. Read `AGENTS.md`, `PROJECT_SPEC.md`, this workflow, `BASE_INDEX.md`, relevant docs, and task acceptance criteria.
7. Search the existing implementation and project ledger before proposing a parallel path.
8. If using an external runtime, framework, UI reference, retrieval system, policy engine, or CI/security tool, read `docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md` and state which authority boundary remains first-party MIS code.

Required preflight output:

```text
Repository:
Branch:
Commit:
Current milestone:
Current objective:
Relevant approved decisions:
Open P0/P1 items:
Risks / unknowns:
```

If branch or commit cannot be verified, mark it `Unknown` and do not infer current implementation from conversation memory.

## Required Steps

1. READ
   Read the project-governance files, `PROJECT_SPEC.md`, this workflow, `BASE_INDEX.md`, relevant docs, current code, and task acceptance criteria.

2. PLAN
   Submit an `agent_plan` before meaningful file or runtime changes.
   Run `agentops agent-plan verify --plan-id <id>` before execution when a plan ID is available.
   After execution, bind the plan to evidence with `agentops plan-evidence create --plan-id <id> --run-id <id> --mismatch-policy block`.
   Normal AgentOps worker loops now do this automatically for pulled tasks; manual runs must still create the plan and manifest explicitly.

3. RETRIEVE
   Search approved project knowledge, runbooks, base notes, reviewed memory, and relevant Project Ledger entries through `/api/knowledge/search`, `agentops knowledge search`, or the approved project sources.
   A retrieved candidate memory is not authority merely because it was found.

4. COMPARE
   Compare the proposed work with approved decisions, active backlog, base constraints, runtime boundaries, security rules, and current implementation.
   Classify any durable new item as `duplicate_of`, `updates`, `supersedes`, `conflicts_with`, or genuinely new.
   If borrowing from open source, classify the borrowing as direct tool adoption, reference-only method adaptation, or forbidden authority transfer.

5. EXECUTE
   Work through Agent Gateway CLI/API where possible. Browser UI is for human supervision, not normal agent execution.

6. VERIFY
   Run the smallest useful smoke or build check for the touched surface. Record failures as evidence instead of hiding them.

7. RECORD
   Record run/tool/evaluation/audit/artifact evidence and propose memory candidates only when the lesson should survive.
   Emit a Project Delta rather than copying the entire answer or transcript.
   Update `PROJECT_STATE`, `DECISIONS`, `BACKLOG`, and `HANDOFF` only when their facts changed.

## Evidence Per Phase

- READ: cite specs, approved decisions, branch, commit, and relevant docs in `referenced_specs` or equivalent evidence.
- PLAN: submit `agentops agent-plan create`.
- RETRIEVE: cite knowledge paths, decision IDs, ledger IDs, and reviewed memory IDs.
- COMPARE: cite base IDs, existing implementation, duplicate/conflict relationships, and risk decisions.
- EXECUTE: record tool calls and runtime events.
- VERIFY: submit evaluations or smoke artifacts against the exact relevant branch and commit.
- RECORD: write audit/artifact evidence, verify a `plan_evidence_manifest`, emit the Project Delta, and propose reviewable memory candidates.

## Project Delta

Choose exactly one durable type:

```text
Decision | Proposal | Requirement | Task | Risk | Evidence | Question | Handoff
```

New ideas default to `Inbox` or `Proposed`. Only human-reviewed `Approved` or evidence-backed `Implemented` items may become canonical.

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
updates:
supersedes:
conflicts_with:
owner:
next_action:
```

If nothing durable changed, record:

```text
No canonical project-state change.
```

## Clean Repo Rule

Do not commit generated plans, FTS index data, temporary databases, raw runtime logs, raw prompts, raw responses, tokens, cache directories, or unreviewed customer/private content.

## Open-Source Adoption Rule

Open-source projects may support tools, protocols, retrieval, CI, scanning,
SBOM, Git isolation, UI reference, or adapter work. They must not become the
source of truth for MIS objects or approvals. Before integrating a new external
project, record:

```text
Reference:
Borrowed idea:
First-party MIS module touched:
Authority boundary preserved:
Verification:
```

If the dependency would own workspace, task, run, approval, prepared action,
memory, evaluation, artifact, audit, delivery, or identity state, reject it or
wrap it as a runtime/connector adapter.

## Required Agent Plan Fields

- `task_understanding`
- `referenced_specs`
- `referenced_memories`
- `referenced_bases`
- `proposed_files_to_change`
- `risk_level`
- `approval_required`
- `execution_steps`
- `verification_plan`
- `rollback_plan`

## Approval Rules

- High or critical risk plans require approval.
- An Agent must not approve its own high-risk plan or promote its own candidate memory to authority.
- External uploads, connector credential changes, public publishing, destructive file operations, and live Hermes/OpenClaw runs require explicit confirmation or an existing approved policy.
- Customer-facing delivery approval requires a verified `plan_evidence_manifest`; the customer-worker workflow must create or reuse a verified manifest before generating the delivery approval.
- Memory candidates are not authority until reviewed.

## Handoff Rule

At the end of substantive work, state the exact branch and commit, what changed, verification performed, open risks, and the next single action. The latest handoff must allow a new agent to continue without rereading the full conversation.
