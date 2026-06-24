# Pixel Operating Map Acceptance

Date: 2026-06-16
Scope: v1.3 acceptance pass for the current Pixel Operating Map implementation.

## Build Commands Used

- `cd ui/start-building-app && npm install`
- `cd ui/start-building-app && npm run build`

## Build Result

- `npm install`: passed. Dependencies were already up to date. npm reported 3 high severity audit findings; remediation was not run because dependency upgrades are outside this v1.3 acceptance pass.
- `npm run build`: passed.
- Build output: Vite transformed 2264 modules and produced `dist/index.html`, `dist/assets/index-CpWU18Nx.css`, and `dist/assets/index-D3c4UUDW.js`.
- Warning: Vite reported one chunk-size warning for the main JavaScript bundle. This is a performance follow-up, not a build failure.

## Errors Fixed

- No build, type, or runtime import errors were found during this pass.
- No code changes were required to make the current Pixel Operating Map build.
- `server.py` was not modified for this acceptance pass.

## Acceptance Checklist

| Item | Status | Evidence |
| --- | --- | --- |
| `/workspace/pixel-office` route exists | Pass | `ui/start-building-app/src/app/App.tsx` defines the route and renders `PixelOffice`. |
| Sidebar has Pixel Office entry | Pass | `ui/start-building-app/src/app/components/layout/Sidebar.tsx` includes a Pixel Office navigation item. |
| Workspace Home no longer embeds dominant Star-Office iframe | Pass | `ui/start-building-app/src/app/components/pages/WorkspaceHome.tsx` links into Pixel Office and does not render a Star-Office iframe. |
| Star Office is only an optional legacy link via `VITE_STAR_OFFICE_URL` | Pass | `WorkspaceHome.tsx` and `PixelOffice.tsx` gate the legacy Star Office link behind `import.meta.env.VITE_STAR_OFFICE_URL`. |
| Pixel map uses original React/CSS only | Pass | `PixelOperatingMap.tsx`, `PixelZone.tsx`, `AgentSprite.tsx`, and related components are React/CSS DOM components. No PixiJS, Phaser, canvas engine, or sprite atlas is used. |
| No third-party assets were copied | Pass | No image or sprite assets were found under `ui/start-building-app/src`; the implementation uses CSS shapes and text. |
| Zones route to formal MIS pages | Pass | `pixelModel.ts` maps zones to MIS routes such as `/admin`, `/workspace/agents`, `/workspace/tasks`, `/admin/connectors`, `/admin/toolcalls`, `/workspace/approvals`, `/admin/evaluations`, `/workspace/memory`, `/admin/audit`, `/admin/bases/notion`, `/workspace/runs`, and `/admin/templates`. |
| Agents derive from AgentOps MIS/mock state | Pass | `PixelOffice.tsx` loads live MIS data through `loadAgentOpsSnapshot`, and `pixelModel.ts` derives pixel agents from the AgentOps snapshot with deterministic fallback state. |
| Task cards appear in Task Hall | Pass | `deriveTaskCards` creates task cards for the Task Hall zone, and `PixelOperatingMap.tsx` renders them with `TaskCardSprite`. |
| Zone Inspector exists | Pass | `ui/start-building-app/src/app/components/pixel/ZoneInspector.tsx` exists and is rendered by `PixelOperatingMap.tsx`. |
| Operations Bar exists | Pass | `ui/start-building-app/src/app/components/pixel/OperationsBar.tsx` exists and is rendered by `PixelOffice.tsx`. |
| `/admin/evaluations` exists | Pass | `App.tsx` defines `/admin/evaluations`, rendering `EvaluationRoom`. |
| Build passes | Pass | `npm run build` completed successfully on 2026-06-16. |

## Known Limitations

- The v1.3 map is an original React/CSS operating map, not a production pixel-art engine.
- It does not include pathfinding, replay trails, or time-scrubbed run playback.
- Agent placement and movement are lightweight presentation states rather than a full simulation layer.
- Some live ledger strings, agent names, and source labels may remain in their original source language.
- The current JavaScript bundle triggers a Vite chunk-size warning; code splitting is a v1.4+ performance task.
- npm reports 3 high severity audit findings after install. Dependency audit and remediation should be handled separately from this map acceptance pass.
- The current working tree may include local post-v1.3 workflow changes from adjacent demo work; this document validates the Pixel Operating Map acceptance boundary only.

## Next Recommended Work

### v1.4

- Add an original, license-clean pixel visual pack after art direction approval.
- Add stronger responsive layout checks for classroom projector, laptop, and narrow browser widths.
- Add keyboard navigation and clearer focus states for zones and inspector controls.
- Add route-trail overlays from Run Ledger events without introducing a canvas engine.

### v1.5

- Consider PixiJS or Canvas only after original assets and interaction requirements justify it.
- Add run replay with time controls, parent-child delegation paths, and tool-call event markers.
- Add richer evaluation overlays for quality gates, blocked runs, and high-risk approvals.
- Add customer-safe localization pass for all user-facing labels.
