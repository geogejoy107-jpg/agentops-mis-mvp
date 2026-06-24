# AgentOps MIS UI / UX Specification v2

> Status: implementation specification  
> Intended implementer: Gemini working in the existing React/Vite application  
> Base branch: `codex/agent-gateway-kb-demo`  
> Related research: `docs/design/UI_BENCHMARK_RESEARCH_2026.md`  
> Constraint: redesign and decomposition must not weaken the current local-first governance/hardening work

## 0. Executive summary

The current UI has reached the point where visual cleanup alone will not solve the problem. The product now contains several distinct operator systems inside one shell, especially inside `AIEmployees.tsx`.

UI v2 reorganizes AgentOps MIS around four operator domains:

1. **Operate** — goals, work packages, tasks, reviews and deliveries.
2. **Workforce** — agents, workers, runtimes and gateway access.
3. **Observe** — runs, traces, tool calls, evaluations and incidents.
4. **Govern** — approvals, policies, knowledge/memory, integrations and audit.

Pixel Office remains a fifth optional visualization mode, not a competing authority surface.

The first implementation milestone is not a full rewrite. It is a controlled strangler migration:

- Create a coherent design system and shell.
- Build new high-value pages beside existing pages.
- Reuse current APIs and types.
- Split the mega-page by domain.
- Preserve legacy routes until parity is proven.

## 1. Product definition

### 1.1 Product statement

AgentOps MIS is a local-first control plane for supervising a small AI workforce across multiple runtimes. It connects company goals and human decisions to plans, tasks, executions, approvals, artifacts, evaluations, memory and audit evidence.

### 1.2 Core product promise

A human operator can see what AI workers are doing, understand why, control risky actions, review outputs and recover from failures without reading raw logs or trusting an opaque chat session.

### 1.3 Long-term extensibility

The information architecture must later accommodate:

- One-person company templates.
- Research laboratory and deep-learning experiment workflows.
- GPU/server/experiment resources.
- Multi-agent swarm orchestration.
- Industry templates such as EDR/security operations.
- Agent and workflow marketplace.
- Usage billing and commercial SaaS/private deployment.

These are roadmap extensions, not P0 UI requirements.

## 2. Users and roles

### 2.1 Owner / Founder

Needs:

- Understand current company/project status.
- Delegate a goal to AI workers.
- Review important decisions and deliveries.
- Know cost, risk and quality without operating every runtime.

Primary surfaces:

- Mission Control
- Work Packages
- Review Queue
- Deliveries
- Reports

### 2.2 Operator / Project Manager

Needs:

- Plan work packages and assign agents.
- Track blockers, queues and dependencies.
- Inspect runs and request rework.
- Manage workers and runtime readiness.

Primary surfaces:

- Work Packages
- Task Queue
- Workforce
- Run Explorer
- Integrations

### 2.3 Approver / Security Reviewer

Needs:

- See the exact proposed action.
- Understand policy, risk and affected resources.
- Approve one revision/scope without approving unrelated future actions.
- Maintain separation of duties and audit evidence.

Primary surfaces:

- Security Approvals
- Gateway & Access
- Tool Calls
- Audit

### 2.4 Quality Reviewer

Needs:

- Compare output with acceptance criteria.
- Inspect artifacts and evaluator results.
- Approve delivery or request changes.

Primary surfaces:

- Human Review Queue
- Evaluations
- Run Explorer
- Deliveries

### 2.5 Agent / Worker (API or CLI user)

Needs:

- Pull authorized work.
- Retrieve permitted knowledge.
- Submit plan, run, tool, artifact and evaluation evidence.
- Receive approval/resume status.

The browser UI is not the agent’s primary interface, but all agent-side actions must be visible to humans.

## 3. Jobs to be done

The design must optimize these workflows:

1. “Tell me what needs my attention now.”
2. “Create a work package from a business goal and verify the plan before dispatch.”
3. “See which agents/workers can execute this work safely.”
4. “Approve or reject one prepared action with sufficient evidence.”
5. “Review an output against acceptance criteria and request changes.”
6. “Investigate why a run failed or became stuck.”
7. “Find which knowledge influenced a plan or output.”
8. “Confirm that a customer delivery is complete and safe to share.”
9. “Understand who changed access, trust or policy and when.”
10. “Open Pixel Office to see the organization at a glance, then jump to formal records.”

