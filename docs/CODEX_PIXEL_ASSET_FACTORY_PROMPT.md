# Codex Task — Build the Pixel Office v2 Asset Factory

Copy this task into Codex from the repository root.

---

You are working in `geogejoy107-jpg/agentops-mis-mvp`.

## Objective

Build a repeatable, local-first asset pipeline for the original AgentOps MIS **Night-shift Agent Campus**. Do not copy, trace, bundle or lightly modify Star-Office-UI artwork. Existing Star Office code is reference material only.

The runtime must keep the current CSS-rendered characters and room decor as a fallback. The new factory produces original sprite sheets, atlas metadata and a versioned scene file that can later be rendered by PixiJS.

Read before changing code:

- `docs/PIXEL_OFFICE_V2_ART_DIRECTION_AND_BUILD_PLAN.md`
- `docs/PIXEL_OPERATING_MAP_SPEC.md`
- `docs/PIXEL_OFFICE_REFERENCE_AUDIT.md`
- `docs/PIXEL_OFFICE_ASSET_REPLACEMENT_PLAN.md`
- `ui/start-building-app/src/app/components/pixel/pixelModel.ts`
- `ui/start-building-app/src/app/components/pixel/PixelOperatingMap.tsx`
- `ui/start-building-app/src/app/components/pixel/AgentSprite.tsx`
- `ui/start-building-app/src/app/components/pixel/PixelRoomDecor.tsx`

## Non-negotiable constraints

1. Preserve the MIS as the source of truth.
2. Do not hard-code live agent/task/run state into art assets or scene files.
3. Do not expose secrets.
4. Do not add remote generation APIs to the normal build.
5. The asset build must run locally and deterministically from checked-in source inputs.
6. Every runtime asset must have provenance and licence metadata.
7. Keep the existing CSS fallback functional.
8. Do not break the current Vite build.

## Deliverables

### 1. Directory structure

Create:

```text
art/pixel-office/
  README.md
  palettes/
    night-shift-campus.json
  characters/
    sources/
    definitions/
  furniture/
    sources/
    definitions/
  rooms/
    sources/
  effects/
    sources/

public/pixel-office/
  atlases/
  scenes/
  manifest.json

tools/pixel-office/
  build-assets.mjs
  validate-assets.mjs
  build-scene.mjs
  lib/
```

Do not commit generated binary files unless they are small, original placeholders required by the demo. Source definitions and scripts are mandatory.

### 2. Palette contract

Create a palette JSON containing named colours for:

- outline
- deep shadow
- wall
- floor cold
- floor warm
- wood light / mid / dark
- skin tone set
- hair tone set
- role blue / purple / teal / amber / rose / slate
- active cyan
- approval amber
- incident red
- success green
- memory purple

The validator must reject colours outside the approved palette unless explicitly whitelisted.

### 3. Character definition format

Create a JSON schema or Zod-compatible TypeScript schema for layered character definitions:

```json
{
  "id": "builder_01",
  "frame": { "width": 32, "height": 48 },
  "layers": {
    "skin": "skin_03",
    "hair": "short_02",
    "jacket": "builder_blue",
    "trousers": "navy",
    "accessory": "laptop"
  },
  "animations": {
    "idle": [0, 1],
    "walk_down": [2, 3, 4, 5],
    "walk_up": [6, 7, 8, 9],
    "walk_left": [10, 11, 12, 13],
    "walk_right": [14, 15, 16, 17],
    "work": [18, 19, 20, 21],
    "wait": [22, 23],
    "alert": [24, 25]
  }
}
```

Support stable palette/accessory selection from Agent ID.

### 4. Original placeholder generator

Implement a deterministic local generator that produces a deliberately simple, original placeholder set from geometric pixel primitives.

Minimum output:

- 8 base character archetypes
- 6 skin tones
- 8 hair variants
- 6 role jackets
- 7 accessories
- 13 room icons
- 24 furniture props
- active / approval / incident effects

The generator may use SVG rectangles converted to PNG, a pure JavaScript PNG library, or another lightweight local approach. Avoid a native dependency unless absolutely necessary. If a dependency is added, explain it in the README.

Generated placeholders must not imitate a specific commercial game or Star Office sprite.

### 5. Sprite atlas output

Output:

```text
public/pixel-office/atlases/characters.png
public/pixel-office/atlases/characters.json
public/pixel-office/atlases/furniture.png
public/pixel-office/atlases/furniture.json
public/pixel-office/atlases/effects.png
public/pixel-office/atlases/effects.json
```

Atlas JSON must include:

- frame rectangle
- source dimensions
- animation tags
- pivot / anchor
- asset ID
- palette version
- checksum

Use transparent PNGs and no interpolation.

### 6. Scene file

Create:

`public/pixel-office/scenes/agentops-campus-v2.json`

It must contain:

- `sceneVersion`
- tile size
- map dimensions
- zones
- room themes
- paths
- spawn points
- props
- interaction hit areas
- metric bindings
- formal MIS routes

Migrate geometry from `PIXEL_ZONES` without changing current routes. Add a parser and validation test, but do not remove the existing TypeScript definitions until the new loader is proven.

