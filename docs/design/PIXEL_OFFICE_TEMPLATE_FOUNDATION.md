# Pixel Office Template Foundation

> Status: draft implementation on `design/pixel-office-template-foundation`  
> Base: `codex/agent-gateway-kb-demo` at `cce739415c2e795e824b46ef072ebc9ec6cc36bc`  
> Scope: Pixel Office only; no backend or authority semantics change

## Objective

Rebuild Pixel Office as a reusable spatial UI foundation. Business entities, floor structure, room composition, camera behavior and art direction must be separable so later releases can replace the visual style without rewriting MIS routing or state mapping.

## Relationship to existing work

- **updates** Draft PR #7: retain its useful typed-scene and original-art principles, but rebase the implementation on the current development line.
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
| Command | Mission control, planning and approvals |
| Operations | Tasks, runs, tools and worker activity |
| Knowledge | Research, memory, evidence and evaluation |
| Templates | Future style packs and reusable office layouts |

## Current theme packs

| Theme | Intent |
| --- | --- |
| `night-shift` | Dark operational campus; current default |
| `cozy-studio` | Warm, approachable studio-office treatment |
| `blueprint` | Low-decoration structural/debug view |

A theme pack owns semantic materials, status tones, avatar palettes, background effects, borders and shape language. It must not own routes, permissions, approval decisions or record identity.

## Component boundaries

- `pixelOfficeTheme.ts`: theme IDs, tokens, local-storage key and registry.
- `pixelOfficeScene.ts`: layer definitions, zone membership and typed room props.
- `PixelCampusBackdrop.tsx`: theme-aware building/campus background.
- `PixelRoomSceneRenderer.tsx`: semantic room-prop renderer.
- `AgentAvatar.tsx`: deterministic theme-aware pixel person primitive.
- `PixelOfficeThemeSelector.tsx`: style-pack selector.
- `PixelZone.tsx`: room shell, state badge and route entry.
- `PixelOperatingMap.tsx`: layer focus, zoom, dimming and formal navigation.

## Non-negotiable authority boundary

Pixel Office is not a second ledger.

- All state comes from AgentOps MIS APIs/view models.
- Every actionable room or object must resolve to a formal MIS route or record.
- Security approvals, human review, audit, permissions and external writes remain in formal surfaces.
- Proposed, Approved, Implemented and Canonical states must not be represented only by color or animation.
- A theme cannot change record visibility or behavior.

## Template contract

A future art pack should be installable by adding a theme entry and optional renderer assets, without changing:

- workspace/task/run/approval/memory IDs;
- route targets;
- layer and room semantics;
- authority or permission checks;
- evidence breadcrumbs;
- compact-mode behavior.

Original project-owned CSS/SVG/canvas primitives are preferred. Third-party assets require provenance and license review before inclusion.

## Verification checklist

- [ ] `npm run build` passes in `ui/start-building-app`.
- [ ] Full Pixel Office can switch all registered themes.
- [ ] Layer focus and room navigation work with keyboard and pointer.
- [ ] Compact preview remains usable.
- [ ] Reduced-motion mode removes non-essential camera and sprite motion.
- [ ] Formal MIS route targets remain unchanged.
- [ ] No backend, database, approval, authentication, runtime or audit files changed.
- [ ] Desktop and compact screenshots reviewed.

## Follow-up

1. Wire the selector into the full page and persist the selected theme.
2. Extract any remaining hard-coded visual values from legacy pixel components.
3. Add scene/theme contract tests.
4. Capture full/compact visual baselines.
5. Review whether the floor model should remain a camera layer or become true route-addressable subviews.