## 4. Information architecture

## 4.1 Primary navigation

Use four primary groups plus a visual mode.

### Operate

- Mission Control
- Work Packages
- Tasks
- Human Review
- Deliveries

### Workforce

- Agents
- Worker Fleet
- Runtimes
- Agent Gateway

### Observe

- Runs & Traces
- Evaluations
- Tool Calls
- Incidents

### Govern

- Security Approvals
- Knowledge & Memory
- Policies & Access
- Integrations
- Templates
- Audit

### Visualize

- Pixel Office

## 4.2 Navigation behavior

Desktop:

- 240 px collapsible side navigation.
- Workspace/environment switcher at top.
- Group headers with optional collapse.
- Active item uses background + left indicator, not color alone.
- Badge counts only for actionable queues: approvals, review, incidents.

Tablet:

- 72 px icon rail with expandable flyout.

Mobile:

- Bottom navigation with four destinations: Home, Work, Review, More.
- Deep admin tables remain usable via responsive list/card mode.

## 4.3 Proposed route structure

New canonical routes:

```text
/workspace                         Mission Control
/work                              Work Package list
/work/:workPackageId               Work Package detail
/tasks                             Task queue
/tasks/:taskId                     Task detail
/review                            Human Review Queue
/deliveries                        Delivery board
/deliveries/:projectId             Customer delivery/report

/workforce/agents                  Agent Directory
/workforce/agents/:agentId         Agent detail
/workforce/workers                 Worker Fleet
/workforce/runtimes                Runtime directory
/workforce/gateway                 Gateway & sessions

/observe/runs                      Run Explorer
/observe/runs/:runId               Run detail
/observe/evaluations               Evaluation Lab
/observe/tool-calls                Tool Call Ledger
/observe/incidents                 Incident queue

/govern/approvals                  Security Approvals
/govern/knowledge                  Knowledge & Memory
/govern/access                     Policies & Access
/govern/integrations               Integrations
/govern/templates                  Template Studio
/govern/audit                      Audit Explorer

/pixel-office                      Pixel Office
```

Legacy routes remain as redirects/aliases until migration is complete.

## 4.4 Old-to-new module mapping

| Current route/page | v2 destination | Migration action |
|---|---|---|
| `/workspace` / WorkspaceHome | Mission Control | Replace composition, preserve APIs |
| `/workspace/tasks` / MyTasks | Task Queue | Add views, filters, project context |
| `/workspace/agents` / AIEmployees | Split across Agents, Workers, Gateway, Review, Deliveries | Strangler decomposition |
| `/workspace/approvals` | Security Approvals | Evidence-centered redesign |
| `/workspace/memory` | Knowledge & Memory | Switch to live APIs and retrieval workflow |
| `/workspace/reports` | Deliveries / Reports | Stakeholder-safe presentation |
| `/admin` / ControlTower | Mission Control + Observability | Remove duplicate KPI wall |
| `/admin/runs` | Run Explorer | Add trace/evidence model |
| `/admin/evaluations` | Evaluation Lab | Replace mock data |
| `/admin/toolcalls` | Tool Call Ledger | Add detail/evidence/policy |
| `/admin/connectors` | Runtimes + Integrations | Separate execution adapter from external integration |
| `/admin/templates` | Template Studio | Discover/install/export model |
| `/admin/audit` | Audit Explorer | Replace mock data, add search and integrity detail |

## 5. Object and state model for UI

The UI must not invent a second data model. It creates view models over current API objects.

### 5.1 Core objects

- Workspace
- Goal / Work Package
- Agent Plan
- Task
- Agent
- Worker
- Runtime / Adapter
- Run
- Span / Tool Call
- Prepared Action
- Approval
- Artifact
- Evaluation
- Memory / Knowledge Source
- Delivery
- Audit Event

### 5.2 Required relationship breadcrumbs

Every detail page must show its parents:

