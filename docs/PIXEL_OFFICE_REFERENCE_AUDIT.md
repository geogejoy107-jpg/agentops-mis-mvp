# Pixel Office Reference Audit

_Audit date: 2026-06-14_

This document focuses only on pixel office, virtual office and agent-map references for the AgentOps MIS Pixel Operating Map.

The audit goal is narrow: identify visual and interaction patterns that can guide an original AgentOps MIS map. It is not a recommendation to copy another project, import third-party assets, or replace the AgentOps MIS authority model.

## Summary decision

| Question | Answer |
|---|---|
| Best visual inspiration | **Star-Office-UI** for simple readable pixel-office ambience; **pixel-agents-standalone / pixel-agents** for richer future canvas behavior. |
| Best movement logic | **pixel-agents-standalone / pixel-agents** for Canvas loop, pathfinding and session-driven movement; use as reference only. |
| Best state mapping | **openclaw-virtual-office** for simple OpenClaw session-to-presence mapping; **Star-Office-UI** for area-based status mapping. |
| Best license situation | For pure code, Star-Office-UI code is MIT but its assets are non-commercial; OpenClaw virtual office appears simplest conceptually but assets still require verification; no candidate is safe for asset reuse without review. |
| Which project should be forked | **None for v1.3 product implementation.** A separate research fork can be made outside the main repo if needed, but not as the product base. |
| Which should be reference only | Star-Office-UI, openclaw-virtual-office, pixel-agents, pixel-agents-standalone, agent-office, agent-virtual-office, pixel-agents-desktop. |
| Which should be avoided | Claude-Office content/assets for product use; any paid tileset dump; any TV/pop-culture tribute content; any unclear-license asset pack. |

## Important license boundary

Star-Office-UI is useful as a visual and proof-of-concept reference, but it should not be used as the production art base. Its license separates code and assets: code/logic is MIT, while art assets are explicitly non-commercial and must be replaced for commercial use. The safest stance is:

- Keep Star-Office-UI as a legacy/reference demo link.
- Do not copy Star-Office art into `ui/start-building-app`.
- Build original CSS/SVG/React pixel-like shapes for v1.3.
- Commission or generate a fully original AgentOps MIS asset pack only after product direction stabilizes.

## Candidate comparison

