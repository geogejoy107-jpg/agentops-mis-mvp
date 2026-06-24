# AgentOps MIS UI Benchmark Research 2026

> Status: design research baseline for Gemini implementation  
> Date: 2026-06-21  
> Product baseline: `codex/agent-gateway-kb-demo`  
> Scope: product UI, operator UX, information architecture, observability, approvals, workforce, knowledge, gateway, templates, delivery and Pixel Office integration

## 1. Research objective

AgentOps MIS is no longer a simple dashboard prototype. The current development branch already contains a local-first Agent Gateway, worker fleet, runtime adapters, Commander Work Packages, human review queue, customer delivery board, Run Ledger, Tool Call Ledger, approvals, evaluation, memory, audit and Pixel Office state mapping.

The design task is therefore not to make the current pages “more colorful”. It is to turn a growing control plane into a coherent operating system for a small human + AI organization.

The target experience must answer five questions within seconds:

1. What needs human attention now?
2. What work is in progress, blocked, waiting for approval or ready for delivery?
3. Which agent, worker and runtime is responsible?
4. What evidence proves that the work was executed correctly and safely?
5. Where can the operator inspect, approve, replay, compare or recover the process?

The long-term product vision remains intact: one-person companies, research teams, company templates, multi-agent orchestration, GPU/experiment workflows, agent marketplace and commercial company OS. The UI is designed so these can be added later without replacing the information architecture.

## 2. Current product diagnosis

### 2.1 What is already strong

- The authority chain is explicit: Spec / Decision → Knowledge → Agent Plan → Task → Run → Tool Call / Prepared Action → Approval → Artifact → Evaluation → Memory Candidate → Audit.
- Local-first operation and runtime neutrality are real product differentiators.
- The system already exposes meaningful operational objects rather than only chat messages.
- Commander, review, delivery and evidence workflows create a credible “AI workforce” surface.
- Pixel Office can become an expressive visualization mode without becoming the authority database.

### 2.2 Current UI risks

- Navigation is split into “Client Workspace” and “Admin Console”, but the same entities appear in both; for example Agent Registry and AI Employees point to the same route.
- The `AIEmployees` page has grown into a mega-page that mixes agent directory, worker fleet, runtime gateway, enrollment, sessions, Commander planning, review queue, delivery board, daemon control and integration health.
- Several critical pages still use mock data while related APIs already exist.
- Many pages are tables or KPI-card walls rather than task-oriented workflows.
- Body text is frequently 10–12 px, which harms scanability and accessibility.
- Styling is heavily inline, semantic colors are overused, and there is no stable component/token contract.
- The Pixel Office is visually separate from the product shell and can easily become a second hard-coded system if not constrained.

The redesign must therefore prioritize information architecture and workflow clarity before visual decoration.

## 3. Benchmark method

Products are evaluated by the UI problem they solve, not by copying their visual identity.

Each benchmark is separated into:

- **Pattern to borrow**: a proven interaction or information architecture pattern.
- **Adaptation for AgentOps MIS**: how the pattern maps to our authority chain.
- **What not to copy**: elements that conflict with local-first governance, evidence requirements or product identity.

## 4. Module benchmark matrix

## 4.1 Global shell, navigation and command model

### Linear

Official references:

- https://linear.app/docs/projects
- https://linear.app/docs/initiatives
- https://linear.app/docs/cycles

Patterns to borrow:

- Fast keyboard-first navigation and command palette.
- Clear hierarchy from initiative/project to issue and sub-issue.
- Compact but readable rows, saved views, filters and predictable details panels.
- Strong use of neutral surfaces; state color is reserved for status and priority.
- Projects summarize outcome, progress, lead, target date and recent updates rather than presenting a wall of metrics.

Adaptation:

- Map initiative → company goal or portfolio.
- Map project → Commander Work Package / customer project.
- Map issue → task.
- Add AgentOps-only evidence dimensions: plan hash, approval state, run coverage, artifact completeness and evaluation pass rate.

Do not copy:

- A software-issue-only mental model. AgentOps work may include research, operations, customer delivery and experiments.

### Vercel

Official reference:

- https://vercel.com/docs/observability

Patterns to borrow:

- Environment and deployment context is always visible.
- Overview pages lead to logs, traces and specific incidents without duplicating those tools.
- Time range, environment and project filters are global and persistent.
- Deployment state is summarized in a small number of high-signal cards.

Adaptation:

- Global context bar should expose workspace, execution environment (`local`, `demo`, `remote`), runtime status and data freshness.
- “Deployment” becomes a work package delivery or run execution.
- Health summaries should deep-link into the actual evidence.

Do not copy:

- Cloud-first assumptions. The primary state must still work offline or on a local server.

### Stripe Dashboard

Pattern to borrow:

- A serious, calm operational visual system with excellent hierarchy, tables and progressive disclosure.
- Searchable, filterable object lists with predictable object-detail pages.
- Activity and audit information is part of the object story, not a separate afterthought.

Adaptation:

- Every agent, task, run, approval, artifact and memory item gets a stable object header and detail layout.
- Use object IDs as secondary metadata, never as the only human-readable label.

Do not copy:

- Finance-specific density or terminology.

### Attio

Pattern to borrow:

- Flexible record views and relationship-centric data.
- Fast table/list switching and configurable properties.
- Detail drawers allow users to inspect records without losing list context.

Adaptation:

- Allow work packages, tasks, agents and memories to share a common view/filter framework.
- Use side panels for quick inspection, full pages for deep evidence or policy decisions.

## 4.2 Work packages, projects and tasks

### Linear Projects + GitHub Projects

Patterns to borrow:

- A project overview combines progress, milestones, recent updates and linked work.
- Views can switch between list, board and timeline over the same data.
- Filters are composable and can be saved.
- Detail pages preserve navigational context and show relationship links.

AgentOps adaptation:

A Work Package detail must contain:

1. Objective and customer/business outcome.
2. Commander, supervising human and assigned agents.
3. Acceptance criteria and constraints.
4. Immutable Agent Plan reference and hash.
5. Tasks and dependency graph.
6. Runs, tool calls and approvals.
7. Artifacts and delivery readiness.
8. Evaluation and evidence completeness.
9. Timeline and audit events.

Unique AgentOps status model:

- Draft
- Planned
- Ready
- Running
- Waiting for human
- Blocked
- Under review
- Ready for delivery
- Delivered
- Failed / Cancelled

The UI must distinguish **work status**, **execution health**, **security approval state** and **quality review state**. One ambiguous status pill is insufficient.

## 4.3 Mission Control / operations command center

### Datadog, Grafana, Sentry and Vercel Observability

Patterns to borrow:

- “Attention first”: incidents, failures, regressions and blocked work are above vanity metrics.
- Time range and scope filters are consistent across panels.
- Metrics link to underlying events/traces.
- High-level overview never replaces dedicated investigation surfaces.

AgentOps adaptation:

The home page should prioritize:

1. Pending security approvals.
2. Human review items.
3. Stuck or failed runs.
4. Offline/stale workers and unhealthy adapters.
5. Delivery blockers.
6. Memory candidates requiring curation.

Only four top-level metrics should be shown by default:

- Active work packages
- Work waiting for humans
- Run success rate
- Healthy execution capacity

Cost, tokens, queue depth and throughput belong in secondary panels or drill-downs.

Do not copy:

- A monitoring-wall aesthetic with dozens of gauges.
- Red/green-only status communication.

## 4.4 Runs, traces, tool calls and evaluation

### LangSmith

Official reference:

- https://docs.langchain.com/langsmith/observability

Patterns to borrow:

- Trace tree and nested runs make agent trajectories inspectable.
- Input/output, metadata, feedback, latency and errors are connected to the same run.
- Filters and drill-down support debugging from broad trend to one trace.

### Langfuse

Official reference:

- https://langfuse.com/docs/observability/features/traces

Patterns to borrow:

- Trace → observation/span → generation/tool hierarchy.
- Sessions and users are first-class grouping dimensions.
- Cost, token and latency metadata are visible without dominating the trace.

### Arize Phoenix

Official reference:

- https://arize.com/docs/phoenix/tracing

Patterns to borrow:

- OpenTelemetry-style spans, status and attributes.
- Strong distinction between trace navigation and evaluation analysis.
- Error investigation is connected to model/tool behavior.

### Braintrust

Official reference:

- https://www.braintrust.dev/docs/guides/evals

Patterns to borrow:

- Dataset, experiment, scorer and result comparison.
- Side-by-side evaluation makes regressions concrete.
- Evaluation is not a single score; it is a set of named criteria and evidence.

AgentOps adaptation:

The Run Explorer should provide:

- List view with saved filters and time range.
- Trace tree/waterfall.
- Run summary: task, agent, worker, runtime, model, plan hash, start/end, status.
- Inputs and outputs with redaction labels.
- Tool calls with risk, target, policy decision and approval chain.
- Artifacts with integrity/checksum and preview.
- Evaluations with rubric, score, pass/fail and reviewer.
- Audit events linked in time order.
- Raw JSON only as an advanced tab.
- Compare two runs for output, latency, cost, tool path and evaluation deltas.

The Tool Call Ledger should become an investigation list, not only a flat table. Clicking a tool call must show:

- Redacted arguments and result.
- Target resource.
- Risk classification and policy reason.
- Prepared action or diff.
- Approval decision and approver separation.
- Parent run and plan binding.
- Duration, retry and error state.

## 4.5 Human review and security approval

### GitHub pull request review

Official reference:

- https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests

Patterns to borrow:

- Review is evidence-centered: summary, changed files, discussion, checks and final decision.
- Reviewers can request changes rather than only approve/reject.
- The decision remains linked to the exact revision being reviewed.

### Cloudflare Access policies

Official reference:

- https://developers.cloudflare.com/cloudflare-one/access-controls/policies/

Patterns to borrow:

- Explicit policy rules, order, scope and decision reasoning.
- Sessions, service tokens, applications and identities are separable objects.
- Purpose justification and step-up access are visible governance concepts.

AgentOps adaptation:

Separate two queues that are currently easy to confuse:

1. **Security Approval**: permission to execute a prepared action.
2. **Quality Review**: judgment that output/artifact satisfies acceptance criteria.

Security Approval screen must show:

- Requested action in plain language.
- Exact tool/runtime/agent/worker.
- Scope and affected resource.
- Prepared action preview or diff.
- Risk level and policy rule.
- Plan hash/revision being approved.
- Whether approval is one-time, session-scoped or denied.
- Previous related decisions.
- Separate approver identity and audit chain.

Quality Review screen must show:

- Acceptance criteria checklist.
- Artifact previews.
- Evaluation evidence.
- Reviewer comments.
- Approve delivery, request changes or reject.

Do not use a generic confirmation modal for high-risk actions.

## 4.6 AI workforce, workers and runtime gateway

### Temporal Web UI and GitHub Actions

Official references:

- https://docs.temporal.io/web-ui
- https://docs.github.com/en/actions/how-tos/monitor-workflows/view-workflow-run-history

Patterns to borrow:

- Workflow/job history with status, duration, retry and step details.
- Operators can inspect the current execution and its history without confusing workflow definitions with runs.
- Filters and explicit retry/cancel controls are contextual.

### Dagster / Prefect operational UIs

Patterns to borrow:

- Asset/workflow definitions are separated from individual executions.
- Schedules, sensors, workers and run queues have dedicated operational views.
- Health and freshness have clear operator meanings.

### Cloudflare Zero Trust, Tailscale Admin and Okta

Patterns to borrow:

- Device/session identity, trust and policy are explicit.
- Enrollment, authorization scope and current session are separate concepts.
- Security-sensitive changes use confirmation and strong audit visibility.

AgentOps adaptation:

The current `AIEmployees` mega-page must be split into three products surfaces:

### A. Agent Directory

- Role, description and capability set.
- Default runtime and model policy.
- Current assignment and status.
- Success/evaluation/cost trend.
- Permissions and allowed tools.
- Memory access scope.
- Agent detail tabs: Overview, Assignments, Runs, Evaluations, Memory, Permissions.

### B. Worker Fleet

