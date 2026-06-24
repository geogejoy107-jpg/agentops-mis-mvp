# Agent Plan — Spatial OS Foundation v0

- Plan ID: `plan-spatial-os-foundation-v0-2026-06-23`
- Repository: `geogejoy107-jpg/agentops-mis-mvp`
- Development branch verified: `codex/agent-gateway-kb-demo`
- Development commit verified: `32730808ee227140690f969017df0fd388be63f0`
- Execution branch: `design/spatial-os-foundation-v0`
- Risk level: `low`
- Approval required: `false`
- Human approval source: project owner explicitly approved the Basic/Lite plus Advanced Spatial OS split in project chat and the Notion Decision `3876adfd-d920-8183-87cc-e3ca9cf153a1`.

## Current milestone and priority boundary

The canonical v1.5 development line remains `READY_TO_MERGE`. This plan is an isolated P2 branch and does not displace release-hardening, P0 keep-green gates, or P1 module-splitting work.

## Task understanding

Create the renderer-neutral foundation required before implementing the first full game-art world. Preserve the existing React/CSS Pixel Office as `Basic / Lite`; introduce first-party contracts so future Phaser/Tiled, isometric, cutaway, graph-space, or other renderers can consume the same MIS-derived spatial model without owning MIS authority state.

This cycle deliberately does **not** claim that an Advanced game world is finished. It establishes the contracts, first world/template/art manifests, a bridge from the current Basic Pixel model, and CI validation needed to build that world safely.

## Referenced specs and evidence

- `docs/project/PROJECT_STATE.md`
- `docs/project/DECISIONS.md`, especially D-001 through D-006
- `docs/project/BACKLOG.md`
- `docs/project/HANDOFF.md`
- `AGENTS.md`
- `PROJECT_SPEC.md`
- `AGENT_WORKFLOW.md`
- `BASE_INDEX.md`
- `docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md`
- `docs/PIXEL_OPERATING_MAP_SPEC.md`
- `docs/PIXEL_OPERATING_MAP_IMPLEMENTATION_DECISION.md`
- existing `PixelOffice.tsx`, `PixelOperatingMap.tsx`, and `pixelModel.ts` on the exact development commit
- Notion Decision: `Spatial OS 双层底座：基础版保留，升级版采用世界模板 + 美术模块`

## Relationship classification

- `updates`: the approved Spatial OS Decision, the multi-layer Pixel Office Proposal, and Draft PR #13's reusable-template direction
- `supersedes`: the interpretation that palette/shape token changes alone constitute a complete game-art template
- `duplicate_of`: none
- `conflicts_with`: none confirmed; D-006 remains in force because this branch is isolated from the release line

## Proposed files to change

- `docs/design/SPATIAL_OS_FOUNDATION_V0.md`
- `docs/project/SPATIAL_OS_FOUNDATION_HANDOFF.md`
- `ui/start-building-app/src/app/spatial/contracts.ts`
- `ui/start-building-app/src/app/spatial/manifestValidation.ts`
- `ui/start-building-app/src/app/spatial/catalog.ts`
- `ui/start-building-app/src/app/spatial/basicPixelProjection.ts`
- `ui/start-building-app/src/app/spatial/manifests/top-down-rpg-campus.v0.json`
- `ui/start-building-app/src/app/spatial/manifests/warm-research-art-kit.v0.json`
- `ui/start-building-app/src/app/spatial/manifests/research-district.v0.json`
- `ui/start-building-app/src/app/components/pages/PixelOffice.tsx`
- `scripts/spatial_os_manifest_smoke.py`
- `.github/workflows/ci.yml`

## Execution steps

1. Define first-party semantic world, authority reference, renderer, projection, world-template, art-kit, semantic-zoom, portal, entity, and snapshot contracts.
2. Add dependency-free runtime manifest validators so malformed or authority-violating manifests fail closed.
3. Add the first `top-down-rpg-campus` World Template manifest.
4. Add the first original `warm-research` Art Kit manifest as a planned asset contract, without copying or bundling commercial game artwork.
5. Add the Research District vertical-slice world manifest:
   `World Atlas → Research District → AI Papers House → Claude Research Desk → formal MIS portals`.
6. Add a Basic/Lite projection bridge that converts the current Pixel Office agents, tasks, and metrics into the renderer-neutral snapshot.
7. Wire the bridge into the existing Pixel Office only as metadata/contract evidence; preserve the current visual behavior.
8. Add a deterministic Python smoke validating manifest topology, semantic-zoom ancestry, formal routes, asset provenance, renderer capability declarations, and authority boundaries.
9. Add the smoke to existing CI and run exact-head UI build plus deterministic checks through the Draft PR.
10. Update GitHub and Notion with exact branch, commit, verification, remaining risks, and next action.

## Open-source adoption record

Reference: Phaser, Tiled, EasyStar-style pathfinding concepts.

Borrowed idea: scene/camera/tilemap/pathfinding interfaces and data-driven world manifests.

First-party MIS module touched: optional Spatial OS projection/rendering layer only.

Authority boundary preserved: external game libraries may render or navigate projected entities but never own workspace, agent, task, run, approval, memory, artifact, evaluation, audit, permission, or delivery state.

Verification: dependency-free contract and manifest validation lands before any engine dependency; actual framework adoption requires a later reviewed plan and provenance record.

## Verification plan

- `python3 scripts/spatial_os_manifest_smoke.py`
- `npm ci && npm run build` in `ui/start-building-app` through GitHub Actions
- existing `Backend deterministic smokes` remain green
- no backend, database, authentication, approval, runtime, redaction, external-write, or audit files change
- every portal route must exist in the current React router
- all manifest assets must be `first_party`, `generated_first_party`, or `planned_first_party`; remote commercial asset URLs are forbidden
- the Basic/Lite renderer continues to render the current Pixel Office unchanged

## Rollback plan

Close or revert the isolated branch. The development line remains unchanged at its independently advancing head. The manifest/contracts directory can be removed without affecting MIS authority objects or the existing Basic Pixel Office.

## Plan verification

Verified before execution:

- exact repository, development branch, development commit, and feature branch established from GitHub;
- required governance/spec files read from the exact development commit;
- existing Pixel Office code and current router inspected;
- existing implementation contains no Phaser or renderer-neutral Spatial OS contract;
- plan scope is UI/docs/CI validation only and does not alter authority or external-write behavior;
- human owner explicitly approved the product split and advanced foundation direction.

Plan status: `verified`.