| Candidate | URL | License posture | Stack | Active / maturity | Visual inspiration | Movement logic | State mapping | Asset risk | Recommendation |
|---|---|---|---|---|---|---|---|---|---|
| Star-Office-UI | https://github.com/ringhyacinth/Star-Office-UI | Code MIT; art non-commercial; third-party guest sprites require attribution | Flask, static HTML/CSS/JS, Pillow | Mature demo/reference; used by current WorkspaceHome iframe | Strong: approachable pixel office, rooms, status areas | Medium: enough for demo state visualization, not a full engine | Strong: status-to-area concept is very relevant | High | Reference only; keep legacy visualizer |
| openclaw-virtual-office | https://github.com/thx0701/openclaw-virtual-office | Appears MIT; asset provenance still verify | Node.js, static frontend, custom WebSocket, OpenClaw CLI polling | Small, direct, useful | Medium: compact dashboard-like office | Medium: presence updates via WebSocket rather than advanced movement | Strong: online/idle/busy/offline from session age | Medium | Reference only for polling and presence model |
| pixel-agents | https://github.com/pixel-agents-hq/pixel-agents and forks | MIT family, but assets require verification; MetroCity/Donarg references appear in ecosystem | VS Code extension, React, TypeScript, Vite, Canvas 2D | Richer and more complex | Strong future reference: characters, speech bubbles, office zones | Strong: Canvas loop, pathfinding, layout editor, session-driven behavior | Strong for Claude/task/sub-agent state, but source of truth differs | Medium/high | Reference only; do not import engine into v1.3 |
| pixel-agents-standalone | https://github.com/rolandal/pixel-agents-standalone | MIT code; full Donarg tileset purchased separately | Express, ws, React, TypeScript, Vite, Canvas 2D | Rich standalone prototype | Strong future reference | Strongest movement reference among inspected candidates | Medium: maps Claude JSONL events to agents | High for paid tileset workflow | Reference only for future v1.4/v1.5 Canvas/Pixi exploration |
| hootbu/pixel-agents | https://github.com/hootbu/pixel-agents | MIT code; paid tileset not included | VS Code extension, React, TypeScript, Vite, Canvas | Rich feature fork | Strong but playful | Strong | Medium | High | Reference only |
| Claude-Office | https://github.com/W17ant/Claude-Office | Code appears permissive; content/asset/IP risk is high | React, Vite, Express, WebSocket, SQLite/Electron optional | Interesting but branded/tribute-oriented | Medium: office as narrative space | Medium: lifecycle and event flow | Medium | Very high: tribute characters/props/art direction | Avoid for product visuals; reference event lifecycle only |
| agent-office | https://github.com/Pixel-Process-UG/agent-office | MIT | Vite/Node-oriented app, integrations, optional DBs | Early and unstable | Medium | Medium | Medium: assignment, decisions/voting | Medium/high | Reference only |
| agent-virtual-office | https://github.com/k1dav-c/agent-virtual-office | MIT | React 19, Vite, Tailwind, FastAPI, MCP, Hasura, Postgres, RabbitMQ | Heavy but serious | Medium: modern map/control room hybrid | Medium | Strong: MCP status reporting, role inference, audit logs | Low/medium if no assets copied | Reference only for status-reporting and audit concepts |
| pixel-agents-desktop | https://github.com/Dsantiagomj/pixel-agents-desktop | MIT code; inherited asset risks | Electron, React, Vite, TypeScript, Canvas 2D | Desktop-oriented | Medium | Strong | Medium | Medium/high | Reference only for future ambient desktop monitor, not v1.3 web |
| arpdale/virtual-office | https://github.com/arpdale/virtual-office | MIT family, likely pixel-agents fork | Canvas/React family | Fork/reference | Medium | Medium | Medium | Medium/high | Weak evidence; reference only |

## Detailed findings

### Star-Office-UI

**Useful patterns**

- A single office map can function as a live status board rather than a game.
- Agents can be placed in semantically meaningful areas instead of arbitrary decorative rooms.
- A small local server and state JSON can be enough for demos.
- The current AgentOps MIS iframe integration proves users understand the metaphor quickly.

**Borrow**

- Concept of a pixel-office workbench.
- State-to-area mapping.
- Small status badges near agents.
- Optional legacy launch link.

**Reimplement**

- Map layout.
- CSS pixel borders and grid textures.
- Agents as original blocks/sprites.
- Zone click handling and route navigation.

**Avoid**

- Copying art assets, backgrounds, furniture, sprites, posters, buttons, animation frames or rebuilt asset indexes.
- Making Star-Office room semantics the AgentOps MIS IA.
- Treating Star-Office state as the authority ledger.

### openclaw-virtual-office

**Useful patterns**

- Agent status can be inferred from session recency: busy, online, idle, offline.
- A small WebSocket push model is enough for live presence.
- Agent config can map runtime/session identity to UI identity.

**Borrow**

- Presence categories.
- Polling-to-broadcast idea.
- Configurable agent list.

**Reimplement**

- State source should be AgentOps MIS API, not `openclaw sessions list` directly inside the UI.
- Socket strategy can come later; v1.3 can use current live data hooks and refresh.

**Avoid**

- Shelling out from frontend/runtime UI.
- Making OpenClaw the sole source of truth.

### pixel-agents / pixel-agents-standalone family

**Useful patterns**

- Canvas rendering, BFS pathfinding, sprite animation and layout editing are useful for a future polished map.
- Session transcript parsing can produce rich states such as tool use, sub-agent activity and permission waiting.
- Speech bubbles and task panels are helpful for ambient context.