- Worker ID, host, version and environment.
- Heartbeat, queue status and active job.
- Capacity/concurrency.
- Runtime adapters installed.
- Health issues and stale state.
- Drain/restart/disable actions with confirmation.

### C. Agent Gateway

- Gateway readiness and endpoint.
- Enrollment policy.
- Scope catalog.
- Tokens/service identities.
- Active sessions.
- Runtime trust registry.
- Redaction/auth status.
- Policy change history.

These surfaces may share data, but they must not share one giant page component.

## 4.7 Knowledge, memory and retrieval

### Notion database views

Official reference:

- https://www.notion.com/help/guides/using-database-views

Patterns to borrow:

- One data set can be shown as table, list, board, gallery, calendar or timeline.
- Filters, sorts, groups and properties are user-configurable.
- Each record is both a row/card and a rich detail page.

### Dify Knowledge

Official reference:

- https://docs.dify.ai/en/use-dify/knowledge/readme

Patterns to borrow:

- Knowledge base → document → chunk hierarchy.
- Retrieval testing is a dedicated workflow.
- Metadata, index strategy, source and retrieval behavior are inspectable.
- External knowledge sources can be connected without pretending they are local authority.

### Glean / enterprise search pattern

Patterns to borrow:

- Search results carry source, permissions, freshness and context.
- Filters help users understand why a result is visible and relevant.

AgentOps adaptation:

The Knowledge & Memory surface needs four modes:

1. Search: hybrid query with source/scope/type/status filters.
2. Sources: Markdown, project specs, decisions, runtime docs, external bases.
3. Memory Review: candidate → approved/canonical → stale/superseded/rejected.
4. Retrieval Test: query, top hits, score, source excerpt, ACL/provenance and run consumption.

Every memory or knowledge result should expose:

- Scope/workspace/project.
- Source URI and source type.
- Provenance chain.
- Confidence.
- Review status.
- Freshness/TTL.
- ACL/access tags.
- Related decisions, plans, tasks and runs.
- Duplicate or contradiction warnings.

## 4.8 Integrations and templates

### Vercel integrations, Notion templates, n8n/Zapier templates

Patterns to borrow:

- Integration cards clearly state data access and permissions before installation.
- Templates preview included objects, workflow and expected outcome.
- Installation is a staged flow with review rather than one destructive action.
- Community/marketplace discovery is separated from installed resources.

AgentOps adaptation:

Template detail should preview:

- Intended company/team type.
- Included agent roles.
- Work package/workflow definitions.
- Approval and security policies.
- Knowledge sources and memory scopes.
- Dashboards and reports.
- Required runtimes/integrations.
- Local-only records versus exportable records.
- Version, author, license and compatibility.

The current “Template + Base Switching” screen can evolve into a Template Studio with three tabs:

- Discover
- Installed
- Export / External Bases

## 4.9 Customer delivery and reports

Patterns from Linear project updates, Vercel deployment details and Stripe object reports:

- Delivery status is tied to concrete artifacts and checks.
- Stakeholder view is simpler than operator view.
- A shared report must never expose secrets, raw prompts or internal policy data by default.

AgentOps adaptation:

Customer Project Report should show:

- Executive summary.
- Objectives and completion state.
- Deliverables/artifacts.
- Validation/evaluation evidence.
- Timeline and key decisions.
- Open risks or requested changes.
- Export/share controls with an explicit redaction profile.

## 4.10 Pixel Office and game-like visualization

Reference products/patterns:

- Gather and WorkAdventure: rooms and avatars provide spatial awareness.
- Management/simulation games: visual state is readable through movement, zones, alerts and props.

AgentOps rules:

- Pixel Office is a visualization and orientation layer, never the authority system.
- State is derived from MIS APIs through a typed scene adapter.
- Clicking an avatar or room opens the corresponding formal object/page.
- Pixel mode may show presence, queue, blocked state, active assignment and incident alerts.
- It must not expose tokens, secrets, raw tool arguments or private customer data.
- It may use its own art direction, but shares semantic status tokens with the product shell.

## 5. Design inspiration sources and how to use them

## 5.1 Product flow research

### Mobbin