```text
Workspace → Work Package → Task → Run → Tool Call / Artifact / Evaluation
```

Security decisions additionally show:

```text
Plan revision → Prepared Action → Approval → Resume / Block result
```

Knowledge items show:

```text
Source → Document / Memory → Retrieval event → Agent Plan / Run
```

### 5.3 State separation

Never collapse these into one label:

- **Work state**: draft, planned, ready, active, blocked, complete.
- **Execution state**: queued, claimed, running, waiting, failed, succeeded.
- **Security state**: not required, pending, approved, rejected, expired.
- **Quality state**: not evaluated, pass, fail, needs review.
- **Delivery state**: internal, review-ready, customer-ready, delivered.

## 6. Global application shell

## 6.1 Layout

```text
┌──────────────────────────────────────────────────────────────┐
│ Context bar: workspace · environment · search · health · user│
├──────────────┬───────────────────────────────────────────────┤
│ Side nav     │ Page header                                   │
│              │ Optional view/filter bar                      │
│              │ Main content                                  │
│              │                                               │
└──────────────┴───────────────────────────────────────────────┘
```

## 6.2 Context bar

Left:

- Workspace selector.
- Environment badge: Local / Demo / Remote.
- Data freshness timestamp.

Center:

- Global search / command palette trigger.
- Search domains: work package, task, agent, run, artifact, memory.

Right:

- Backend/API health.
- Worker capacity.
- Pending approval count.
- Incident count.
- Theme/locale.
- User/role menu.

## 6.3 Command palette

Shortcut: `⌘K` / `Ctrl+K`.

Commands:

- Navigate to page/object.
- Create work package/task.
- Search all records.
- Refresh current view.
- Open pending approvals.
- Open Pixel Office.
- Switch workspace/environment/theme/locale.

Destructive or privileged actions are not directly executed from the command palette; it may open their reviewed flow.

## 6.4 Page header contract

Every page header supports:

- Eyebrow/breadcrumb.
- Human-readable title.
- One-line purpose/status.
- Optional status badges.
- One primary action.
- At most two secondary actions.
- Tabs or view selector below header where needed.

## 7. Visual design system

## 7.1 Art direction

Name: **Operational Calm**.

Characteristics:

- Neutral, high-clarity surfaces.
- Strong typographic hierarchy.
- Limited semantic color.
- Thin borders instead of heavy shadows.
- Dense operational data without tiny text.
- Subtle motion for state changes.
- Pixel art is contained to the visualization mode and selected identity moments.

## 7.2 Typography

Recommended:

- UI: Inter or Geist.
- Monospace: Geist Mono or JetBrains Mono.
- Chinese fallback: `PingFang SC`, `Microsoft YaHei`, system sans.

Scale:

| Token | Size / line-height | Use |
|---|---:|---|
| Display | 28 / 36 | rare workspace heading |
| H1 | 22 / 30 | page title |
| H2 | 18 / 26 | section title |
| H3 | 15 / 22 | panel title |
| Body | 14 / 21 | primary content |
| Small | 12 / 18 | metadata/helper |
| Micro | 11 / 16 | IDs, timestamps, compact labels only |

Do not use 10 px for primary content or actionable labels.

## 7.3 Spacing

Base unit: 4 px.

Primary rhythm:

- 4: icon/text micro gap.
- 8: control internal gap.
- 12: compact row/panel gap.
- 16: standard panel padding.
- 24: section separation.
- 32: page-level separation.

## 7.4 Radius and elevation

- Controls: 6–8 px.
- Cards/panels: 10–12 px.
- Modal/drawer: 12–16 px.
- Default surfaces use 1 px border, no shadow.
- Floating overlays use a restrained shadow and clear focus trap.

## 7.5 Color tokens

Replace page-specific inline colors with semantic tokens.

### Foundation

```css
--bg-canvas
--bg-surface
--bg-subtle
--bg-elevated
--border-default
--border-muted
--text-primary
--text-secondary
--text-muted
--text-inverse
--accent-primary
--accent-hover
--focus-ring
```

### Semantic