### 7. Asset manifest and provenance

Create `public/pixel-office/manifest.json` with:

```json
{
  "manifestVersion": "1.0.0",
  "artDirection": "night-shift-agent-campus",
  "paletteVersion": "1.0.0",
  "assets": []
}
```

Every asset entry requires:

- ID
- category
- source path
- runtime path
- dimensions
- licence
- creator/method
- checksum
- tags

Validator must fail on missing licence or provenance.

### 8. Validation

`node tools/pixel-office/validate-assets.mjs` must check:

- file existence
- frame dimensions
- no frame overlap outside atlas rules
- alpha/transparency
- palette compliance
- manifest completeness
- animation tags present
- duplicate asset IDs
- scene routes belong to an approved MIS route list
- no filenames or metadata suggesting copied Star Office production assets

### 9. Build commands

Add scripts to the appropriate package or root documentation:

```text
pixel:build
pixel:validate
pixel:scene
pixel:all
```

The build must be deterministic. Running it twice without source changes must produce identical checksums.

### 10. Optional PixiJS spike

Only after the asset pipeline and validation pass, create a small isolated `PixelSceneCanvas` spike behind a feature flag.

Requirements:

- lazy-loaded
- no impact on the formal dashboard bundle when disabled
- renders one room and two animated characters
- React remains responsible for inspector/accessibility/navigation
- CSS renderer remains default
- do not migrate the entire map in this task

## Art production matrix

Prepare source templates for these role packs:

| Pack | Roles | Accessory cues |
|---|---|---|
| Build | Coder, Builder, DevOps | laptop, terminal, wrench |
| Research | Researcher, Scientist, Analyst | notebook, tablet, chart |
| Governance | Reviewer, Approver, Auditor | clipboard, badge, evidence folder |
| Memory | Curator, Librarian | book, archive box |
| Integration | Connector, Sync Operator | antenna terminal, cable case |
| Management | PM, Supervisor, Control Tower Operator | headset, planning board |

Prepare furniture packs:

| Room | Minimum props |
|---|---|
| Control Tower | command desk, 3 monitors, KPI wall, chair |
| Agent Lobby | reception desk, sofa, plant, notice board |
| Task Hall | kanban wall, dispatch desk, task terminal |
| Runtime Lab | server rack, terminal, cable tray |
| Tool Workshop | workbench, tool modules, test console |
| Approval Gate | barrier, warning lamp, holding bench |
| Evaluation Room | score screen, review table, trophy |
| Memory Archive | shelves, archive boxes, reading desk |
| External Dock | crates, sync tower, loading rail |
| Audit Vault | vault door, evidence terminal, security light |
| Incident Corner | damaged rack, alarm, recovery kit |
| Template Market | 3 kiosks, signs, package boxes |

## Batch image-model prompt templates

Do not call an external image API from the repository. Put these prompts in `art/pixel-office/README.md` for a human-operated generation pass.

### Character sheet prompt

```text
Original pixel-art character sprite sheet for a dark futuristic office management game, orthographic top-down three-quarter view, 32x48 pixel frame, strict 1-pixel dark outline, limited approved palette, readable human proportions, [ROLE], [ACCESSORY], neutral professional clothing, transparent background, frames arranged in a clean grid: idle 2, walk down/up/left/right 4 each, work 4, wait 2, alert 2. No text, no logos, no copyrighted characters, no resemblance to an existing game or Star Office UI, crisp nearest-neighbour pixels, consistent lighting from upper left.
```

### Furniture sheet prompt

```text
Original pixel-art furniture sprite sheet for the AgentOps MIS Night-shift Agent Campus, orthographic top-down three-quarter view, 16px tile grid, strict 1-pixel dark outline, limited midnight navy / warm wood / cyan / amber palette, [ROOM] prop set containing [PROP_LIST], transparent background, each object isolated with consistent anchor and lighting, no text, no logos, no copyrighted game assets, crisp nearest-neighbour pixels.
```

### Room concept prompt

```text
Original pixel-art management-sim room concept for AgentOps MIS, orthographic top-down three-quarter camera, Night-shift Agent Campus art direction, [ROOM_NAME], readable functional storytelling through [SIGNATURE_PROPS], dark navy walls, warm wood furniture, cyan active systems, amber safety lights, plants and lived-in details, no characters, no text labels, no logos, no copyrighted game resemblance, 16px tile discipline, crisp pixel clusters.
```

Human review must select and clean generated concepts before runtime use. Generated image output is reference/source material, not automatically approved production art.

## Acceptance criteria

- The current app builds with the CSS fallback.
- `pixel:all` succeeds twice with identical hashes.
- Scene JSON validates.
- At least one generated character and one furniture atlas can be loaded by a small test.
- All assets have provenance/licence entries.
- No Star-Office-UI art is bundled.
- Existing MIS routes and business state mapping are unchanged.
- A short report lists created files, build commands, test results and remaining manual art work.

---

Do not broaden the task into marketplace, agent runtime or backend work. This task is only the original Pixel Office v2 art and scene pipeline.
