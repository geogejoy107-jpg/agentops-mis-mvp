# Codex Handoff — Pixel Office Original Asset Batches

## Baseline

- Repository: `geogejoy107-jpg/agentops-mis-mvp`
- Design branch: `design-ui-visual-system-v3`
- Parent development branch: `codex/agent-gateway-kb-demo`
- Read first: `docs/UI_VISUAL_SYSTEM_V3.md`

## Goal

Replace the CSS fallback gradually with a fully original, commercially usable Pixel Office asset pack. Preserve the current MIS data adapters, bilingual UI, routes, permissions and authority model.

Do not copy, trace, recolor or bundle Star Office, paid tilesets, recognizable game artwork or unclear-license assets.

## Batch A — Character source sheets

Create source definitions and review sheets for these role families:

1. Research / Science
2. Builder / Coding
3. Reviewer / Approval
4. Operations / Runtime
5. Memory / Knowledge
6. Connector / Integration
7. Audit / Security
8. Supervisor / Project Manager

Character contract:

- nominal frame: 32 × 48 px;
- transparent background;
- strict one-pixel dark outline;
- consistent upper-left lighting;
- stable anchor and shadow;
- diverse face, hair and clothing combinations;
- role identity comes from silhouette/accessory, not only recolor;
- animation tags: `idle`, `walk_down`, `walk_up`, `walk_left`, `walk_right`, `work`, `wait`, `alert`.

Suggested image-generation prompt template:

```text
Original pixel-art character sprite sheet for an AI workforce management simulation, orthographic top-down three-quarter view, 32x48 pixel frame, strict one-pixel dark outline, limited midnight navy / warm neutral / cyan / amber palette, professional [ROLE] carrying [ACCESSORY], transparent background, consistent lighting from upper left, clean frame grid for idle, four-direction walk, work, wait and alert. No text, no logo, no copyrighted character, no resemblance to an existing game or Star Office UI, crisp nearest-neighbour pixels.
```

Generated outputs are candidates only. A human must review, clean and approve them before production use.

## Batch B — Room and furniture sheets

Create original props for:

- Control Tower: command desk, triple monitors, KPI signal;
- Agent Lobby: reception, seats, plants;
- Task Hall: kanban wall, dispatch desks;
- Run Stream: server racks, event conduit;
- Runtime Lab: connector racks and terminals;
- Tool Workshop: workbench and tool modules;
- Approval Gate: barrier, amber lamp, waiting bench;
- Evaluation Room: score display and review table;
- Memory Archive: shelves, books, archive workstation;
- External Base Dock: crates, sync terminal, rail;
- Audit Vault: vault door and evidence terminal;
- Incident Corner: failed rack, alarm, recovery kit;
- Template Market: package kiosks.

Environment contract:

- 16 px base tile;
- orthographic perspective matching character sheets;
- isolated transparent props plus optional room concept boards;
- no baked text labels;
- no business state embedded in the artwork.

## Batch C — Build pipeline

Create a deterministic local pipeline under:

```text
art/pixel-office/
public/pixel-office/atlases/
public/pixel-office/scenes/
tools/pixel-office/
```

Required outputs:

```text
characters.png / characters.json
furniture.png / furniture.json
effects.png / effects.json
manifest.json
agentops-campus-v3.json
```

Every manifest entry must include:

- asset ID;
- source path;
- creator or generation method;
- license;
- dimensions;
- animation tags;
- palette version;
- checksum.

## Batch D — Optional renderer spike

Only after the atlas validator passes:

- add a lazy-loaded PixiJS scene behind a feature flag;
- render one room and two agents first;
- keep React responsible for inspector, labels, keyboard access and formal navigation;
- keep the CSS scene as the default fallback;
- do not migrate the whole application into a game engine.

## Required validation

1. `npm run build` passes in `ui/start-building-app`.
2. Existing Pixel Office route smoke passes.
3. Reduced-motion mode works.
4. No secret, database, generated cache or raw customer content is committed.
5. No third-party artwork enters the runtime bundle without explicit provenance and compatible commercial license.
6. A visual review sheet compares full and compact layouts before merge.

## Scope guard

This task is UI/art only. Do not change Agent Plan, runtime execution, approval semantics, security policy, database schema or release gates.