```css
--state-success
--state-warning
--state-danger
--state-info
--state-running
--state-waiting
--risk-low
--risk-medium
--risk-high
--risk-critical
```

Status must always include text/icon/shape, not color only.

### Theme direction

Light theme:

- Warm-neutral canvas, white surfaces, graphite text, indigo/blue accent.

Dark theme:

- Graphite/ink canvas, slightly lighter neutral surfaces, desaturated cyan/indigo accent.

Avoid saturated neon backgrounds and broad purple/cyan glow.

## 7.6 Motion

- 120–180 ms for hover/focus/selection.
- 180–240 ms for drawer/panel transitions.
- Live updates use a subtle highlight/fade, not bouncing animations.
- Respect `prefers-reduced-motion`.
- Pixel Office can have richer animation but must provide pause/reduced-motion controls.

## 7.7 Density modes

Provide comfortable and compact density for data-heavy views.

- Comfortable row: 44–48 px.
- Compact row: 34–38 px.
- Preserve 14 px primary text in both modes.

## 8. Shared component inventory

Gemini should build or normalize these components before deep page work:

### Shell and navigation

- `AppShellV2`
- `WorkspaceSwitcher`
- `EnvironmentBadge`
- `GlobalSearch`
- `CommandPalette`
- `PrimaryNav`
- `MobileNav`
- `HealthCluster`

### Page composition

- `PageHeader`
- `Breadcrumbs`
- `TabNav`
- `ViewSwitcher`
- `FilterBar`
- `SavedViewMenu`
- `SectionHeader`
- `SplitPane`
- `DetailDrawer`

### Data and evidence

- `DataTable`
- `ObjectListRow`
- `StatusPill`
- `RiskPill`
- `ActorBadge`
- `EvidenceCard`
- `RelationshipBreadcrumb`
- `TraceTree`
- `TraceWaterfall`
- `Timeline`
- `DiffViewer`
- `ArtifactPreview`
- `PolicyDecisionCard`
- `EvaluationScorecard`
- `ProvenancePanel`

### Feedback

- `Skeleton`
- `EmptyState`
- `ErrorState`
- `StaleDataBanner`
- `LiveUpdateIndicator`
- `Toast`
- `ConfirmDialog`
- `HighRiskDecisionPanel`

New surfaces should use Radix primitives + Tailwind/CSS tokens. Avoid mixing MUI components into the new design unless a current component cannot be replaced safely.

## 9. Screen specifications

## 9.1 Mission Control

### Purpose

Give the owner/operator a reliable answer to “what needs attention and what is moving?”

### Desktop composition

```text
Page header + New Work Package
Attention Queue (full width)
4 signal metrics
Active Work Packages (2/3) | Workforce Health (1/3)
Recent Activity / Incidents
Optional Pixel Office preview
```

### Attention Queue

Merged but clearly typed queue entries:

- Security approval
- Human quality review
- Failed/stuck run
- Offline/stale worker
- Unhealthy runtime
- Delivery blocker
- Memory candidate

Each row contains:

- Type icon and severity.
- Human-readable title.
- Related work package/task.
- Responsible agent/worker.
- Age/SLA.
- One primary action.

### Metrics

- Active work packages.
- Waiting for human.
- 24h run success rate.
- Healthy worker capacity.

Every metric links to a filtered view.

### Acceptance criteria

- No hard-coded date.
- No synthetic chart values.
- Empty/loading/error/stale states implemented.
- Page usable at 1280, 1024 and 768 px.
- Pending attention visible without scrolling on a 1440×900 screen.

## 9.2 Work Package list

### Views

- List (default).
- Board by lifecycle.
- Timeline/milestones.

### Row/card fields

- Name and objective.
- Customer/project tag.
- Commander/human owner.
- Assigned agent group.
- Lifecycle status.
- Execution health.
- Security/quality blockers.
- Progress and evidence completeness.
- Last update.

### Actions

- New Work Package.
- Open detail.
- Pause/resume if allowed.
- Duplicate as template.
- Archive.

Bulk privileged actions require confirmation and audit.

## 9.3 Work Package detail

### Header

