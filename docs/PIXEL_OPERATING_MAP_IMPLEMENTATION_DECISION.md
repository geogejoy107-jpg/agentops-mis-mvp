# Pixel Operating Map Implementation Decision

_Audit date: 2026-06-14_

This document is the implementation gate for the AgentOps MIS Pixel Operating Map. It converts the open-source UI reference audit into a concrete v1.3 build decision.

## Final decision

**Build the new Pixel Operating Map inside the AgentOps MIS React/Vite UI using original React/CSS components.**

The map is a visual navigation and live operations layer for AI digital employees. It is not an LLM runtime, not an agent builder, not a cloned virtual office product, and not the authority ledger. AgentOps MIS remains the authority system for agents, tasks, runs, tool calls, approvals, memory, evaluations, audit, runtime connectors, external bases and templates.

## Decision answers

| Question | Decision |
|---|---|
| Should the new map be built inside AgentOps MIS React/Vite UI? | **Yes.** Build it in `ui/start-building-app` as native React components. |
| Should Star-Office-UI remain as legacy/reference visualizer? | **Yes.** Keep it as a legacy/reference link only. Do not make it the main workspace map. |
| Should external assets be copied? | **No.** Do not copy any external art assets unless a future legal/design review confirms they are safe. Star-Office-UI art assets are treated as non-commercial demo/reference only. |
| Should v1.3 use React/CSS absolute positioning, PixiJS, Phaser, SVG or Canvas? | **React/CSS absolute positioning.** It is the lowest-risk option and aligns with the current Vite app. |
| Should v1.3 introduce a complex game engine? | **No.** No PixiJS, Phaser, Tiled map pipeline, asset atlas, pathfinding engine or animation runtime in v1.3. |
| Should any open-source project become the product base? | **No.** Use open-source repositories as references, not as architecture replacements. |

## Why React/CSS absolute positioning for v1.3

React/CSS is the lowest-risk first implementation because it:

- works inside the current AgentOps MIS UI without framework migration;
- keeps route navigation, live data hooks and existing MIS pages in one product surface;
- avoids bundling third-party art, sprite sheets or game-engine dependencies;
- supports clickable zones, labels, status lights, CSS transitions and simple packet animations;
- is easy to review, test and modify as ordinary MIS UI code;
- keeps product direction flexible before investing in original pixel art.

## Rejected v1.3 alternatives

| Alternative | Decision | Reason |
|---|---|---|
| Embed Star-Office-UI iframe as the main map | Reject | It is useful as a demo visualizer, but the product needs native MIS routing and original UI. |
| Fork Star-Office-UI | Reject | Code may be reusable, but assets are non-commercial and the app architecture is not the MIS authority system. |
| Import pixel-agents / pixel-agents-standalone engine | Reject | Movement logic is useful, but Canvas/game engine scope is too large for v1.3. |
| PixiJS | Defer | Good future choice for richer sprite animation after original assets exist. |
| Phaser | Defer/avoid | Too game-oriented for a management information system control plane. |
| SVG-only map | Defer | Good for diagrams, but CSS-positioned React zones are simpler for current dashboard cards and routing. |
| Canvas-only map | Defer | Better for dense animation later; worse for accessible clickable enterprise UI in v1.3. |

## v1.3 scope

Implement:

- route `/workspace/pixel-office`;
- sidebar entry under Client Workspace;
- native `PixelOffice` page;
- original low-fidelity pixel-style operations map using React/CSS;
- clickable zones for Control Tower, Agent Lobby, Task Hall, Runtime Lab, Tool Workshop, Approval Gate, Evaluation Room, Memory Archive, Audit Vault, External Base Dock, Run Stream, Incident Corner and Template Market;
- at least five safe demo/fallback agent sprites when live data is sparse;
- CSS transitions for visible agent movement;
- task card sprites in Task Hall;
- Zone Inspector for selected/hovered zone or agent;
- Operations Bar with active runs, pending approvals, failed quality gates, memory candidates, latest audit, runtime health and external base sync state;
- compact Pixel Office preview on Workspace Home;
- legacy Star Office link only, not a dominant iframe;
- documentation in `docs/PIXEL_OPERATING_MAP_SPEC.md`;
- optional asset replacement plan in `docs/PIXEL_OFFICE_ASSET_REPLACEMENT_PLAN.md`.

Do not implement:

- backend `server.py` changes;
- new runtime semantics;
- Star-Office asset import;
- third-party sprite sheets;
- node_modules or generated caches;
- complex pathfinding;
- third-party marketplace art;
- a replacement for Run Ledger, Audit, Approvals, Tool Calls or Memory pages.

## v1.4 / v1.5 future path

For a richer future implementation:

- commission or generate an original AgentOps MIS pixel asset pack;
- define tile size, perspective, sprite scale, naming convention and attribution policy;
- consider Canvas or PixiJS only after original assets and stable zone semantics exist;
- add optional pathfinding, route trails, multi-agent collaboration clusters and richer tool-call animation;
- introduce map-state replay from the AgentOps MIS run ledger;
- keep formal ledgers and admin pages as the source of truth.

## Star-Office-UI boundary

Star-Office-UI remains useful as:

- legacy visualizer;
- external reference for pixel-office ambience;
- non-commercial local demonstration if separately launched;
- evidence that live agent state can be represented visually.

Star-Office-UI must not be used as:

- the AgentOps MIS product base;
- the main Workspace Home content;
- a source of copied production art assets;
- the source of truth for runs, tasks, approvals, audit or memory.

## Implementation principle

The Pixel Operating Map should answer one product question quickly:

> Where is each AI digital employee working right now, what MIS state caused that placement, and which formal page should the user open to inspect or decide?

That is the v1.3 product boundary.
