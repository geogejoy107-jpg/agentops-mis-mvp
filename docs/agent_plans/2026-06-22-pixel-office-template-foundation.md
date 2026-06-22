# Agent Plan: Pixel Office Template Foundation

Plan ID: `plan-pixel-office-template-foundation-2026-06-22`

Repository: `geogejoy107-jpg/agentops-mis-mvp`

Base: `codex/agent-gateway-kb-demo` at `cce739415c2e795e824b46ef072ebc9ec6cc36bc`

Branch: `design/pixel-office-template-foundation`

Risk: low. Approval required: no. The project owner explicitly requested this isolated office-only development branch.

## Task

Rebuild only the optional Pixel Office visualizer as a reusable React/CSS foundation. Keep formal MIS pages and ledgers authoritative. Do not change backend, runtime, approval, authentication, database, or audit behavior.

## References

- `docs/project/PROJECT_STATE.md`
- `docs/project/DECISIONS.md`
- `docs/project/BACKLOG.md`
- `docs/project/HANDOFF.md`
- `AGENTS.md`
- `PROJECT_SPEC.md`
- `AGENT_WORKFLOW.md`
- `BASE_INDEX.md`
- `docs/PIXEL_OPERATING_MAP_IMPLEMENTATION_DECISION.md`
- Draft PR #7: current-office visual research and typed scene prototype
- Draft PR #2: stale old-main implementation line
- Draft PR #11: broader UI-v2 work, excluded from this branch
- Notion proposal: multi-layer Pixel Office panel

## Relationships

- updates: PR #7 and the Notion proposal
- supersedes: PR #2 as the implementation line
- duplicate_of: none
- conflicts_with: none; the v1.5 hardening milestone remains unchanged

## Execution

1. Add a typed art-template registry with semantic materials and character palettes.
2. Add data-driven office layers, camera focus, and room scene composition.
3. Add original CSS campus, room, and Agent renderers.
4. Refactor the map, zones, and sprites to consume the selected template.
5. Add an accessible persistent template selector.
6. Preserve all current formal routes and live MIS state mapping.
7. Document the extension contract.
8. Open a Draft PR and verify with the UI build and relevant smoke checks.
9. Update GitHub and Notion project memory with exact evidence.

## Verification

- `npm run build` in `ui/start-building-app`
- no server/database/runtime files changed
- current routes remain reachable from every room
- compact mode remains supported
- reduced-motion behavior remains supported
- exact branch and commit recorded

## Rollback

Close or revert the isolated branch. The development branch is not modified by this plan.

## Verification result

Verified before implementation against the exact base commit. The required governance files and Pixel Office implementation were inspected. PR #7 is 110 commits behind the current development branch, so this work uses a fresh branch rather than extending the stale branch.

Status: verified.