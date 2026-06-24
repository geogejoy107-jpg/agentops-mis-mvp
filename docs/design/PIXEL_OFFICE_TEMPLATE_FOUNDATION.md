# Pixel Office Template Foundation

> Status: draft implementation on `design/pixel-office-template-foundation`  
> Starting base: `codex/agent-gateway-kb-demo` at `cce739415c2e795e824b46ef072ebc9ec6cc36bc`  
> Scope: Pixel Office only; no backend or authority semantics change

## Objective

Rebuild Pixel Office as a reusable spatial UI foundation. Business entities, floor structure, room composition, camera behavior and art direction remain separable so later releases can replace the visual style without rewriting MIS routing or state mapping.

## Relationship to existing work

- **updates** Draft PR #7: retain its useful typed-scene and original-art principles while implementing on the active Pixel Office branch.
- **supersedes** Draft PR #2 as the active implementation line.
- **does not replace** Draft PR #11, which covers the broader UI-v2 shell and Mission Control.
- **updates** the Notion proposal `Proposal｜多层像素化工作区 UI：楼层 / 场景式交互面板`.

## Architecture

```text
MIS records and live snapshot
        ↓
pixelModel view model
        ↓
pixelOfficeScene: floors, rooms, semantic props
        ↓
pixelOfficeTheme: materials, tones, character palettes, effects
        ↓
PixelOperatingMap: camera, focus, navigation, compact mode
        ↓
formal MIS route / authoritative record
```

The scene model describes *what exists*. The theme registry describes *how it looks*. The operating map describes *how the user navigates it*.

## Current layers

| Layer | Purpose |
| --- | --- |
| Overview | Whole-office operational view |
| Command | Mission control, people, tasks and run flow |
| Operations | Runtimes, tools, approvals and evaluation |
| Knowledge | Memory, external bases, audit and incidents |
| Templates | Reusable office layouts and art packs |

## Current theme packs

| Theme | Intent |
| --- | --- |
| `night-shift` | Dark operational campus; current default |
| `cozy-studio` | Warm, approachable studio-office treatment |
| `blueprint` | Low-decoration structural/debug view |
| `harvest-commons` | Bright rural commons with garden paths, timber and workshop warmth |
| `orbital-deck` | High-contrast space-station office with luminous conduits and modular bays |

A theme pack owns semantic materials, status tones, avatar palettes, background effects, borders and shape language. It must not own routes, permissions, approval decisions or record identity.

## Theme-selection behavior

- The full page exposes all registered themes as an ARIA `radiogroup`.
- The selected theme is persisted under `agentops.pixel-office.theme.v1`.
- Browser `storage` events synchronize theme changes across tabs.
- Arrow keys, Home and End move selection with roving tab focus.
- Selection accents come from the chosen style pack rather than a hard-coded global color.
- Compact consumers can omit the selector and use the safe default.

## Component boundaries

- `pixelOfficeTheme.ts`: theme IDs, tokens, local-storage key and registry.
- `pixelOfficeThemePacks.ts`: additional original style-pack definitions.
- `pixelOfficeScene.ts`: layer definitions, zone membership and typed room props.
- `PixelCampusBackdrop.tsx`: theme-aware building/campus background.
- `PixelRoomSceneRenderer.tsx`: semantic room-prop renderer.
- `AgentAvatar.tsx`: deterministic theme-aware pixel person primitive.
- `PixelOfficeThemeSelector.tsx`: accessible style-pack gallery.
- `PixelZone.tsx`: room shell, state badge and route entry.
- `PixelOperatingMap.tsx`: layer focus, zoom, dimming and formal navigation.
- `capture-pixel-office-screenshots.mjs`: deterministic browser evidence capture.

## Non-negotiable authority boundary

Pixel Office is not a second ledger.

- All state comes from AgentOps MIS APIs/view models.
- Every actionable room or object resolves to a formal MIS route or record.
- Security approvals, human review, audit, permissions and external writes remain in formal surfaces.
- Proposed, Approved, Implemented and Canonical states are not represented only by color or animation.
- A theme cannot change record visibility or behavior.

## Template contract

A future art pack should be installable by adding a theme entry and optional renderer assets without changing:

- workspace/task/run/approval/memory IDs;
- route targets;
- layer and room semantics;
- authority or permission checks;
- evidence breadcrumbs;
- compact-mode behavior.

Original project-owned CSS/SVG/canvas primitives are preferred. Third-party assets require provenance and license review before inclusion.

## Screenshot evidence

GitHub Actions workflow `Pixel Office Screenshots` starts the local MIS server and Vite UI, renders the real `/workspace/pixel-office` route in Chinese, selects the target template, disables non-essential motion, and uploads PNG evidence.

Cycle 3 evidence:

- workflow run: `27958293187`;
- code head: `9007684220ddc72383bef37e7ba64c6608bf792c`;
- artifact: `pixel-office-screenshots` (`7794557026`);
- files:
  - `pixel-office-theme-gallery.png`;
  - `pixel-office-harvest-commons.png`;
  - `pixel-office-orbital-deck.png`.

The two full screenshots were visually reviewed: they preserve identical MIS rooms, agents, metrics and formal-page controls while presenting materially different palette, shape, path, lighting and character treatments.

## Verification checklist

- [x] UI production build passes on the Cycle 3 code head.
- [x] Backend deterministic smokes remain green.
- [x] Five theme packs compile under one typed registry.
- [x] The two new themes switch through the real full-page selector.
- [x] Theme choice remains appearance-only; formal route targets are unchanged.
- [x] No backend, database, approval, authentication, runtime or audit files changed.
- [x] Desktop gallery, Harvest Commons and Orbital Deck screenshots generated and reviewed.
- [ ] Exercise floor navigation and all selector keys in an interactive browser review.
- [ ] Capture compact/mobile visual evidence.
- [ ] Reverify or synchronize against the final development head before merge.

## Follow-up

1. Capture compact/mobile baselines.
2. Add browser assertions for arrow-key selection and formal route activation.
3. Extract remaining hard-coded visual values from legacy pixel components.
4. Decide whether the floor model should remain a camera layer or become route-addressable subviews.
5. Re-run exact-head CI after branch synchronization or any further commit.
