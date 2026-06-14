# AgentOps MIS — Implementation Plan (+ Pixel Hero Addition)

## Context

User has a real Python backend (`geogejoy107-jpg/agentops-mis-mvp`, private) with SQLite schema, REST API in `server.py`, and demo seed scripts. The goal is to build a **high-fidelity React frontend** in this Figma Make scaffold — using mock data shaped exactly to the real DB schema so it can be wired to the live API (`http://localhost:5000`) with minimal change later.

Two portal experiences: **Client Workspace** (operator/reviewer) and **Admin Console** (owner/admin/auditor). Eight core screens. Visual style: **Dark Ops Control Plane** (dark navy + cyan/purple).

---

## Real Schema Enums (from `sql/schema.sql` + `docs/DATABASE_SCHEMA.md`)

```
agents.status:          idle | running | paused | error | disabled
agents.runtime_type:    mock | claude_code | codex | openhands | crewai | langgraph | openclaw | hermes
tasks.status:           backlog | planned | running | waiting_approval | blocked | completed | failed | canceled
tasks.risk_level:       low | medium | high | critical
tasks.priority:         low | medium | high | critical
tool_calls.category:    browser | github | file | shell | email | notion | discord | database | mcp | custom
tool_calls.risk_level:  low | medium | high | critical
approvals.decision:     pending | approved | rejected | expired
memories.review_status: candidate | approved | rejected | stale | superseded
memories.scope:         task | project | org
evaluations.pass_fail:  pass | fail
audit_logs.actor_type:  user | agent | system
```

Runtime connector IDs (v1.2.1): `rtc_openclaw`, `rtc_hermes_default`, `rtc_agnesfallback_cli`, `rtc_agnesfallback_openai_api`

High-risk tools requiring approval: `shell.exec`, `github.push`, `email.send`, `file.delete`, `database.write`, `mcp.invoke`

---

## Files to Modify

- `src/app/App.tsx` — BrowserRouter + route tree
- `src/styles/theme.css` — add AgentOps dark color tokens

---

## New Files

### Layout — `src/app/components/layout/`
- `AppShell.tsx` — root layout: sidebar (fixed left) + topbar + `<Outlet>`
- `Sidebar.tsx` — two nav groups (Client Workspace / Admin Console), active state, collapse support
- `Topbar.tsx` — workspace switcher, search input, live-mode status pill, user avatar dropdown

### Shared — `src/app/components/shared/`
- `StatusBadge.tsx` — maps every status/decision enum to colored badge variant
- `RiskBadge.tsx` — low=green / medium=yellow / high=orange / critical=red
- `MetricCard.tsx` — icon + value + label + optional trend arrow (wraps `ui/card`)
- `ConnectorCard.tsx` — runtime connector card: provider, status, mode, last_checked, confirm_required, probe button
- `AuditTimeline.tsx` — vertical timeline of `audit_logs` entries with actor type icon

### Mock Data — `src/app/data/mockData.ts`
Typed mock records using real field names:
- 5 agents (incl. `agt_openclaw`, `agt_research`, `agt_writer`)
- 8 tasks across all statuses
- 10 runs (one with `parent_run_id` for delegation demo)
- 15 tool_calls (mixed risk levels, incl. `shell.exec` as high-risk)
- 3 pending approvals
- 6 memory candidates
- 4 evaluations
- 10 audit_log entries
- 4 runtime_connectors with real connector_id values
- 4 template_packages

### Pages — `src/app/components/pages/`

1. **`WorkspaceHome.tsx`** — today's agent activity, pending approvals (from `approvals` where decision=pending), active tasks, recent runs, memory candidates, connected bases, quick-action buttons

2. **`ControlTower.tsx`** — 10 KPI MetricCards (total agents, tasks, runs, pending approvals, runtime health, failure rate, total cost, memory candidates, openclaw imports, audit flags), AreaChart (run volume by day), BarChart (cost by agent), agent performance summary table

3. **`AgentDetail.tsx`** — agent profile (name, role, runtime_type, model_provider/model_name), allowed_tools list with risk annotation, budget_limit_usd + used bar, success rate, recent runs table, approval-required actions, evaluation score card; routed at `/admin/agents/:id`

4. **`TaskDetail.tsx`** — task header with status/risk/priority badges, description, acceptance_criteria, collaborator_agent_ids, related runs table, approvals list, memory candidates, artifacts, quality gate progress bar (evaluation score); routed at `/admin/tasks/:id`

5. **`RunDetail.tsx`** — run metadata (runtime_type, model, tokens, cost_usd, duration_ms), parent/child delegation graph (static SVG node diagram), tool_calls table with risk badges, evaluation result (pass/fail + score), AuditTimeline, error panel if status=failed; routed at `/admin/runs/:id`

6. **`RuntimeConnectors.tsx`** — four ConnectorCards:
   - `rtc_openclaw`: status=ready, last probe success, import count
   - `rtc_hermes_default`: status=unavailable, recorded health failure
   - `rtc_agnesfallback_cli`: status=live, confirm_required=true, dry-run default
   - `rtc_agnesfallback_openai_api`: status=dry_run, OpenAI-compatible mode
   Below cards: recent `runtime_events` list

7. **`NotionBase.tsx`** — export mode selector (dry_run_only / page_parent / database_parent / workspace_private), token status masked ("configured" or "not set"), writeback toggle (OFF by default, red warning if ON), linked memory objects count, sync_events log, export preview JSON block, security note about token rotation

8. **`TemplateSwitching.tsx`** — 4 template package cards (AI Software Team / AI Experiment Evaluation / Content Studio / One-Person Company Ops), current base = "Agent-MIS Local", target base selector (Notion / W&B / Plane / Docmost), field mapping table, capability comparison grid, non-migratable fields list (Run Ledger, Tool Call Ledger, Approval, Audit, Agent IAM, Evaluation stay in core), migration preview status

