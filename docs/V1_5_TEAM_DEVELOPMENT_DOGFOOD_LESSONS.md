# AgentOps MIS v1.5 Team Development Dogfood Lessons

## Purpose

This document translates the way AgentOps MIS is being built with one Codex
commander and multiple parallel Codex worker threads into product requirements
for AgentOps MIS itself.

The lesson is simple: the development workflow already behaves like the product
we are trying to sell. A human commander decomposes work, assigns scoped lanes to
AI workers, reviews returned evidence, controls integration risk, and captures
stable operating memory. AgentOps MIS should make that pattern visible,
repeatable, auditable, and safe for customers managing their own AI teams.

## Dogfood Workflow Observed

The current team workflow used these roles:

- Commander thread: owns product coherence, branch sequencing, merge judgment,
  safety checks, and final reporting.
- Subagent / worker threads: own bounded work packages such as local-first ops,
  RBAC hardening, remote worker deploy, worker fleet console, customer task flow,
  product docs, QA, research, or architecture.
- Human operator: approves live runtime use, resolves scope conflicts, chooses
  product direction, and accepts final artifacts.

The workflow used these controls:

- A branch plan defined ownership lanes, avoid-edit lists, merge order, shared
  verification commands, and handoff prompts.
- A commander runbook defined the integration contract, branch return checklist,
  review steps, merge acceptance, and non-goals.
- Workers returned summaries with branch name, changed files, behavior changes,
  verification evidence, known limits, and scope deviations.
- Live Hermes/OpenClaw execution required explicit confirmation and readiness
  checks.
- Evidence mattered more than narrative claims: commits, diffs, smoke output,
  run IDs, artifact IDs, audit rows, evaluations, and approval states were used
  to decide readiness.
- Private content stayed outside committed artifacts: no credentials, raw
  prompts, private transcripts, local databases, runtime logs, or generated
  service files.

This is the customer story AgentOps MIS should support: a manager should be able
to run a small AI delivery team with the same discipline, without reconstructing
the operating model from markdown files and chat memory.

## What We Learned

### 1. Task Decomposition Is The Product

The most important artifact was not a task list; it was a structured split of
the project into lanes with explicit ownership, allowed files, avoided files,
acceptance criteria, and merge order. Without that decomposition, parallel AI
work becomes fast but unsafe.

Product requirement:

- MIS tasks must support work packages, not only flat todos.
- A work package needs goal, owner agent, branch/workspace, allowed write scope,
  avoid scope, dependencies, verification commands, delivery artifact contract,
  and return checklist.
- The product should distinguish "planned", "claimed", "in progress",
  "ready for review", "blocked", "needs integration", "merged", and "delivered"
  states.

### 2. Branch Ownership Is A Safety Boundary

Branches were used as isolated execution surfaces. The commander could let
workers move quickly because each worker had a lane and the integration thread
checked scope before merge.

Product requirement:

- MIS should track branch or workspace ownership as a first-class primitive.
- Each task/run should record branch name, base branch, changed paths, intended
  write scope, and out-of-scope touches.
- Integration should include a branch scope gate before merge or delivery.

### 3. Agent Assignment Needs Capability And Trust Context

Different threads were suited to different jobs: implementation, QA, docs,
security hardening, research, architecture, runtime adapter checks. The operator
also had to distinguish safe mock execution from live Hermes/OpenClaw execution.

Product requirement:

- Agents need capability profiles, runtime type, trust status, current health,
  scopes, and live-execution policy.
- Task assignment should match work package requirements to agent capabilities.
- Live runtime assignment must require readiness and explicit confirm gates.

### 4. The Evidence Ledger Is The Shared Reality

The commander could not safely integrate branches based on prose alone. Useful
handoffs included concrete evidence: changed files, command results, run IDs,
tool calls, evaluations, artifacts, approvals, and known limitations.

Product requirement:

- MIS must treat evidence as the system of record.
- Every worker run should write run, tool-call, evaluation, audit, artifact, and
  approval evidence where applicable.