- Title, objective, status.
- Human owner/Commander.
- Delivery target.
- Primary action based on state: Review Plan, Dispatch, Resume, Review Delivery.

### Tabs

1. Overview
2. Plan
3. Tasks
4. Runs & Evidence
5. Delivery
6. Activity

### Overview

- Outcome/acceptance criteria.
- Progress and blockers.
- Agent/worker assignments.
- Latest update.
- Evidence completeness.

### Plan

- Current Agent Plan content.
- Plan revision/hash.
- Referenced specs/knowledge.
- Risk and permission requirements.
- Change history.

### Runs & Evidence

- Related run list.
- Tool/approval summary.
- Artifacts.
- Evaluation status.

### Acceptance criteria

- Plan revision is always visible when dispatching or approving.
- Delivery cannot appear “ready” without artifact/evaluation evidence.
- Object relationships are deep-linkable.

## 9.4 Task Queue

### Views

- List.
- Kanban.
- Timeline.

### Filter dimensions

- Work package.
- Status.
- Priority.
- Agent.
- Worker/runtime.
- Approval state.
- Quality state.
- Updated time.

### List columns

- Task title.
- Work package.
- Status.
- Priority.
- Agent/worker.
- Current run.
- Approval/review indicator.
- Updated.

### Interaction

Clicking a row opens a right detail panel. “Open full page” enters task detail.

## 9.5 Task detail

Split layout:

Left/main:

- Brief and acceptance criteria.
- Plan context.
- Subtasks/dependencies.
- Artifacts and output.

Right/inspector:

- Current status.
- Assignment.
- Current/latest run.
- Approval and review state.
- Timeline.

Actions:

- Assign/reassign.
- Start/dispatch.
- Pause/cancel.
- Request review.
- Create follow-up task.

Actions appear only when allowed by current state and permissions.

## 9.6 Agent Directory

### Views

- Table (default for operations).
- Cards (visual/team view).

### Fields

- Agent identity/name/role.
- Status and current assignment.
- Default runtime/model.
- Allowed capability/tool summary.
- 7/30-day success rate.
- Evaluation trend.
- Cost/token trend where available.
- Memory scope.
- Trust/permission warnings.

### Agent detail tabs

- Overview
- Assignments
- Runs
- Evaluations
- Memory
- Permissions

### Acceptance criteria

- No gateway, worker daemon or Commander planner controls on the directory page.
- Agent status is derived from real MIS state.
- Cards do not imply an avatar is the agent’s security identity.

## 9.7 Worker Fleet

### Summary

- Ready workers.
- Busy workers.
- Stale/offline workers.
- Queue depth.
- Available capacity.

### Worker table

- Worker ID/host.
- Environment/version.
- Heartbeat.
- Current job.
- Capacity.
- Installed adapters.
- Health state.

### Detail drawer

- Telemetry timeline.
- Recent jobs.
- Logs preview.
- Adapter readiness.
- Safe controls: drain, restart, disable.

Restart/disable requires confirmation and audit.

## 9.8 Runtimes

Cards/list for Hermes, OpenClaw, Mock and future adapters.

Each runtime shows:

- Availability.
- Trust state.
- Real/dry-run capability.
- Health/probe.
- Version/config source.
- Worker coverage.
- Recent error.
- Allowed environments.

Trust changes open a policy decision panel explaining effect and scope.

External SaaS/data integrations belong in Integrations, not this page.

## 9.9 Agent Gateway & Access

### Tabs

- Overview
- Enrollment
- Scopes
- Tokens/Service Identities
- Sessions
- Policy History

### Overview

- Endpoint and readiness.
- Auth mode and fail-closed status.
- Active sessions.
- Enrollment mode.
- Redaction status.
- Security warnings.

### Enrollment

- Pending enrollments.
- Approved agents/workers.
- Allowed workspace and environment.
- Expiration/revocation.

### Scopes

- Scope name.
- Description.
- Objects/actions allowed.
- Risk classification.
- Agents/tokens using it.

## 9.10 Security Approvals

### Queue tabs

- Pending
- Approved
- Rejected
- Expired

### Queue row

