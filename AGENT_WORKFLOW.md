# Agent Workflow

Every agent must follow this protocol before and during execution:

READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD

## Required Steps

1. READ
   Read `PROJECT_SPEC.md`, this workflow, `BASE_INDEX.md`, relevant docs, and task acceptance criteria.

2. PLAN
   Submit an `agent_plan` before meaningful file or runtime changes.
   Run `agentops agent-plan verify --plan-id <id>` before execution when a plan ID is available.
   After execution, bind the plan to evidence with `agentops plan-evidence create --plan-id <id> --run-id <id> --mismatch-policy block`.

3. RETRIEVE
   Search approved project knowledge, runbooks, base notes, and memory candidates through `/api/knowledge/search` or `agentops knowledge search`.

4. COMPARE
   Compare the proposed work with base constraints, runtime boundaries, security rules, and existing product decisions.

5. EXECUTE
   Work through Agent Gateway CLI/API where possible. Browser UI is for human supervision, not normal agent execution.

6. VERIFY
   Run the smallest useful smoke or build check for the touched surface. Record failures as evidence instead of hiding them.

7. RECORD
   Record run/tool/evaluation/audit/artifact evidence and propose memory candidates only when the lesson should survive.

## Evidence Per Phase

- READ: cite specs and docs in `referenced_specs`.
- PLAN: submit `agentops agent-plan create`.
- RETRIEVE: cite knowledge paths and memory IDs.
- COMPARE: cite base IDs and risk decisions.
- EXECUTE: record tool calls and runtime events.
- VERIFY: submit evaluations or smoke artifacts.
- RECORD: write audit/artifact evidence, verify a `plan_evidence_manifest`, and propose reviewable memory candidates.

## Clean Repo Rule

Do not commit generated plans, FTS index data, temporary databases, raw runtime logs, raw prompts, raw responses, tokens, or cache directories.

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
- External uploads, connector credential changes, public publishing, destructive file operations, and live Hermes/OpenClaw runs require explicit confirmation or an existing approved policy.
- Customer-facing delivery approval requires a verified `plan_evidence_manifest`; unresolved manifest mismatches must block delivery.
- Memory candidates are not authority until reviewed.
