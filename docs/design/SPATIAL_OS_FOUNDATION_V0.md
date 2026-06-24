# Spatial OS Foundation v0

> Status: first implementation slice  
> Repository: `geogejoy107-jpg/agentops-mis-mvp`  
> Branch: `design/spatial-os-foundation-v0`  
> Verified starting development commit: `32730808ee227140690f969017df0fd388be63f0`  
> Scope: UI projection, manifests and CI validation only

## Product decision

AgentOps MIS now has two deliberately different rendering tiers:

| Tier | Role | Current implementation |
| --- | --- | --- |
| Basic / Lite | Fast preview, low-performance fallback, accessible DOM view | Existing React/CSS Pixel Office |
| Advanced Spatial | Full map topology, semantic zoom, pathfinding, animated Agents and complete game-art modules | Contract foundation in this branch; game renderer follows in a later slice |

The Basic renderer remains useful and supported. It is no longer presented as proof that palette or shape-token changes alone create a complete game-art template.

## Authority boundary

```text
AgentOps MIS authority objects
        ↓
Spatial Projection Adapter
        ↓
Semantic World Snapshot
        ↓
World Template + Art Kit
        ↓
Renderer Adapter
        ↓
Spatial Portal → formal MIS route / record
```

Spatial OS does not own or mutate workspace, Agent, task, run, approval, prepared action, memory, artifact, evaluation, audit, permission or delivery state. It projects redacted, scoped view models and routes users back to formal MIS surfaces.

## Contract layers

### Semantic world

`contracts.ts` defines stable, renderer-neutral objects:

- `world`
- `district`
- `facility`
- `workspace`
- `landmark`
- `portal`
- live entities such as Agent, task, run, approval, memory, artifact and incident
- authority references and formal routes
- semantic zoom stages
- renderer mount, focus, hit-test and screenshot hooks

### Spatial projection adapter

A projection adapter converts an existing MIS-derived UI model into a `SpatialWorldSnapshot`. The first adapter, `basicPixelProjectionAdapter`, converts the current Pixel Office Agent, task-card and metric models. This proves that Basic and Advanced renderers can share the same semantic snapshot boundary.

### World Template

A World Template owns structural behavior rather than art color:

- projection model;
- tile scale;
- topology and scene hierarchy;
- semantic zoom grammar;
- camera/query/interaction depth;
- renderer capabilities;
- fallback renderer requirements.

The first template is `top-down-rpg-campus`.

### Art Kit

An Art Kit owns complete art-production modules:

- terrain tiles;
- buildings and interiors;
- props and landmarks;
- directional avatar atlases;
- state animations;
- effects and lighting;
- HUD and interaction skin;
- provenance and license metadata.

The first kit is `warm-research-v0`. Its slots are intentionally `planned_first_party`; no commercial game, paid tileset, marketplace pack or reference-image asset is bundled.

### Renderer Adapter

The renderer interface supports:

- mount and unmount;
- load world/template/art kit;
- project snapshot;
- focus semantic node;
- resolve hit target;
- route through a formal portal;
- reduced-motion mode;
- screenshot hooks.

A future Phaser/Tiled renderer can implement this interface, while the existing React/CSS map remains the Basic/Lite implementation.

## Semantic zoom

The v0 template fixes four semantic levels:

| Level | Camera | Query scope | Interaction depth | Example |
| --- | --- | --- | --- | --- |
| 0 | World atlas | Global | Overview | AgentOps World Atlas |
| 1 | District | District | Navigate | Research District |
| 2 | Facility | Facility | Inspect | AI Papers House |
| 3 | Workspace | Workspace | Operate | Claude Research Desk |

Zoom changes camera, query scope, visible object kinds and interaction depth. It is not a CSS scale operation.

## First vertical slice

```text
AgentOps World Atlas
→ Research District
→ AI Papers House
→ Claude Research Desk
→ Run Ledger / Evidence Library formal portals
```

The semantic world also includes a Shared Paper Table, Evidence Garden and Mission Control Kiosk. Every portal resolves to a route registered in the current React router.

## Manifest files

```text
ui/start-building-app/src/app/spatial/manifests/
├── top-down-rpg-campus.v0.json
├── warm-research-art-kit.v0.json
└── research-district.v0.json
```

JSON is the durable data boundary. TypeScript runtime validation fails closed before a malformed manifest can enter a renderer.

## Validation

`scripts/spatial_os_manifest_smoke.py` verifies:

- schema versions and cross-manifest compatibility;
- four-level semantic zoom;
- root/parent/child topology;
- required vertical-slice ancestry;
- portal nodes and existing formal React routes;
- AgentOps MIS authority markers;
- complete game-art asset-slot coverage;
- first-party provenance and project-owned/generated licenses;
- no remote commercial asset URL;
- current Basic Pixel projection bridge and renderer marker.

The smoke is added to the existing deterministic CI suite. The UI build compiles the runtime validators and Basic projection bridge because `PixelOffice.tsx` exercises the catalog and snapshot projection.

## Open-source adoption boundary

Reference ideas: Phaser scenes/cameras/tilemaps, Tiled map metadata and A*-style pathfinding.

No game-engine dependency is added in v0. This sequence deliberately proves the first-party MIS boundary before choosing an engine package. A later reviewed plan must record exact dependency version, license, bundle impact, browser support and rollback.

## Non-goals in v0

- no claim that the Advanced world is visually complete;
- no copied game or marketplace assets;
- no pathfinding runtime yet;
- no tilemap renderer yet;
- no new MIS database tables;
- no change to approvals, auth, runtime, redaction or audit;
- no replacement of formal task/run/memory pages.

## Next implementation slice

1. Add an `AdvancedSpatialSurface` behind an explicit renderer mode boundary.
2. Adopt and pin the selected game renderer after license/bundle review.
3. Create an original Research District terrain/building/interior prototype.
4. Add four-direction Agent movement and deterministic state actions.
5. Implement Level 0 → 1 → 2 → 3 semantic transitions.
6. Capture real desktop and compact screenshots from the Advanced renderer.
7. Keep Basic/Lite as a separately testable fallback.