- Action in plain language.
- Agent/runtime.
- Work package/task.
- Target resource.
- Risk.
- Age.
- Policy reason.

### Approval detail layout

```text
Context header
Prepared action / diff (main)
Risk & policy inspector (right)
Related plan/run/history
Sticky decision bar
```

Decision options:

- Approve this action/revision once.
- Approve for a bounded session if supported.
- Reject.
- Request changes / clarification.

A checkbox-only confirmation is not sufficient for high/critical risk.

### Required audit details

- Approver identity.
- Requested and decided timestamp.
- Exact plan/action hash.
- Decision reason/comment.
- Resulting resume/block event.

## 9.11 Human Review Queue

### Difference from approval

This queue judges output quality and delivery readiness, not permission to execute.

### Review detail

- Work objective and acceptance criteria.
- Artifact previews.
- Evaluator results.
- Run summary and relevant trace segments.
- Reviewer checklist/comments.

Actions:

- Accept.
- Request changes.
- Reject.
- Create follow-up task.

## 9.12 Run Explorer

### List view

Columns:

- Run.
- Task/work package.
- Agent/worker/runtime.
- Status.
- Duration.
- Tool count/high-risk count.
- Evaluation result.
- Cost/tokens where available.
- Start time.

Filters:

- Time.
- Status.
- Agent.
- Runtime.
- Work package.
- Evaluation.
- Risk/approval.
- Error type.

### Run detail tabs

1. Overview
2. Trace
3. Inputs / Outputs
4. Tool Calls
5. Artifacts
6. Evaluations
7. Audit
8. Raw

### Trace

- Hierarchical tree and aligned timeline/waterfall.
- Span status, start, duration, parent/child.
- Tool spans display risk/approval icon.
- Clicking a span opens inspector without losing trace position.

### Run comparison

Select two runs to compare:

- Inputs/context.
- Output/artifact.
- Trace path.
- Tool calls.
- Duration/cost/tokens.
- Evaluation score/rubric.

## 9.13 Evaluation Lab

### Data requirement

Use live evaluation API. Mock data is allowed only behind an explicit demo fixture flag.

### Views

- Overview trends.
- Evaluation result table.
- Failure analysis.
- Comparison/experiments later.

### Dimensions

- Evaluator/rubric.
- Agent.
- Runtime/model.
- Work package/task type.
- Time.

### Detail

- Named criteria and per-criterion score.
- Notes/evidence.
- Linked artifact/run.
- Reviewer/evaluator identity.
- Pass/fail threshold.

## 9.14 Tool Call Ledger

### List columns

- Tool/action.
- Agent/run.
- Target resource.
- Risk.
- Policy/approval.
- Status.
- Duration.
- Time.

### Detail drawer

- Human-readable action summary.
- Redacted arguments/result.
- Prepared action/diff.
- Policy decision.
- Approval chain.
- Error/retry.
- Parent trace.

Never expose secret values; show redaction tokens and secret references.

## 9.15 Knowledge & Memory

### Top-level tabs

- Search
- Sources
- Memory Review
- Retrieval Test

### Search

- Query input with keyboard focus.
- Filters: workspace, project, source type, memory type, status, access tag, freshness.
- Result includes title/excerpt, source, score, provenance, scope and freshness.

### Sources

- Markdown/project docs.
- Approved decisions.
- Runtime/base documentation.
- External bases.
- Ingestion/index health.

### Memory Review

Columns/cards:

- Candidate text/title.
- Type/scope.
- Source/provenance.
- Confidence.
- Created/freshness/TTL.
- Duplicate/contradiction warning.
- Review state.

Actions:

- Approve as canonical.
- Edit then approve.
- Reject.
- Mark stale/superseded.
- Merge duplicate.

### Retrieval Test

- Query.
- Retrieval strategy metadata.
- Ranked hits with scores/excerpts.
- ACL/provenance explanation.
- Optional preview of augmented context.

## 9.16 Integrations

Separate categories:

- Runtime adapters.
- Knowledge/data sources.
- Project/report destinations.
- Model providers.
- Developer tools.

Card fields:

- Name/category.
- Connected/health status.
- Data and permission scope.
- Local/cloud marker.
- Last sync/event.
- Configure/test/disable.

Installation/configuration uses a reviewed multi-step flow:

1. Select.
2. Explain access.
3. Configure secret reference.
4. Test connection.
5. Review scope.
6. Enable.

## 9.17 Template Studio

### Tabs

- Discover
- Installed
- Export & Bases

### Template card

- Name and intended team/company.
- Outcome.
- Included roles.
- Workflow count.
- Required runtimes/integrations.
- Version/license/author.
- Compatibility.

### Template detail

- Preview organization and workflow.
- Included policies.
- Knowledge/memory setup.
- Dashboards/reports.
- Local-only protected data.
- Install preview and changes.

## 9.18 Deliveries and customer report

### Delivery board

Columns/stages:

- In progress
- Internal review
- Customer-ready
- Delivered
- Changes requested

### Delivery detail/report

- Objective.
- Executive summary.
- Deliverables.
- Validation/evaluation evidence.
- Timeline/key decisions.
- Risks/open questions.
- Redaction profile.
- Export/share.

Operator-only evidence and customer-safe report must be visibly separated.

## 9.19 Audit Explorer

### Data requirement

Use live audit API, not mock data.

### Filters

- Time.
- Actor type/identity.
- Action.
- Entity type/id.
- Workspace/project.
- Risk/policy.
- Correlation/trace ID.

### Event row/detail

- Actor.
- Action in human language.
- Object.
- Timestamp.
- Correlation.
- Integrity/chain state.
- Redacted before/after or metadata.

Features:

- Search.
- Export with redaction.
- Chain/integrity status.
- Deep links to related objects.

## 9.20 Pixel Office

### Role

Optional spatial visualization of live MIS state.

### Requirements

- Typed scene adapter, not hard-coded business state.
- Agent avatar maps to stable agent ID.
- Rooms map to canonical routes.
- Status mapping documented.
- Clicking avatar/room opens details.
- Pause animation and reduced-motion mode.
- No sensitive content in labels/speech bubbles.
- Loading/error/offline mode.

### Integration points

- Mission Control preview card.
- Agent Directory “View in Office”.
- Full-screen Pixel Office route.

## 10. Responsive behavior

Breakpoints:

- ≥1440: full navigation, three-column dashboards where useful.
- 1024–1439: two-column, collapsible inspector.
- 768–1023: nav rail, table horizontal overflow or responsive row layout.
- <768: mobile stack, bottom nav, drawers instead of persistent side panels.

Rules:

- Important actions remain visible; secondary metadata collapses first.
- Tables offer a mobile list mode, not only horizontal scrolling.
- Trace detail can be desktop-first but must provide usable tree/log mode on tablet.
- Minimum interactive target 24×24 px; prefer 32–40 px in dense desktop UI and 44 px on touch.

## 11. Accessibility

Target: WCAG 2.2 AA.

Required:

- Full keyboard navigation.
- Visible focus indicator.
- Logical heading order.
- Semantic table/list/button markup.
- Labels for icon buttons.
- Non-color status cues.
- Sufficient text and non-text contrast.
- Reduced motion support.
- Focus trapping/restoration for dialogs/drawers.
- Screen-reader announcement for live state changes.
- Locale-aware dates/numbers.
- Avoid critical information in tooltips only.

## 12. Content and terminology

Preferred terms:

- Work Package, not generic “project” when referring to a Commander-dispatched unit.
- Agent for logical AI worker identity.
- Worker for executing process/host/daemon.
- Runtime for execution framework/provider.
- Security Approval for permission to act.
- Human Review for output quality.
- Artifact for concrete deliverable/evidence.
- Memory Candidate / Canonical Memory for governed memory state.

Copy style:

- Plain, concise and operational.
- Explain consequence before privileged action.
- Avoid anthropomorphic language in security or audit contexts.
- Bilingual strings use centralized copy keys.

## 13. Front-end architecture

## 13.1 Constraints

