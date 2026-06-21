# AgentOps MIS Pixel Office v2

## 1. Product role

Pixel Office is not a second MIS and it is not the source of truth. It is a game-like live visualizer over the AgentOps MIS ledger.

Authoritative state remains:

- agents
- tasks
- runs
- tool calls
- approvals
- evaluations
- memories
- audit events
- runtime connectors

The scene converts these objects into rooms, characters, task cards, alerts and movement. Every room must open the corresponding formal MIS page.

## 2. Why the first integration looked hard-coded

The current implementation already maps MIS entities into zones, but the visual layer is still dominated by percentage-positioned rectangles and generic CSS blocks. This creates four problems:

1. Rooms have labels but little environmental storytelling.
2. Character silhouettes do not communicate role, activity or personality.
3. Scene geometry, data mapping and visual decoration are mixed in component code.
4. There is no stable art bible or asset contract, so each new contribution drifts in style.

The fix is not to copy Star-Office-UI more deeply. The fix is to keep the MIS data contract and replace the visual layer with an original, data-driven scene system.

## 3. Chosen visual direction

### Style name

**Night-shift Agent Campus**

### Camera

- Orthographic top-down / three-quarter management-sim view.
- Do not mix true isometric projection with flat rectangular MIS hit areas in the same scene.
- Use integer scaling and nearest-neighbour rendering.
- Default camera is fixed; later versions may support room focus and 0.75x / 1x / 1.25x zoom.

### Mood

- Dark midnight operations campus.
- Warm wood, amber safety lighting and living plants soften the technical blue/purple MIS palette.
- Cyan represents active computation.
- Amber represents approval and caution.
- Red represents incidents.
- Purple represents memory, audit and orchestration.
- Green represents healthy completion.

### Visual hierarchy

1. Characters and live alerts.
2. Functional room identity.
3. Current task / run evidence.
4. Environmental decoration.
5. Background grid and atmospheric effects.

The room should look understandable before its text label is read.

## 4. Pixel art bible

### Base grid

- Environment tile: 16 x 16 px.
- Furniture footprint: multiples of 16 px.
- Character frame: 32 x 48 px.
- Small status icon: 8 x 8 or 12 x 12 px.
- Export scale: source at 1x; display at integer multiples only.

### Character animation set

Each base character should include:

- idle: 2 frames
- walk down: 4 frames
- walk up: 4 frames
- walk left: 4 frames
- walk right: 4 frames
- work / type: 4 frames
- inspect / read: 2 frames
- wait / approval: 2 frames
- alert / failure: 2 frames

### Character identity system

Identity is assembled from independent layers:

- skin tone
- hair shape and colour
- jacket / role colour
- trousers
- accessory
- runtime badge
- risk/status light

Recommended role accessories:

- Researcher: notebook or tablet
- Builder: laptop or tool case
- Reviewer: clipboard
- Memory Curator: book / archive box
- Connector: antenna terminal
- Auditor: evidence folder / badge
- Operator: headset
- Scientist: lab tablet

The same Agent ID must always resolve to the same palette and accessory unless the user explicitly changes its avatar.

### Room identity

- Control Tower: triple monitors, KPI wall, command desk.
- Agent Lobby: reception desk, lounge seats, plants.
- Task Hall: kanban wall, dispatch desks.
- Run Stream: server racks and animated event conduit.
- Runtime Lab: connector racks, terminal stations.
- Tool Workshop: workbench and tool modules.
- Approval Gate: safety barrier, warning lamp and holding area.
- Evaluation Room: score display and review desk.
- Memory Archive: shelves, books and archive workstation.
- External Base Dock: crates, sync terminal and loading rail.
- Audit Vault: secure vault door and evidence terminal.
- Incident Corner: warning console, broken server and recovery markers.
- Template Market: small stalls / kiosks for packages.

## 5. Rendering architecture

### Phase A — current branch

Use original React/CSS pixel primitives as a zero-asset fallback.

Advantages:

- no dependency on copied Star Office artwork
- fast iteration
- works before the art pipeline is ready
- room identity can be reviewed immediately
- preserves existing React interaction and routes

This phase includes:

- `PixelCampusBackdrop.tsx`
- `PixelRoomDecor.tsx`
- role-aware `AgentSprite.tsx`
- MIS-driven zones and indicators

