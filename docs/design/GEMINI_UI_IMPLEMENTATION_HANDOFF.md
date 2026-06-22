# Gemini UI v2 Implementation Handoff

> Target implementer: Gemini coding agent  
> Working baseline: `codex/agent-gateway-kb-demo`  
> Design source branch: `design/gemini-ui-research-spec-v2`  
> Required reading:
>
> 1. `docs/project/PROJECT_STATE.md`
> 2. `docs/project/HANDOFF.md`
> 3. `docs/design/UI_BENCHMARK_RESEARCH_2026.md`
> 4. `docs/design/AGENTOPS_MIS_UI_UX_SPEC_V2.md`

## 1. Mission

Redesign the existing AgentOps MIS web application into a coherent, professional and commercially credible operating system for a small human + AI organization.

The result must preserve the product’s local-first control-plane strengths:

- Agent Gateway and scoped enrollment.
- Agents, workers and runtime adapters.
- Commander Work Packages.
- Tasks, runs, tool calls, approvals, artifacts, evaluations and audit.
- Knowledge retrieval and governed memory.
- Human review and customer delivery.
- Pixel Office as an optional live visualization layer.

This is not a decorative re-skin and not a new mock dashboard. It is a staged information-architecture and interaction redesign over the current working APIs.

## 2. Non-negotiable constraints

1. **Use the current development line.** Do not implement against stale `main`. Start from `design/gemini-ui-research-spec-v2` or from a fresh implementation branch based on it.
2. **Read governance state first.** Respect the current security/correctness milestone in `PROJECT_STATE.md` and `HANDOFF.md`.
3. **Do not rewrite the backend.** UI work may request a missing read model in a documented follow-up, but must not refactor `server.py`, gateway auth, approval semantics or worker execution as part of a visual PR.
4. **Do not weaken security.** Never bypass approval, token scope, trust status, redaction or audit behavior for demo convenience.
5. **Use live APIs where they exist.** Mock data is permitted only behind an explicit demo fixture flag and must be visibly labeled.
6. **No hard-coded business dates or fake metrics.** Derive values from API data or show an honest unavailable/empty state.
7. **Preserve bilingual support.** New UI must work in Chinese and English through centralized copy keys.
8. **Use the existing front-end stack.** React, TypeScript, Vite, Tailwind, Radix, React Router and Recharts are already available.
9. **Avoid dependency inflation.** Do not add a large component framework or state library without a written reason. Prefer Radix primitives and project-owned components. Do not introduce more MUI usage in new surfaces.
10. **Use a strangler migration.** Build v2 routes/components beside existing pages, add aliases/feature flags, then retire old sections after parity.
11. **Do not create another mega-page.** Page composition files should ideally remain under 300 lines; move view-model transforms and feature panels into modules.
12. **Pixel Office is not the authority system.** It reads typed MIS state and deep-links to canonical records. Do not put governance logic inside the game scene.

## 3. Product interpretation

The UI should be organized around the human operator’s jobs, not around database table names.

Primary domains:

- **Operate**: Mission Control, Work Packages, Tasks, Human Review, Deliveries.
- **Workforce**: Agents, Worker Fleet, Runtimes, Agent Gateway.
- **Observe**: Runs & Traces, Evaluations, Tool Calls, Incidents.
- **Govern**: Security Approvals, Knowledge & Memory, Policies & Access, Integrations, Templates, Audit.
- **Visualize**: Pixel Office.

The design language is **Operational Calm**:

- Neutral, precise, readable and trustworthy.
- Strong hierarchy and excellent table/list/detail behavior.
- Semantic colors only for state, risk and attention.
- Pixel-art personality stays concentrated in Pixel Office and selected brand moments.
- No broad neon glow, glass card wallpaper, tiny primary text or generic AI-gradient hero sections.

## 4. Required repository analysis before coding

Before changing files, produce a short implementation note containing:

- Current route inventory.
- Current data source for each page: live API, partial live or mock.
- Shared components that can be reused.
- Duplicate concepts/routes.
- Sections currently embedded in `AIEmployees.tsx` and their target modules.
- APIs required for the first milestone.
- Any blocker that requires a backend read model instead of UI guessing.

Do not start by generating hundreds of lines of JSX.

## 5. Branch and commit protocol

Recommended implementation branch:

```bash
git switch design/gemini-ui-research-spec-v2
git pull
git switch -c design/gemini-ui-v2-implementation
```

Commit by coherent slice:

```text
feat(ui-v2): add semantic design tokens and shell
feat(ui-v2): add navigation and command palette
feat(ui-v2): implement mission control
feat(ui-v2): implement work package list and detail shell
feat(ui-v2): add security approval evidence layout
refactor(ui): split workforce modules from AIEmployees
```

Do not mix backend governance changes with visual/UI decomposition in the same commit.

## 6. Phase 0 — Foundation implementation

### 6.1 Deliverables

- `AppShellV2`
- New navigation data model.
- Workspace/environment context bar.
- Global command palette.
- Semantic design tokens.
- Typography and spacing normalization.
- Core shared components.
- Feature flag or route alias for gradual rollout.

### 6.2 Suggested structure