---

## Routes

```
/                      → navigate to /workspace
/workspace             → WorkspaceHome
/admin                 → ControlTower
/admin/agents/:id      → AgentDetail
/admin/tasks/:id       → TaskDetail
/admin/runs/:id        → RunDetail
/admin/connectors      → RuntimeConnectors
/admin/bases/notion    → NotionBase
/admin/templates       → TemplateSwitching
```

Use `react-router` v7 with `BrowserRouter` + `Routes` + `Route` + `Navigate`.

---

## Color Tokens (append to `src/styles/theme.css`)

```css
--color-mis-bg:       #0B1020;
--color-mis-surface:  #111827;
--color-mis-surface2: #1a2236;
--color-mis-border:   #1F2937;
--color-mis-primary:  #2E86AB;
--color-mis-success:  #2A9D8F;
--color-mis-warning:  #E76F51;
--color-mis-purple:   #7A5AF8;
--color-mis-cyan:     #22D3EE;
--color-mis-muted:    #6B7280;
--color-mis-text:     #E5E7EB;
--color-mis-dim:      #9CA3AF;
```

Override `background` on `<body>` to `var(--color-mis-bg)` in App.tsx wrapper.

---

## Key Reused UI Components (already in project)

- `src/app/components/ui/card.tsx` — all surface cards
- `src/app/components/ui/badge.tsx` — StatusBadge / RiskBadge base
- `src/app/components/ui/table.tsx` — run ledger, tool calls, audit tables
- `src/app/components/ui/tabs.tsx` — detail page tab panels
- `src/app/components/ui/progress.tsx` — quality gate, budget usage bars
- `src/app/components/ui/separator.tsx` — section dividers
- `recharts` (AreaChart, BarChart, Tooltip, ResponsiveContainer)
- `lucide-react` (Activity, Shield, Cpu, Database, GitBranch, AlertTriangle, CheckCircle, Clock, etc.)

---

---

## Pixel Hero Section (New Addition)

### Goal
Add an isometric pixel-art AI workforce hero to the top of `WorkspaceHome.tsx`. Premium enterprise feel — dark navy base, glowing status lights, moving agents, floating metric cards.

### New File
**`src/app/components/shared/PixelHero.tsx`**

Built with pure SVG + CSS — no canvas, no third-party library.

### Layout Structure
```
<section class="hero-wrapper">          // dark navy, relative positioned, overflow-hidden
  <div class="iso-stage">              // CSS isometric transform container
    <svg class="iso-floor">           // The floating platform + all zones + agents
      <!-- Zone tiles (filled rect with pixel border) -->
      <!-- Agent sprites (pixelated SVG characters, 8x8) -->
      <!-- Connector lines between zones -->
      <!-- Status light dots (blinking circles) -->
    </svg>
  </div>
  <div class="float-metrics">         // Absolutely positioned metric cards (non-isometric)
    <!-- 6 floating KPI chips -->
    <!-- 3 connector status pills -->
  </div>
</section>
```

### Isometric Technique
CSS transform on the stage div:
```css
transform: rotateX(45deg) rotateZ(45deg) scale(0.85);
```
The SVG sits on a flat XY grid; the CSS transform projects it into isometric view.

### Work Zones (10 tiles on the SVG grid)
Each zone = a colored rectangle with a pixel-font label, positioned on the grid:
1. Control Tower — cyan glow
2. Agent Registry Desk — purple
3. Task Board Zone — blue
4. Runtime Lab — orange glow
5. Tool Room — gray
6. Approval Gate — yellow blink
7. Memory Library — purple
8. Evaluation Room — green
9. Audit Vault — red glow
10. External Base Dock — teal (shows Notion, W&B, Plane icons as small dots)

### Agent Sprites (6 characters)
Tiny 8×8 SVG pixelated figures, each colored differently. CSS `@keyframes` animations move them along predefined SVG path segments between zones. Staggered delays create organic movement.

Characters: Research (cyan), Coding (purple), Reviewer (green), Ops (orange), Connector Bot (teal), Memory Curator (lavender).

### Floating Metric Cards (non-isometric, overlay)
6 chips positioned around the hero using absolute positioning:
- Agents: 16
- Runs: 6,043
- Audit Logs: 57,205
- Memory Candidates: 3,003
- Total Cost: $2.22
- Pending Approvals: 2

3 connector status pills (bottom strip):
- OpenClaw · Ready (green dot)
- Agnesfallback · Live (cyan pulse)
- Notion · Dry-run (blue)

### Animation Storyboard (CSS keyframes)
1. Research Agent walks from Registry → Task Board
2. Coding Agent enters Runtime Lab (glow pulse on lab)
3. Approval Gate blinks yellow (high-risk pause)
4. Memory Curator moves to Memory Library
5. Connector Bot walks to External Base Dock (Notion sync flash)
6. Control Tower top light pulses every 2s

### Integration
Add `<PixelHero />` at the very top of `WorkspaceHome.tsx`, before the summary strip cards. Height: ~280px. Responsive: collapses to a static flat view on narrow viewports.

## Verification

1. All 8 routes render without console errors
2. Sidebar navigation switches pages; active item highlighted
3. Dark navy background + cyan/purple accents render correctly
4. StatusBadge: `running`=cyan, `completed`=green, `failed`=red, `waiting_approval`=orange, `pending`=yellow
5. ControlTower: 10 KPI cards + 2 recharts charts render with mock data
6. ConnectorCard: Hermes shows `unavailable`; Agnesfallback CLI shows `confirm_required` warning
7. RunDetail: delegation graph + tool calls table visible
8. NotionBase: writeback toggle OFF by default, security warning visible