- https://mobbin.com/
- Best for real product screens, UI elements and end-to-end flows.
- Use for navigation, onboarding, settings, filters, empty states and responsive behavior.
- Do not use it as a source for copying one product wholesale.

### Page Flows

- https://pageflows.com/
- Best for recorded journeys and micro-interactions.
- Use to study approval, setup, invite, search and error-recovery flows.

### Refero

- https://refero.design/
- Best for web product UI references and component-level patterns.

### SaaSFrame

- https://www.saasframe.io/
- Best for SaaS interface and marketing pattern comparison.
- Use for page composition, not for governance logic.

## 5.2 Visual/art-direction inspiration

### Awwwards

- https://www.awwwards.com/
- Use selectively for landing page composition, transitions and brand expression.
- Do not use experimental scrolling, low contrast or decorative WebGL inside the operator console.

### Recent / Godly

- https://godly.website/
- Use for contemporary visual trends and small interaction ideas.

### Land-book

- https://land-book.com/
- Useful for curated landing pages, sections, typography, color and software/AI categories.

### Figma Community

- https://www.figma.com/community
- Use for wireframe kits, icon references and prototyping utilities.
- Verify licenses and do not ship third-party assets without review.

## 5.3 Design systems and implementation references

### GitHub Primer

- https://primer.style/product/getting-started/foundations/
- Strong reference for complex technical product UI, responsive layouts, data tables, timelines, progressive disclosure and accessible components.

### Atlassian Design System

- https://atlassian.design/foundations/
- Strong reference for design tokens, spacing, content language, navigation and work-management patterns.

### Radix UI

- Use for accessible primitives already compatible with the current React/Tailwind stack.

### WCAG 2.2

- https://www.w3.org/WAI/WCAG22/quickref/
- Required baseline: keyboard navigation, visible focus, minimum contrast, reflow, headings/labels, non-color status cues, target size and reduced motion.

## 6. Consolidated design principles

1. **Attention before analytics.** The first screen shows what requires action, not ten equal KPI cards.
2. **Evidence before confidence.** Every “success”, “safe”, “ready” or “approved” state links to evidence.
3. **One object, one canonical detail page.** Do not duplicate agent/task/run truth across multiple dashboards.
4. **Separate work, execution, security and quality state.** These are different dimensions.
5. **Progressive disclosure.** Summary first, evidence on demand, raw JSON last.
6. **Neutral by default, semantic color by exception.** Color communicates status/risk; it is not page wallpaper.
7. **Local-first clarity.** The UI always states environment, data freshness and whether an action is real, dry-run or demo.
8. **Keyboard-first, mouse-friendly.** Search, command palette and shortcuts are first-class.
9. **Dense but readable.** Base body text is 14 px; 12 px is metadata; 10 px is limited to tiny labels, never primary information.
10. **Bilingual by structure, not duplication.** Use stable copy keys and layouts that tolerate longer Chinese/English labels.
11. **No silent automation.** Important agent actions show plan, scope, policy and audit state.
12. **Pixel Office remains optional.** It expresses operations; it does not replace operations.

## 7. Product identity recommendation

The visual direction should be described as **Operational Calm + Intelligent Workforce**.

It should feel:

- More trustworthy than a consumer AI chat app.
- More alive than a traditional ERP.
- Less intimidating than a security console.
- More systematic than an agent demo dashboard.

Recommended visual mix:

- Linear/Attio clarity for work management.
- Stripe/Primer precision for records and governance.
- Vercel/LangSmith depth for observability.
- A restrained game layer for Pixel Office.

Avoid:

- Cyberpunk neon everywhere.
- Glassmorphism on dense data surfaces.
- Cards around every piece of text.
- Generic AI gradients as the main identity.
- Huge hero sections inside the application.
- Tiny typography or icon-only critical actions.

## 8. Research conclusion

The strongest product position is not “another agent dashboard”. It is a human-supervised operating system where work, execution, evidence, approvals, delivery and memory are linked.

The UI should make the authority chain visible without forcing users to understand the database schema. The design must therefore organize the product around operator jobs and object relationships, then use dashboards, tables, traces and Pixel Office as complementary views of the same truth.