```text
ui/start-building-app/src/app/
  shell/
    AppShellV2.tsx
    PrimaryNav.tsx
    ContextBar.tsx
    CommandPalette.tsx
    navigation.ts
  design-system/
    tokens.css
    components/
      PageHeader.tsx
      StatusPill.tsx
      RiskPill.tsx
      FilterBar.tsx
      DataTable.tsx
      EmptyState.tsx
      ErrorState.tsx
      StaleDataBanner.tsx
      DetailDrawer.tsx
      EvidenceCard.tsx
  modules/
    mission-control/
    work/
    workforce/
    observe/
    govern/
  view-models/
```

The exact names may vary, but domain boundaries must remain clear.

### 6.3 Token migration

Create semantic variables rather than adding more page-specific inline colors:

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
--accent-primary
--focus-ring
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

Maintain compatibility aliases for current `--mis-*` values during migration.

### 6.4 Typography requirements

- Base body: 14 px / 21 px.
- Page title: 22 px / 30 px.
- Section title: 15–18 px.
- Metadata: 12 px.
- Micro labels/IDs: 11 px minimum for normal usage.
- Do not use 10 px for actionable labels or primary content.

### 6.5 Foundation acceptance tests

- Existing legacy routes still render.
- New shell supports Chinese and English.
- Keyboard navigation reaches every nav item and context control.
- Visible focus states.
- Mobile menu/drawer works at 390 px.
- `prefers-reduced-motion` respected.
- `npm run build` succeeds.

## 7. Phase 1 — Mission Control and Work Packages

This is the first user-visible implementation milestone.

## 7.1 Mission Control

Use current APIs and derived view models to show:

1. Attention queue.
2. Four high-signal metrics.
3. Active Work Packages.
4. Workforce health.
5. Recent activity/incidents.
6. Optional Pixel Office preview.

Attention queue types:

- Security approval.
- Human quality review.
- Stuck/failed run.
- Stale/offline worker.
- Runtime health issue.
- Delivery blocker.
- Memory candidate.

Each queue item needs one clear next action and a canonical deep link.

Do not duplicate full approval, run or memory details on the home page.

## 7.2 Work Package list

Implement list first; board/timeline can follow.

Required fields:

- Objective/title.
- Customer/project.
- Commander/human owner.
- Assigned agents.
- Lifecycle state.
- Execution health.
- Security/quality blockers.
- Evidence completeness.
- Updated time.

Required filters:

- Status.
- Owner/agent.
- Customer/project.
- Blocked/attention.
- Updated time.

## 7.3 Work Package detail shell

Tabs:

- Overview
- Plan
- Tasks
- Runs & Evidence
- Delivery
- Activity

The current immutable Agent Plan reference/hash must be visible before dispatch, approval and delivery review.

If the backend does not yet return a complete work-package read model, do not fabricate it. Build an adapter over current endpoints and document the missing API fields.

## 7.4 Phase 1 proof

Capture screenshots at:

- 1440×900 dark.
- 1440×900 light.
- 1024×768.
- 390×844.

Record a short flow:

```text
Mission Control → Work Package → Task → Run → Evidence
```

## 8. Phase 2 — Decisions and workforce decomposition

## 8.1 Security Approvals

Redesign from a simple approve/reject card into an evidence-centered decision surface.

Show:

- Plain-language action.
- Agent, worker and runtime.
- Work package/task/run.
- Target resource and affected scope.
- Prepared action or diff.
- Risk and policy reason.
- Exact plan/action revision hash.
- Previous related decisions.
- Approver identity and decision comment.

Actions:

- Approve this revision once.
- Approve bounded session if supported.
- Reject.
- Request changes/clarification.

Do not use a generic modal for high/critical risk.

## 8.2 Human Review

Separate quality review from security approval.

Show:

- Objective and acceptance criteria.
- Artifact preview.
- Evaluation evidence.
- Relevant run context.
- Reviewer checklist/comment.

Actions:

- Accept delivery.
- Request changes.
- Reject.
- Create follow-up task.

## 8.3 Split `AIEmployees.tsx`

Move UI into independent modules while preserving API calls and behavior:

- Agent Directory.
- Worker Fleet.
- Runtimes.
- Agent Gateway.
- Commander Work Packages.
- Human Review.
- Customer Deliveries.

Do not delete old sections until their replacement reaches functional parity.

## 8.4 Agent Directory

Directory page contains identity, role, assignment, capability, runtime policy, performance and permission summary only.

It must not contain:

- Daemon controls.
- Enrollment token forms.
- Workflow recovery.
- Commander planner.
- Customer delivery board.

## 8.5 Worker Fleet

Show host/process identity, heartbeat, capacity, queue/current job, installed adapters and health. Restart/drain/disable actions require reviewed confirmation and visible audit result.

## 8.6 Gateway & Access

Tabs:

- Overview
- Enrollment
- Scopes
- Tokens/Service Identities
- Sessions
- Policy History

Never display stored token material. A newly issued one-time token may be shown once according to existing backend behavior.

## 9. Phase 3 — Observability, knowledge and audit

## 9.1 Run Explorer

