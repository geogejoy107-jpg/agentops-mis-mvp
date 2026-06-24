# Agent Plan — Spatial Agent Art Dual Track v0

- Plan ID: `plan-spatial-agent-art-dual-track-v0-2026-06-24`
- Repository: `geogejoy107-jpg/agentops-mis-mvp`
- Latest development branch verified: `codex/agent-gateway-kb-demo`
- Latest development commit verified: `896ee1aa288f2733aa9c147ced6a9c2d5c8622d0`
- Parent feature branch: `design/spatial-research-district-art-v1`
- Parent feature commit: `33fccf0f799383eafcb1b195af2886319cd61935`
- Execution branch: `design/agent-art-dual-v0`
- Risk level: `low`
- Approval required: `false`

## Task understanding

Produce two original, usable Agent art assets after reviewing open-source game code and asset pipelines:

1. **Village life-sim Agent** — a full-body top-down character sheet with warm, readable, domestic pixel-art proportions. This is the Agent representation for the Stardew-like world template. It must not carry the compact glyph as a floating badge; the character itself is the Agent.
2. **Industrial unit Agent** — a compact top-down machine/unit sheet with silhouette-first, modular, limited-palette construction inspired by Mindustry's production pipeline and unit readability. This is an alternative Agent renderer, not a status icon attached to the life-sim character.

Both assets represent the same MIS Agent identity and may share identity palette inputs, but a renderer chooses exactly one visual body. Status and risk remain separate channels.

## Required reading and references

- `docs/project/PROJECT_STATE.md`
- `docs/project/DECISIONS.md`
- `docs/project/BACKLOG.md`
- `docs/project/HANDOFF.md`
- `AGENTS.md`
- `PROJECT_SPEC.md`
- `AGENT_WORKFLOW.md`
- `BASE_INDEX.md`
- `docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md`
- current Spatial OS foundation and Agent identity implementation
- user-provided Art v1–v3 screenshots and critique

External reference study:

- `Anuken/Mindustry` — raw assets separated from packed assets, generated `Tex`/`Icon` classes, `tools:pack` sprite packing, compact silhouette-first units; GPL-3.0. Reference-only method adaptation. No source sprite is copied.
- `mapeditor/tiled` — tileset/object-layer/world organization and metadata-driven map assets. Reference-only tooling/design method.
- `MonoGame/MonoGame` — open-source cross-platform 2D rendering framework used by games including Stardew Valley; reference for integer-scale sprite-sheet rendering, not for copying art.
- `arianne/stendhal` — open-source top-down RPG world with towns, buildings, NPCs and tile-based traversal; reference for map/character separation and readable top-down proportions. No sprite is copied.

## Relationship classification

- `updates`: Spatial Agent Identity v0 and Spatial Research District Art v1
- `supersedes`: the current hybrid where a generic body carries the compact glyph as a floating badge
- `duplicate_of`: none
- `conflicts_with`: none confirmed

## Proposed outputs

- `ui/start-building-app/src/assets/spatial/agents/village-research-agent-v0.png`
- `ui/start-building-app/src/assets/spatial/agents/industrial-research-unit-v0.png`
- `ui/start-building-app/src/assets/spatial/agents/village-research-agent-v0.json`
- `ui/start-building-app/src/assets/spatial/agents/industrial-research-unit-v0.json`
- `docs/design/SPATIAL_AGENT_ART_DUAL_TRACK_V0.md`
- deterministic preview/contact-sheet evidence

## Asset specifications

### Village life-sim Agent

- logical frame: `32 × 48`
- sheet: four directions × four frames
- directions: south, west, east, north
- frames: idle, step-a, passing, step-b
- additional actions in metadata: read, type, carry, wait
- no floating identity badge
- original warm-cloth/skin/hair/paper palette
- readable head/torso/legs and directional asymmetry at 1×

### Industrial unit Agent

- logical frame: `32 × 32`
- sheet: eight directions × two activity frames
- silhouette communicates role before color
- team/identity palette occupies an internal material band, not an overlaid badge
- separate status socket reserved for runtime state
- original modular chassis, sensor, manipulator and data-cell forms

## Execution steps

1. Audit the current glyph/body split and define the renderer-choice rule.
2. Study the cited repositories' asset organization, sprite packing and scale conventions.
3. Create both assets as first-party transparent PNG sheets with integer-aligned pixels.
4. Create machine-readable metadata for dimensions, frames, direction order, identity input and provenance.
5. Generate contact sheets at 1× and enlarged integer scales.
6. Validate transparency, frame bounds, palette count, duplicate-frame absence and deterministic hashes.
7. Commit the assets and documentation to the isolated branch.
8. Record exact commit and evidence; do not claim integration into the Advanced route yet.

## Authority and licensing boundary

- MIS remains authoritative for Agent identity, role, runtime, task, run, status, risk and permissions.
- Art assets are a renderer projection only.
- No Mindustry, Stardew Valley, Stendhal or marketplace pixels are copied, traced or redistributed.
- All output PNGs are `PROJECT_OWNED`, `first_party` and generated specifically for this repository.

## Verification plan

- PNG dimensions and transparency checks
- all frame rectangles inside sheet bounds
- exact direction/frame counts
- deterministic SHA-256 manifest
- no remote URLs or third-party image bytes
- palette and silhouette checks
- visual contact sheet for both tracks

## Rollback plan

Delete the two asset pairs and this design note from the isolated branch. No MIS schema, route, authority object or current renderer behavior is changed.

## Plan verification

Verified before execution:

- exact repository, development head, parent feature head and execution branch established from GitHub;
- required project files and open-source adoption boundary read from the exact development head;
- current problem confirmed: the compact glyph is being used as an attachment to a separate generic body rather than as an alternative Agent renderer;
- work is limited to first-party art assets, metadata and documentation;
- no high-risk plan, external write, credential, runtime or customer-data action is involved.

Plan status: `verified`.