- Product screens should make missing evidence obvious before a work package can
  advance.

### 5. Async Workers Need A Commander Queue

Parallel AI work does not finish at the same time. A useful commander should not
wait for every worker before moving the project forward. Faster workers should
enter review or merge immediately; slower workers should keep running; late
results should land in a commander inbox where they can be reviewed, merged,
reassigned, or superseded.

Product requirement:

- MIS should model worker runs as asynchronous lanes with independent state,
  priority, due time, stale timeout, and evidence completeness.
- The commander dashboard should support partial progress: "ready for review",
  "merge now", "waiting on slower lane", "superseded", "needs rebase", and
  "blocked by approval".
- Late worker output should not overwrite integrated work automatically. It
  should enter an integration inbox with provenance, changed scope, conflicts,
  and recommended next action.
- The product should let the commander continue dispatching and reviewing other
  work while long Hermes/OpenClaw jobs continue in the background.

### 6. Readiness Gates Prevent Confident Breakage

The commander runbook required targeted smoke tests, secret scans, UI builds,
adapter readiness checks, and live-runtime confirmation when needed. These gates
prevented a worker from shipping a plausible but unsafe result.

Product requirement:

- Readiness gates should be attached to work packages and integration stages.
- Gates should support required commands, policy checks, review checklists,
  runtime readiness, trust status, and human approval.
- Gate status should block "ready to merge" and "ready to deliver" when required
  evidence is missing or failed.

### 7. Approval Checkpoints Are Part Of Execution

Human approval was not only a final sign-off. It appeared before live runtime
use, before merges, before delivery acceptance, and before memory capture.

Product requirement:

- Approvals should be explicit records with requested action, risk reason,
  reviewer, decision, timestamp, and resulting side effects.
- Product flows should support pre-run approval, merge approval, delivery
  approval, and memory approval.

### 8. Artifact Delivery Needs A Customer View

Workers may produce code, docs, reports, smoke evidence, screenshots, or
customer summaries. The commander needs a compact delivery view, while customers
need a cleaned report that excludes internal prompts and private transcripts.

Product requirement:

- MIS should separate internal evidence from customer-facing delivery artifacts.
- Delivery reports should summarize result, scope, evidence, risks, approvals,
  and next actions.
- Artifacts should record provenance back to task, run, agent, branch, and gate
  status.

### 9. Memory Capture Must Be Curated

Dogfood created reusable operating lessons: branch ownership rules, live runtime
confirm gates, no raw transcripts, return checklists, and scoped workers. These
are valuable product memory, but only after review.

Product requirement:

- Memory should be proposed by workers but approved by humans.
- Memory candidates should record source task/run, proposed lesson, category,
  scope, and sensitivity review.
- Memory capture must exclude credentials, raw prompts, private transcripts, and
  raw model responses.

## Mapping To MIS Product Primitives

| Dogfood practice | MIS primitive | Product requirement |
| --- | --- | --- |
| Commander creates branch plan | Team project board | Show lanes, owners, dependencies, branch state, gate state, and delivery state. |
| Subagent gets bounded prompt | Agent work package | Package goal, scope, allowed files, avoid files, acceptance criteria, and return checklist. |
| Worker uses own branch/thread | Branch ownership | Record owner agent, base branch, current branch, changed paths, and scope deviations. |
| Worker returns verification | Evidence ledger | Attach run, tool calls, tests, artifacts, evaluations, audit events, and limitations. |
| Commander reviews before merge | Readiness gate | Block integration until required checks and evidence pass. |
| Human confirms live runtime | Approval checkpoint | Require explicit confirmation for Hermes/OpenClaw or other high-risk adapters. |
| Worker delivers summary/report | Artifact delivery | Produce internal and customer-facing reports with provenance. |
| Stable lessons become rules | Memory capture | Propose, review, and approve reusable operating memory. |

## Current Product Support

AgentOps MIS already supports much of the lower-level execution fabric needed
for this workflow:

- Agent Gateway APIs for agents to register, pull, claim, run, write tool calls,
  submit evaluations, emit audit events, record artifacts, request approvals,
  and propose memory.
- Repo-local worker loop with `mock`, `hermes`, and `openclaw` adapters.
- Worker daemon start/stop/status controls and local runtime state.
- Scoped worker enrollment tokens, session refresh, heartbeat, revocation, and
  scope enforcement.
- Redaction policy for token-like and sensitive values.
- Explicit `confirm_run` requirement for Hermes/OpenClaw live execution.
- Runtime connector trust states such as trusted, review required, and blocked.
- Customer worker task workflow with async job status and project report
  artifact paths.
- Evidence surfaces for runs, tool calls, evaluations, audit logs, artifacts,
  approvals, and memory candidates.
- Documentation patterns for commander runbooks, branch plans, acceptance
  evidence, and safety boundaries.

## Missing For Customer-Managed AI Teams

The missing product layer is the team-management experience above individual
worker runs:

- No first-class team project board that shows multiple AI workers, work
  packages, branches, dependencies, and integration readiness in one place.
- No work package object that combines task, branch scope, agent assignment,
  prompt-safe instructions, verification requirements, and return checklist.
- No commander dashboard that summarizes worker progress, blocked lanes,
  evidence completeness, merge risk, and next human decisions.
- No merge/integration gate that ties branch diff scope, tests, approvals,
  artifact delivery, and safety scans into one decision.
- No complete branch/run provenance chain from project -> work package -> branch
  -> commit/diff -> run -> evidence -> artifact -> approval.
- No human approval review center optimized for live runtime approval, merge
  approval, delivery approval, and memory approval across a whole AI team.
- No productized memory capture workflow that turns dogfood lessons into
  approved reusable team operating rules.
- No customer-facing distinction between internal agent evidence and polished
  delivery reports across a multi-agent project.

## v1.5 / v1.6 Product Backlog

### v1.5: Team Project Board

Goal:

- Give the commander and customer one place to see the AI team.

Requirements:

- Show project lanes by work package, owner agent, branch, status, dependencies,
  and gate state.
- Highlight blocked work, stale worker heartbeat, failed checks, and unreviewed
  approvals.
- Link each lane to its task, latest run, artifacts, evaluations, audit events,
  memory candidates, and delivery report.
- Keep the board local-first and compatible with current Agent Gateway data.

Acceptance:

- A customer can understand which agents are working, what they own, what is
  ready for review, and what is blocked without reading chat transcripts.

### v1.5: Agent Work Packages

Goal:

- Turn branch handoff prompts into structured product objects.

Requirements:

- Add fields for goal, owner agent, branch, base branch, allowed files, avoided
  files, dependencies, acceptance criteria, verification commands, delivery
  expectations, and safety notes.
- Generate a worker-safe brief that excludes credentials, raw prompts, and
  private transcripts.
- Require workers to return changed files, behavior changed, verification
  evidence, limitations, and scope deviations.

Acceptance:

- A worker can claim a package and return enough structured evidence for a
  commander to review without reconstructing context from conversation history.

### v1.5: Commander Dashboard

Goal:

- Make the human commander role explicit in the product.

Requirements:

- Summarize active agents, claimed work packages, branch state, failing gates,
  pending approvals, stale workers, and artifacts awaiting delivery review.
- Provide next recommended commander actions.
- Preserve separation between human supervision in UI and agent execution
  through CLI/API/MCP.

Acceptance:

- A commander can run a daily project review from AgentOps MIS instead of a
  manually maintained markdown runbook.

### v1.5: Async Integration Inbox

Goal:

- Let the commander keep moving while workers finish at different speeds.

Requirements:

- Show returned worker results as reviewable inbox items with task, agent,
  branch/scope, run evidence, artifact, gate status, and conflict/superseded
  indicators.
- Allow fast lanes to move into review or merge while slower lanes remain
  running.
