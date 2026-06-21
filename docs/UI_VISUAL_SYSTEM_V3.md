# AgentOps MIS UI Visual System v3

_Status: Proposed design branch_  
_Baseline branch: `codex/agent-gateway-kb-demo`_  
_Baseline commit: `68459e581b4704e8b9642b3c1653067c7753400d`_

## 1. Scope and milestone boundary

The current development UI is the baseline. This work does **not** restore the old Star Office integration and does not replace the current Workspace/Admin information architecture.

The active product milestone remains v1.5 hardening and release readiness. UI v3 therefore lives on a separate design branch and must remain optional until the execution, permission, CI and release gates are closed.

This visual pass focuses on one bounded surface:

- preserve the current enterprise shell, navigation, bilingual copy, live APIs and formal ledgers;
- improve the optional Pixel Office so it feels intentionally designed rather than like hard-coded rectangles;
- keep every visual state derived from MIS data;
- keep all formal decisions in the normal React MIS pages;
- add no new backend semantics and no third-party production artwork.

## 2. Product experience model

Use a two-layer product experience:

```text
Enterprise MIS shell
  ├─ tasks, agents, runs, approvals, memory, audit, delivery
  └─ formal controls, evidence and decisions

Ambient operations canvas
  ├─ rooms, people, movement and alerts
  └─ orientation, presence, storytelling and navigation
```

The whole product should not become a game. The game-like layer is a visual cockpit above the same authority ledger.

## 3. Reference synthesis

Reference patterns were reviewed across enterprise operations products, AI command-center concepts, management-simulation interfaces, and visual-design galleries such as Pinterest, Dribbble and Behance.

Patterns to borrow:

1. **Command-center hierarchy** — incidents and required actions must dominate decorative metrics.
2. **Management-sim legibility** — a room should be identifiable by its props before its title is read.
3. **Stable character identity** — the same Agent ID resolves to the same silhouette, palette and role accessory.
4. **Evidence-first interaction** — selecting a room or worker exposes the related task/run/approval and opens the formal ledger.
5. **Restrained atmosphere** — use cyan, amber, red, purple and green as semantic signals, not as constant neon decoration.
6. **Model-driven scene** — room composition and spawn points are data, not scattered conditional markup.
7. **Progressive enhancement** — the CSS renderer remains fast and accessible; a sprite/canvas renderer can be added later behind a feature flag.

Patterns to avoid:

- copying Star Office, paid tilesets or recognizable game assets;
- making every dashboard panel pixel art;
- hiding important evidence inside hover-only interactions;
- continuous motion that distracts from approval and incident work;
- fake scene state that disagrees with MIS APIs;
- a second task or approval state machine inside the visualizer.

## 4. Art direction

### Name

**Night-shift Agent Campus**

### Camera

- orthographic top-down / light three-quarter management-sim perspective;
- no mixed true-isometric projection on top of flat rectangular hit areas;
- integer-like edges and nearest-neighbour treatment;
- fixed camera for the React/CSS phase.

### Palette

The current MIS themes remain authoritative. The Pixel Office derives room atmosphere from existing semantic tokens:

| Meaning | Token / fallback |
|---|---|
| active computation | `--mis-cyan` |
| primary operation | `--mis-primary` |
| healthy / passed | `--mis-success` |
| approval / caution | `#FBBF24` |
| incident | `#F87171` |
| memory / orchestration | `--mis-purple` |
| structure / outline | `#020617`, `#0B1020`, slate tones |
| human warmth | restrained wood, skin and plant tones |

### Visual hierarchy

1. pending approval, blocked run and incident;
2. selected Agent and current task;
3. room identity and metric;
4. live packets and ambient movement;
5. environmental decoration.

## 5. Room language

| Zone | Signature props |
|---|---|
| Control Tower | command desk, triple monitors, KPI signal |
| Agent Lobby | reception desk, seats, plants |
| Task Hall | kanban wall, dispatch desks |
| Run Stream | server racks, event conduit |
| Runtime Lab | connector racks, terminals |
| Tool Workshop | workbench, tool modules |
| Approval Gate | barrier, amber lamp, waiting area |
| Evaluation Room | score display, review table |
| Memory Archive | shelves, archive desk, books |
| External Base Dock | crates, sync terminal, loading rail |
| Audit Vault | vault door, evidence terminal |
| Incident Corner | failed rack, alarm and recovery markers |
| Template Market | package kiosks |

## 6. Character system

The zero-asset CSS character is assembled from deterministic layers:

- skin and shadow;
- hair;
- role jacket and accent;
- trousers and shoes;
- role accessory;
- status/risk light.

Role cues:

| Role family | Accessory |
|---|---|
| Research / Memory | notebook or archive book |
| Builder / Connector | laptop or terminal |
| Review / Audit | clipboard or evidence sheet |
| Operations | compact control device |

The CSS character is a fallback, not the final commercial sprite pack. A future atlas should use a 16 px environment grid and approximately 32 × 48 px character frames with idle, walk, work, wait and alert tags.

## 7. Rendering architecture

### Current v3 pass

```text
MIS API data
  → pixelModel adapter
  → PixelOperatingMap
  → typed room scene data
  → CSS room primitives + CSS character fallback
  → React inspector and formal route navigation
```

### Future optional renderer

```text
versioned scene JSON / Tiled map
  + original sprite atlases
  + PixiJS lazy-loaded canvas
  + React overlay for text, accessibility and formal controls
```

Do not migrate the complete MIS shell into PixiJS or Phaser.

## 8. Performance and accessibility gates

- no new network request for decorative art in the CSS fallback;
- no per-frame React state updates;
- `prefers-reduced-motion` disables ambient and character motion;
- inspector and route actions remain keyboard-accessible;
- room labels retain sufficient contrast;
- compact view keeps only essential labels;
- do not add the Pixel Office bundle to unrelated formal pages;
- visualizer failure must not block tasks, approvals, runs or audit.

## 9. Acceptance criteria

- current Workspace/Admin routes and API loaders remain unchanged;
- room identity is understandable without relying only on labels;
- Agent characters have stable identity and visible role cues;
- live MIS state still determines room placement, risk and status;
- every zone still opens its formal MIS route;
- no Star Office or third-party artwork is bundled;
- full and compact layouts remain usable;
- Vite build and existing smoke tests pass before the branch can leave Draft;
- visual comparison screenshots are reviewed at desktop widths before merge.