Implement a filterable list and trace detail.

Run detail tabs:

- Overview
- Trace
- Inputs/Outputs
- Tool Calls
- Artifacts
- Evaluations
- Audit
- Raw

Trace requirements:

- Parent/child hierarchy.
- Timeline/waterfall where data supports it.
- Tool risk and approval markers.
- Inspector panel that preserves trace position.

Do not manufacture spans that the API does not provide; use explicit “not available” states and document the read-model gap.

## 9.2 Evaluation Lab

Replace implicit mock behavior with live evaluation APIs or a clearly labeled fixture flag.

Show named criteria, evaluator, score, threshold, notes/evidence, linked run/task/artifact and trend filters.

## 9.3 Tool Calls

Upgrade the flat table with a detail drawer containing redacted arguments/results, target resource, prepared action, policy/approval chain, error/retry and parent trace.

## 9.4 Knowledge & Memory

Replace the current mock-only page with:

- Search
- Sources
- Memory Review
- Retrieval Test

Every item displays source/provenance, scope, confidence, review state, freshness/TTL, access tags and related plan/run usage.

## 9.5 Audit Explorer

Use live audit API, filters, correlation links and integrity status. Provide redacted export only if supported; do not invent a successful chain-verification state.

## 10. Phase 4 — Commercial surfaces and Pixel Office

## 10.1 Deliveries

Create an operator delivery board and a separate customer-safe report presentation.

Customer-safe default excludes:

- Raw prompts.
- Secrets/secret references that reveal infrastructure.
- Internal policy details.
- Full audit metadata.
- Private agent notes.

## 10.2 Integrations

Separate runtime adapters from knowledge/data/model/developer integrations. Use a reviewed configuration flow explaining access and secret-reference usage.

## 10.3 Template Studio

Tabs:

- Discover
- Installed
- Export & Bases

Preview included roles, workflows, policies, knowledge, runtimes, reports, compatibility, license and protected local objects.

Do not implement marketplace billing in this milestone; preserve space in the data and layout for future commercialization.

## 10.4 Pixel Office

Polish as an optional visualization mode:

- Consume typed scene state.
- Deep-link rooms/avatars to canonical pages.
- Show presence, assignment, blocked/approval/incident state.
- Provide pause and reduced-motion controls.
- Never display sensitive data.

## 11. Test and validation commands

Run at minimum:

```bash
cd ui/start-building-app
npm install
npm run build
```

If the repository contains updated smoke/acceptance commands, read `docs/project/HANDOFF.md` and execute the relevant non-destructive tests.

Browser validation:

- Test Chinese and English.
- Test light and dark.
- Test loading, empty, backend unavailable and stale states.
- Test keyboard-only navigation.
- Test high-risk approval decision without leaking secrets.
- Test deep links across work package → task → run → tool/artifact/evaluation/audit.

## 12. PR requirements

Every PR description must include:

- User problem solved.
- Screens/routes changed.
- API endpoints used.
- Mock/live data status.
- Security impact.
- Responsive screenshots.
- Accessibility checks.
- Build/test output.
- Deferred items and backend read-model gaps.

Do not claim a screen is production-ready unless live data, error states, permissions and security consequences are implemented.

## 13. First execution prompt for Gemini

Use this exact bounded task for the first implementation PR:

```text
You are implementing AgentOps MIS UI v2 on branch design/gemini-ui-research-spec-v2.

Read, in order:
1. docs/project/PROJECT_STATE.md
2. docs/project/HANDOFF.md
3. docs/design/UI_BENCHMARK_RESEARCH_2026.md
4. docs/design/AGENTOPS_MIS_UI_UX_SPEC_V2.md
5. docs/design/GEMINI_UI_IMPLEMENTATION_HANDOFF.md

Do not implement against main. Do not modify backend execution, auth, approval or worker semantics.

Scope for this PR only:
- Add semantic design tokens while keeping --mis-* compatibility.
- Add AppShellV2 behind a feature flag or v2 route boundary.
- Add the new primary navigation groups: Operate, Workforce, Observe, Govern, Visualize.
- Add workspace/environment/data-freshness context bar.
- Add command palette for navigation and record search using existing APIs where available.
- Add shared PageHeader, StatusPill, RiskPill, EmptyState, ErrorState and StaleDataBanner components.
- Implement a v2 Mission Control page using live data. Prioritize attention items; show only four top metrics. No hard-coded dates and no synthetic charts.
- Preserve all existing routes and behavior.
- Preserve Chinese/English and light/dark themes.
- Do not add a large dependency.

Before coding, write a short route/data-source inventory in the PR description. After coding, run npm run build and attach screenshots at 1440×900, 1024×768 and 390×844 in both available themes where practical.
```

## 14. Stop conditions

Stop and report rather than guessing when:

- A required status or relationship cannot be derived safely from current APIs.
- A UI action would bypass approval or permission enforcement.
- A page would need to expose raw secrets/prompts to appear complete.
- A backend contract is inconsistent with `PROJECT_STATE.md` authority rules.
- The work would require a big-bang rewrite instead of staged migration.

The correct output in these cases is a small read-model/API proposal, not fabricated UI state.