- Mark late results as "needs review", "needs rebase", "superseded", or
  "merge candidate" instead of auto-applying them.
- Surface stuck, stale, or long-running workers without blocking unrelated
  packages.
- Preserve all decisions in the audit ledger: accepted, rejected, superseded,
  reopened, reassigned, or deferred.

Acceptance:

- A commander can integrate one completed worker result, keep two workers
  running, and later review their returned artifacts without losing provenance
  or overwriting already accepted work.

### v1.5: Merge / Integration Gate

Goal:

- Prevent unsafe integration of AI worker output.

Requirements:

- Attach gate rules to each package or integration stage.
- Support diff scope check, secret scan, required smoke commands, UI build
  status, adapter readiness, approval completion, and delivery artifact presence.
- Record pass/fail evidence and reviewer decisions in the ledger.
- Block "ready to merge" when required checks fail or evidence is missing.

Acceptance:

- A commander can see why a branch is or is not merge-ready, with links to the
  exact evidence.

### v1.6: Branch / Run Provenance

Goal:

- Build a complete chain of custody for AI work.

Requirements:

- Link project, work package, branch, base branch, commits, changed files, runs,
  tool calls, evaluations, audit events, artifacts, approvals, and memory.
- Show provenance on both internal review pages and customer delivery reports.
- Preserve hashes/summaries for sensitive execution details instead of raw
  prompts or private transcripts.

Acceptance:

- A customer can answer "who or what changed this, why, under which approval,
  with what evidence, and where was it delivered?"

### v1.6: Human Approval Review

Goal:

- Manage approval checkpoints across the whole AI team.

Requirements:

- Provide a review queue for live runtime approval, merge approval, delivery
  approval, and memory approval.
- Show risk reason, affected agent, task, branch, adapter, evidence summary,
  requested action, and side effects.
- Require explicit decisions for high-risk operations.

Acceptance:

- A human can approve or reject AI team actions without scanning multiple task
  pages or chat threads.

### v1.6: Product Memory Capture

Goal:

- Convert repeated operating lessons into reviewed team memory.

Requirements:

- Propose memory from runs, failures, approvals, and delivery retrospectives.
- Classify memory as product decision, operating rule, safety rule, customer
  preference, technical pattern, or known limitation.
- Require sensitivity review before memory is committed.
- Make approved memory available to future work package generation.

Acceptance:

- The system improves future team coordination without importing raw private
  transcripts or unreviewed agent reasoning.

## Safety Rules

These rules should become product-enforced defaults, not only documentation:

- Do not store or deliver credentials, API keys, bearer tokens, `.env` values,
  local database contents, raw prompts, raw model responses, private messages,
  private transcripts, or full chat logs.
- Store summaries, hashes, status, counts, durations, references, and approved
  artifacts instead of raw sensitive material.
- Live Hermes/OpenClaw or equivalent runtime execution must require readiness,
  trusted connector state, scoped worker identity, and explicit `confirm_run`.
- Workers must operate with scoped tokens and bounded permissions.
- Workers should have explicit write scope and avoid scope; scope deviations
  must be reported and reviewed.
- Human approvals are required for high-risk runtime actions, merge/integration,
  customer delivery, and durable memory capture.
- Browser UI is the human control surface; agent execution should happen through
  Agent Gateway CLI/API/MCP so evidence can be recorded consistently.
- Customer-facing artifacts must be scrubbed of internal prompts, private
  transcripts, credentials, and local runtime details.

## Product Thesis

AgentOps MIS is not only an observability dashboard for agents. The dogfood
workflow shows a stronger product thesis: AgentOps MIS is a management
information system for AI teams.

The winning product primitive is not "chat with an agent"; it is "manage a team
of agents as accountable workers." That means decomposed work, scoped ownership,
assigned agents, evidence-led review, approval checkpoints, integration gates,
artifact delivery, and curated memory. v1.5 proves the execution ledger and
worker loop. v1.6 should make the commander layer product-native.
