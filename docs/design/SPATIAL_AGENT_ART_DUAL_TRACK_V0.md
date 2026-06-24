# Spatial Agent Art Dual Track v0

> Status: first-party asset study  
> Branch: `design/agent-art-dual-v0`  
> Parent: `design/spatial-research-district-art-v1@33fccf0f799383eafcb1b195af2886319cd61935`

## Correction

The compact geometric Agent glyph must not be attached to a separate generic person as a floating identity badge. It is an **alternative Agent renderer**.

A world template chooses one body renderer:

```text
AgentOps MIS Agent identity
        ↓
Spatial Agent visual identity
        ↓
world-template renderer choice
        ├── village-life-sim → full character
        └── industrial-unit → compact machine unit
```

The two bodies may use the same stable Agent identity inputs and palette family. They do not appear simultaneously as body plus badge. Status, risk and approval state remain independent channels.

## Asset A — Village Research Agent

Files:

- `src/assets/spatial/agents/village-research-agent-v0.png`
- `src/assets/spatial/agents/village-research-agent-v0.json`

Contract:

- frame: `32 × 48`;
- sheet: `192 × 192`;
- directions: south, west, east, north;
- actions: idle, three walk phases, read, type;
- full-body character with readable head, hair, glasses, coat, satchel, hands and feet;
- no floating identity glyph;
- original project-owned pixels.

The art direction borrows only high-level methods from open-source top-down engines and games: integer-scale sprite sheets, readable NPC proportions, map/character separation and metadata-driven action ordering. It does not copy Stardew Valley, Stendhal, marketplace or tutorial pixels.

## Asset B — Industrial Research Unit

Files:

- `src/assets/spatial/agents/industrial-research-unit-v0.png`
- `src/assets/spatial/agents/industrial-research-unit-v0.json`

Contract:

- frame: `32 × 32`;
- sheet: `256 × 96`;
- directions: eight compass directions;
- states: idle, active, blocked;
- silhouette-first modular chassis with sensor, manipulators, exhaust, identity material band and state socket;
- no person body and no floating glyph;
- original project-owned pixels.

The design adapts Mindustry's asset-production ideas only: raw assets separated from packed output, atlas-friendly naming, compact silhouette recognition and limited material palettes. It does not copy Mindustry unit geometry, sprites, icons or team marks.

## Open-source reference record

### Mindustry / Arc

- Reference: `Anuken/Mindustry`, `Anuken/Arc`.
- Borrowed idea: compact unit silhouettes, raw/packed asset separation, generated atlas references and integer-aligned 2D rendering.
- First-party MIS module touched: optional Spatial Agent renderer assets only.
- Authority boundary preserved: MIS still owns Agent identity, runtime, task, run, approval, status, risk and permissions.
- Verification: PNGs are project-authored and metadata declares `copiedPixels: false`.

### MonoGame / Stendhal / Tiled

- Reference: `MonoGame/MonoGame`, `arianne/stendhal`, `mapeditor/tiled`.
- Borrowed idea: sprite-sheet/action metadata, top-down character/world separation, integer scaling and map object organization.
- First-party MIS module touched: optional Spatial Agent renderer assets only.
- Authority boundary preserved: the asset sheet cannot mutate or become authority for an MIS record.
- Verification: no third-party image byte or remote production asset URL is included.

## Selection rule

| World template | Agent body renderer | Use case |
| --- | --- | --- |
| warm research village | `village-life-sim` | human-readable social/workspace world |
| industrial command network | `industrial-unit` | dense automation, runtime and production world |
| Basic/Lite sidebar | compact glyph or thumbnail derived from the selected body | roster/navigation only |

The Basic/Lite sidebar may show a compact thumbnail. It must not imply that a second icon is physically attached to an in-world Agent.

## Verification

Expected hashes:

- village PNG: `7c5af2207046c9458afc0e6735986600cbe0ffdb1d033a9372c6143286242cb0`;
- industrial PNG: `cea70e84fa98526c6f4001a68ff9763168aa39d4cc75490798671352d607d098`.

Both sheets contain 24 non-empty frames, use transparent backgrounds and keep status/risk semantics outside the identity silhouette.

## Non-goals

- no Advanced route integration in this asset-only slice;
- no claim that the complete Research District world is finished;
- no commercial-game style or asset replication;
- no change to MIS data, routes, permissions or authority state.