**Borrow**

- Future movement model ideas.
- Agent status legend.
- Tool/sub-agent visualization patterns.
- Agent task panel patterns.

**Reimplement**

- AgentOps MIS run/task/approval mapping.
- Zone model.
- Map component boundaries.
- Operations Bar and Zone Inspector.

**Avoid for v1.3**

- Full Canvas engine.
- Layout editor.
- Transcript watcher as product authority.
- Paid tilesets and large asset dumps.

### Claude-Office

**Useful patterns**

- Lifecycle events can make agent work feel alive.
- WebSocket server + local events can power ambient views.
- Day/night and narrative signals are attractive for demos.

**Avoid**

- Branded tribute art/content.
- Entertainment-first theme.
- Any product use of characters, props, names or generated tribute assets.

## Best-reference awards

| Category | Best candidate | Why |
|---|---|---|
| Visual inspiration | Star-Office-UI | Most legible office metaphor; simple enough to translate into an original control-plane map. |
| Movement logic | pixel-agents-standalone / pixel-agents | Richest pathfinding and Canvas animation reference. |
| State mapping | openclaw-virtual-office + Star-Office-UI | OpenClaw provides clear presence logic; Star-Office gives area mapping. |
| Control-plane seriousness | agent-virtual-office | More explicit identity, status reporting, MCP and audit posture. |
| License safety for code concepts | OpenClaw virtual office and MIT pixel projects | Code may be permissive, but this does **not** make art assets safe. |
| Asset reuse safety | None | No inspected candidate is safe enough for direct asset reuse in the main product. |

## Decision table

| Candidate | Fork? | Reference only? | Avoid? | Reason |
|---|---:|---:|---:|---|
| Star-Office-UI | No | Yes | Assets: yes | Code is useful but art assets are non-commercial. |
| openclaw-virtual-office | No | Yes | No | Great presence model, too narrow to be product base. |
| pixel-agents | No | Yes | Assets: yes | Strong future movement reference, but not the MIS authority model. |
| pixel-agents-standalone | No | Yes | Assets: yes | Strongest movement reference, paid tileset risk. |
| hootbu/pixel-agents | No | Yes | Assets: yes | Rich but too playful/heavy for v1.3. |
| Claude-Office | No | Lifecycle only | Yes for visuals | Product/IP/content risk. |
| agent-office | No | Yes | No | Early-stage; assignment concepts useful. |
| agent-virtual-office | No | Yes | No | Status/audit ideas useful, stack too heavy. |
| pixel-agents-desktop | No | Yes | No | Desktop future reference only. |

## AgentOps MIS mapping

The new Pixel Operating Map should map AgentOps MIS state into zones like this:

| MIS state | Pixel zone | Visual treatment |
|---|---|---|
| Agent registered / idle | Agent Lobby | Agent block at lobby desk, neutral status light |
| Task planned / assigned | Task Hall | Agent near task cards, backlog packets |
| Run active | Run Stream / Runtime Lab | Moving pulse line, active terminal light |
| Tool call active | Tool Workshop | Tool bench sparks, connector packet |
| Waiting approval | Approval Gate | Agent blocked at gate, amber risk badge |
| Evaluation needed / failed | Evaluation Room | Score card, red/amber pass-fail light |
| Memory candidate | Memory Archive | Archive card, review marker |
| Audit event / high risk | Audit Vault | Locked vault, hash-chain bead |
| External base sync | External Base Dock | Dock connector, sync arrows |
| Failure / incident | Incident Corner | Red warning tile, failed-run counter |

## Final recommendation

For v1.3, build an original React/CSS absolute-positioned Pixel Operating Map inside AgentOps MIS. Use Star-Office-UI only as a legacy/reference visualizer, and use pixel-agents/openclaw projects only as design references. Do not fork, import or embed a third-party virtual office product as the main UI.