### Phase B — asset-backed scene

Use a hybrid renderer:

- PixiJS renders tile layers, sprites, particles and character animation.
- React renders inspector panels, accessible buttons, labels and formal MIS navigation.
- Tiled JSON stores floor, walls, prop positions, collision areas and spawn points.
- A sprite atlas stores characters and furniture.

Do not rewrite the whole MIS in a game engine. The canvas is only the scene surface.

### Phase C — large live office

Move to the PixiJS scene when one or more of these are true:

- more than roughly 30–40 visible agents
- many animated props or particles
- path-following and room transitions are enabled
- camera pan / zoom is enabled
- sprite atlas assets replace CSS primitives

## 6. Non-hardcoded scene contract

Create a versioned scene document under:

`public/pixel-office/scenes/agentops-campus-v2.json`

Suggested shape:

```json
{
  "sceneVersion": "2.0.0",
  "tileSize": 16,
  "map": {
    "width": 100,
    "height": 62,
    "projection": "orthographic"
  },
  "zones": [
    {
      "id": "runtime_lab",
      "route": "/admin/connectors",
      "rect": { "x": 6, "y": 25, "w": 23, "h": 18 },
      "roomTheme": "runtime_lab",
      "spawnPoints": ["terminal_a", "terminal_b"],
      "metricBinding": "runtimeHealth"
    }
  ],
  "paths": [],
  "props": [],
  "spawnPoints": [],
  "interactions": []
}
```

Rules:

- Components render scene data; they do not own scene geometry.
- MIS adapters decide target room and status; art components do not infer business truth.
- Routes remain explicit and validated.
- Unknown zone types fall back to a safe generic room.
- Scene files are versioned and can migrate independently from the MIS schema.

## 7. Data-to-scene mapping

```text
MIS API / local SQLite
        ↓
Pixel view adapter
        ↓
Scene state
        ↓
room metrics + agent targets + alerts + task cards
        ↓
React/Pixi renderer
```

Examples:

- `run.status=running` → agent walks to Runtime Lab / Run Stream.
- `approval.status=pending` → agent waits at Approval Gate.
- failed quality gate → Evaluation Room flashes red and Incident Corner receives an alert.
- approved memory candidate → Memory Curator moves to Memory Archive.
- external sync active → Connector moves to External Base Dock.

No fake visual state should contradict the formal MIS pages.

## 8. Interaction rules

- Single click: select room or character and update inspector.
- Double click: open the formal MIS route.
- Hover: show name, runtime and current status.
- Alert marker: opens the exact approval, run or incident record.
- Room focus: later camera feature; never hide formal navigation.
- Reduced motion: disable walking/bobbing/particles under `prefers-reduced-motion`.

## 9. Asset pipeline

Source files:

```text
art/pixel-office/
  characters/
  furniture/
  rooms/
  effects/
  palettes/
```

Runtime files:

```text
public/pixel-office/
  atlases/
    characters.png
    characters.json
    furniture.png
    furniture.json
  scenes/
    agentops-campus-v2.json
  manifest.json
```

Every asset entry must include:

- asset ID
- source file
- creator / generation method
- licence
- palette version
- dimensions
- animation tags
- checksum

No Star-Office-UI asset may silently become a production asset. Reference code and visual ideas may be studied, but final commercial assets must be original or have a compatible, recorded licence.

## 10. Performance rules

- Load atlases once and cache by manifest version.
- Group sprites by atlas/texture.
- Avoid per-frame React state updates.
- Update scene state from events rather than polling every animation frame.
- Keep text and inspector UI in React; do not redraw it as canvas text every frame.
- Use culling when camera movement is introduced.
- Pause animation when the tab is hidden.
- Provide low-motion and low-resolution modes.

## 11. Definition of done for v2 visual pass

- Every functional zone is visually recognisable without relying only on its title.
- Agent characters look human, have role cues and stable identities.
- Current MIS data still drives all room metrics, agent positions and alerts.
- No production asset is copied from Star-Office-UI.
- Compact and full layouts remain usable.
- The formal MIS page is reachable from every room.
- The map stays optional and does not slow down the core dashboard route.
- Build and accessibility checks pass.
