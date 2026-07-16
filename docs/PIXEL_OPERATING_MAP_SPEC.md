# Pixel Operating Map Spec

_Status: v1.3 implementation spec_

The Pixel Operating Map is a native AgentOps MIS React/Vite page that visualizes AI digital employees moving between MIS work zones. It is an orientation and navigation layer, not an LLM runtime, not an agent builder, and not a replacement for formal MIS ledgers.

## Product boundary

AgentOps MIS remains the authority system for agents, tasks, runs, tool calls, approvals, memory, evaluations, audit, runtime connectors, external bases and templates. The pixel map only renders and routes from that state.

## v1.3 implementation decision

| Question | Decision |
|---|---|
| UI host | `ui/start-building-app` React/Vite app |
| Route | `/workspace/pixel-office` |
| Rendering | Original React/CSS absolute positioning |
| External assets | None copied into the product UI |
| Star-Office-UI | Optional legacy/reference link only through `VITE_STAR_OFFICE_URL` |
| Game engine | None for v1.3; no PixiJS, Phaser, Tiled map pipeline or sprite atlas |
| Backend changes | None required |

## User jobs

1. See where each AI digital employee is working right now.
2. Understand which MIS state caused that placement.
3. Click a zone to inspect it.
4. Open the formal MIS page for decisions and evidence.
5. Spot active runs, pending approvals, failed gates, memory candidates, audit activity and external base sync state from one operating floor.

## Routes and zone contract

| Pixel zone | Target route | Formal MIS page |
|---|---|---|
| Control Tower | `/admin` | Control Tower dashboard |
| Agent Lobby | `/workspace/agents` | AI Employees / Agent Registry |
| Task Hall | `/workspace/tasks` | Task Hall / My Tasks |
| Runtime Lab | `/workspace/connectors` | Runtime Connectors |
| Tool Workshop | `/workspace/tool-calls` | Tool Call Ledger |
| Approval Gate | `/workspace/approvals` | Approvals Inbox |
| Evaluation Room | `/workspace/evaluations` | Evaluation Room |
| Memory Archive | `/workspace/memory` | Memory Library |
| Audit Vault | `/workspace/audit` | Audit Center |
| External Base Dock | `/workspace/external-bases/notion` | External Base Dock / Notion Base |
| Run Stream | `/workspace/runs` | Run Ledger |
| Incident Corner | `/workspace/runs` | Failed/blocked run inspection |
| Template Market | `/workspace/templates` | Template Switching / Template Market |

## State-to-zone mapping

| MIS state signal | Target zone |
|---|---|
| Agent exists but no active work | Agent Lobby |
| Planned or assigned task | Task Hall |
| Running or executing run | Runtime Lab |
| Run timeline inspection | Run Stream |
| Tool call execution | Tool Workshop |
| Pending approval or paused high-risk action | Approval Gate |
| Completed/evaluating/pass/fail quality state | Evaluation Room |
| Memory candidate or stale memory | Memory Archive |
| Audit or evidence event | Audit Vault |
| Syncing or dry-run external base state | External Base Dock |
| Failed/blocked/error/unavailable | Incident Corner |

## Data sources

The first implementation reads existing frontend data loaders: `loadDashboard`, `loadAgents`, `loadTasks`, `loadApprovals`, `loadRuns`, `loadMemories` and `loadAudit`. When the backend is unavailable, the page falls back to demo-safe mock data from `mockData.ts`.

## Component map

| Component/file | Responsibility |
|---|---|
| `components/pages/PixelOffice.tsx` | Page shell, live-data loading, fallback snapshot, route opening, asset boundary copy |
| `components/pixel/pixelModel.ts` | Zone definitions, state mapping, derived agents/tasks/metrics |
| `components/pixel/PixelOperatingMap.tsx` | Absolute-positioned map scene, zone selection, compact/full modes |
| `components/pixel/PixelZone.tsx` | Clickable room/zone tile |
| `components/pixel/AgentSprite.tsx` | Original CSS pixel-style agent block with status/risk light |
| `components/pixel/TaskCardSprite.tsx` | Pixel task-card chips inside Task Hall |
| `components/pixel/ZoneInspector.tsx` | Selected zone/agent inspector and route actions |
| `components/pixel/OperationsBar.tsx` | Active run/approval/gate/memory/runtime/incident summary |
| `components/pages/EvaluationRoom.tsx` | Lightweight quality gate review page for `/workspace/evaluations` |

## Interaction model

- Click a zone once to inspect it.
- Double-click a zone to navigate to the formal MIS route.
- Click an agent to inspect that agent and its mapped MIS state.
- Click a task card sprite to open formal task detail.
- Refresh from the Operations Bar to reload live state.
- Use Workspace Home preview to open the full Pixel Office page.

## Visual language

The v1.3 visual treatment is intentionally low fidelity: CSS grid floor texture, clipped pixel rooms, block-style agents, status/risk lights, packet/pulse animations and no external tilesets. No copied backgrounds, sprites, furniture, logos or decoration assets are used.

## Star-Office-UI boundary

Star-Office-UI can remain useful as a legacy local visualizer, visual inspiration, non-production demo reference and optional external link. It must not be used as the AgentOps MIS authority layer, the main Workspace Home content, a source of copied production art, or a replacement for runs, approvals, memory, audit, evaluations or tool-call ledgers.

## Acceptance checklist

- `/workspace/pixel-office` renders as a native AgentOps MIS page.
- Sidebar includes Pixel Office entry.
- Workspace Home no longer embeds a dominant Star-Office iframe.
- Pixel map zones are clickable and route into formal MIS pages.
- Agents are placed from AgentOps MIS state, with demo-safe fallback.
- Task cards appear in Task Hall.
- Zone Inspector displays selected zone/agent details.
- Operations Bar displays active runs, pending approvals, failed gates, memory candidates, runtime health, incident count and audit/base signals.
- `/workspace/evaluations` exists as the Evaluation Room target.
- No external assets are committed.
- Backend core logic is unchanged.

## Future v1.4/v1.5 path

After v1.3 validation, the richer map can add an original AgentOps MIS pixel asset pack, Canvas/PixiJS renderer after asset ownership is clear, pathfinding, route trails, run-ledger replay mode, multi-agent collaboration clusters, connector-specific packet animations, richer evaluation overlays and map-state audit snapshots.
