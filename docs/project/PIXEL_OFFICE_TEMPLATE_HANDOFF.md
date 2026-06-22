# Pixel Office Template Foundation — Handoff

## Scope

Parallel draft UI branch only. It does not change the current hardening milestone or displace P0/P1 correctness work.

## Repository baseline

- Repository: `geogejoy107-jpg/agentops-mis-mvp`
- Base branch: `codex/agent-gateway-kb-demo`
- Verified base commit: `cce739415c2e795e824b46ef072ebc9ec6cc36bc`
- Working branch: `design/pixel-office-template-foundation`

## Objective

Create a reusable office/campus UI substrate that separates:

1. authoritative MIS data and formal routes;
2. floor/room scene semantics;
3. camera and interaction behavior;
4. replaceable art-direction templates.

## Implemented on this branch

- Verified Agent Plan.
- Semantic theme registry.
- Three initial style packs: night shift, cozy studio, blueprint.
- Typed floors/layers and room scene props.
- Theme-aware backdrop, rooms, avatars and task cards.
- Layer focus / zoom and room dimming.
- Reduced-motion handling in the map layer.
- Existing formal MIS route handoff preserved.

## Existing-work relationships

- `updates`: Draft PR #7 (`design-ui-visual-system-v3`).
- `supersedes`: stale Draft PR #2 implementation line (`feature/pixel-office-art-direction-v2`).
- `conflicts_with`: none confirmed.
- Broader Draft PR #11 is explicitly out of scope.

## Verification status

Required before review:

- run `npm run build` in `ui/start-building-app`;
- wire and verify full-page theme selection/persistence;
- capture desktop and compact screenshots;
- test route targets, focus states and reduced motion;
- confirm no backend/authority files changed;
- rebase or reverify against the moving development branch.

## Remaining risks

- Legacy components may still contain hard-coded visual values.
- Current floor focus is a camera interaction, not yet a route-addressable subview.
- Visual regression coverage does not yet exist.
- No third-party art assets are approved for bundling.

## Canonical-state note

This branch is experimental and non-canonical until reviewed and merged. `docs/project/PROJECT_STATE.md` is intentionally unchanged.