- Existing stack: React, Vite, TypeScript, Tailwind, Radix, Recharts, React Router.
- Reuse existing `liveApi.ts` contracts and types.
- No backend rewrite in UI PRs.
- No new cloud dependency.
- No shipping third-party art/assets without license review.

## 13.2 Recommended structure

```text
src/app/
  shell/
    AppShellV2.tsx
    navigation.ts
    CommandPalette.tsx
  design-system/
    tokens.css
    components/
  modules/
    mission-control/
    work/
    workforce/
    observe/
    govern/
    pixel-office/
  view-models/
    workPackageViewModel.ts
    runViewModel.ts
    approvalViewModel.ts
  data/
    liveApi.ts
    queryKeys.ts
  routes/
    routes.tsx
```

Do not create another 1,000+ line page. Suggested limits:

- Page composition file: ideally <300 lines.
- Feature component: ideally <250 lines.
- Pure view-model/transform logic outside JSX.

## 13.3 Data behavior

Every live page implements:

- Loading skeleton.
- Empty state.
- Error with retry.
- Stale/offline indicator.
- Manual refresh.
- Safe optimistic update only where rollback is clear.

No synthetic production metrics. If data is unavailable:

- Hide the metric, or
- Label it clearly as demo fixture.

## 13.4 Performance

Targets on a normal local development machine:

- Initial shell interactive: under 2.5 s on cold local load where practical.
- Route transition: under 250 ms for cached data.
- Large tables virtualized or paginated after 200 rows.
- Avoid polling every module independently; share refresh strategy.
- Lazy-load heavy trace, chart and Pixel Office bundles.
- No full-page rerender for small live updates.

## 13.5 Security UX

- Never display raw secrets.
- Distinguish secret reference from secret value.
- Privileged controls require current permissions and clear consequence.
- Approval UI binds decision to exact revision/action.
- Trust, token, session and policy changes have confirmation and audit result.
- Customer report defaults to redacted output.

## 14. Implementation sequence

### Phase 0 — Foundation

- Add tokens and normalized typography.
- Build AppShellV2, navigation and page header.
- Build shared status/risk/evidence/filter/table components.
- Add route aliases, feature flag and visual regression fixtures.

### Phase 1 — Operator core

- Mission Control.
- Work Package list/detail.
- Task Queue/detail.
- Security Approvals.
- Human Review.

### Phase 2 — Workforce decomposition

- Agent Directory/detail.
- Worker Fleet.
- Runtimes.
- Gateway & Access.
- Remove equivalent sections from `AIEmployees` only after parity.

### Phase 3 — Observability and knowledge

- Run Explorer/detail.
- Evaluation Lab using live data.
- Tool Call detail.
- Knowledge & Memory using live data.
- Audit Explorer using live data.

### Phase 4 — Commercial surfaces

- Deliveries/customer report.
- Integrations.
- Template Studio.
- Pixel Office integration polish.

## 15. Quality gates and definition of done

A page is not complete until:

- It uses live API data or an explicitly labeled fixture.
- Loading, empty, error, stale and success states exist.
- It works in Chinese and English.
- Keyboard navigation and focus are verified.
- Mobile/tablet behavior is defined.
- Privileged actions show consequence and audit result.
- Object relationships deep-link correctly.
- There are no hard-coded dates, fake success claims or secret values.
- `npm run build` succeeds.
- Existing backend smoke/acceptance tests are not broken.
- Screenshots are captured at 1440×900, 1024×768 and 390×844.

## 16. Success metrics for the redesign

Usability:

- Operator can reach pending approvals in one click from any page.
- Operator can identify the cause of a failed run within three navigational steps.
- Work package to delivery evidence chain is visible without searching raw IDs.
- New user can distinguish agent, worker and runtime after onboarding.

Operational:

- Reduced duplicated UI state and mock-data surfaces.
- `AIEmployees.tsx` decomposed into domain modules.
- Fewer inline style declarations and centralized semantic tokens.
- Shared components cover tables, filters, evidence and decision flows.

Commercial:

- Demo tells a coherent story: goal → plan → execution → approval → evidence → delivery.
- Pixel Office adds memorability without undermining professional trust.
- Template and delivery surfaces can later support paid vertical packages.
