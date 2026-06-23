# Agent Plan — Spatial Agent Identity v0

- Plan ID: `plan-spatial-agent-identity-v0-2026-06-23`
- Repository: `geogejoy107-jpg/agentops-mis-mvp`
- Development branch verified: `codex/agent-gateway-kb-demo`
- Development commit verified before work: `16cf95d7230e9298ca374b2af3a93f2e363697af`
- Parent foundation branch: `design/spatial-os-foundation-v0`
- Parent foundation commit: `1dd4c0b8f4f984cd6b9ac396852f897a0af31393`
- Execution branch: `design/spatial-agent-identity-v0`
- Starting execution commit: `1dd4c0b8f4f984cd6b9ac396852f897a0af31393`
- Risk level: `low`
- Approval required: `false`
- Human direction: begin the next cycle and design the Basic/Lite Agent representation using the compact, geometric clarity of modern coding-agent interfaces and the supplied pixel-glyph roster as reference.

## Current milestone and objective

The canonical development line remains `READY_TO_MERGE`; P0 release gates stay Keep Green and P1 module splitting remains active. This work is an isolated stacked P2 UI slice and does not reprioritize or displace the release line.

The cycle objective is to establish a first-party Agent visual-identity grammar that works in both rendering tiers:

- Basic/Lite: compact 12–32 px geometric glyphs in rosters, inspectors and the existing operating map;
- Advanced Spatial: stable archetype/palette/seed metadata that later selects full directional sprites without changing MIS identity.

## Task understanding

The previous Basic Pixel Agent used one generic robot silhouette, which made different Agents visually interchangeable. The user-provided reference instead distinguishes each entry with a tiny geometric pixel mark whose shape remains legible at sidebar scale.

Implement an original identity system with these rules:

1. identity is communicated by silhouette plus palette, not color alone;
2. runtime, status and risk remain separate channels and must not redefine identity;
3. the same Agent ID always resolves to the same visual identity;
4. role keywords may select a meaningful archetype, while unknown roles use deterministic hashing;
5. no OpenAI, Anthropic, Claude, Codex, marketplace or game logo/asset is copied;
6. the identity contract must be renderer-neutral and present in projected Spatial entities;
7. the Basic/Lite UI must visibly use the new glyphs and expose screenshot evidence.

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
- `docs/agent_plans/2026-06-23-spatial-os-foundation-v0.md`
- `docs/design/SPATIAL_OS_FOUNDATION_V0.md`
- `docs/project/SPATIAL_OS_FOUNDATION_HANDOFF.md`
- Notion Decision `3876adfd-d920-8183-87cc-e3ca9cf153a1`
- Notion Handoff `3886adfd-d920-8142-adaf-f63a5476b93c`
- user-provided compact pixel-glyph roster screenshot
- reference-only product pages: `https://openai.com/codex/` and `https://claude.com/product/claude-code`

## Relationship classification

- `updates`: Spatial OS foundation v0, the approved two-tier rendering Decision, and the Basic/Lite Agent representation
- `supersedes`: the single generic robot silhouette as the only Basic/Lite Agent identity
- `duplicate_of`: none
- `conflicts_with`: none confirmed

## Proposed files to change

- `ui/start-building-app/src/app/spatial/contracts.ts`
- `ui/start-building-app/src/app/spatial/agentIdentity.ts`
- `ui/start-building-app/src/app/spatial/basicPixelProjection.ts`
- `ui/start-building-app/src/app/spatial/manifestValidation.ts`
- `ui/start-building-app/src/app/spatial/manifests/warm-research-art-kit.v0.json`
- `ui/start-building-app/src/app/components/pixel/SimpleAgentGlyph.tsx`
- `ui/start-building-app/src/app/components/pixel/AgentGlyphRoster.tsx`
- `ui/start-building-app/src/app/components/pixel/AgentSprite.tsx`
- `ui/start-building-app/src/app/components/pixel/ZoneInspector.tsx`
- `ui/start-building-app/src/app/components/pages/PixelOffice.tsx`
- `ui/start-building-app/scripts/capture-agent-identity-screenshots.mjs`
- `.github/workflows/spatial-agent-identity-screenshots.yml`
- `scripts/spatial_agent_identity_smoke.py`
- `.github/workflows/ci.yml`
- `docs/design/SPATIAL_AGENT_IDENTITY_V0.md`
- `docs/project/SPATIAL_AGENT_IDENTITY_HANDOFF.md`

## Execution steps

1. Add renderer-neutral `SpatialAgentVisualIdentity` fields and a typed set of original glyph archetypes/palette slots.
2. Implement deterministic role-aware identity derivation with stable hashing and no external assets.
3. Populate projected Agent entities with the identity contract.
4. Extend the Art Kit manifest and validators with an explicit Agent identity grammar.
5. Implement a crisp-edge SVG pixel-glyph primitive and a compact roster matching the density of the supplied reference without copying any mark.
6. Replace the generic robot-only Basic map token with a glyph-bearing Agent token; keep status and risk indicators separate.
7. Add glyphs to the Zone Inspector roster and expose a full Agent roster on the Pixel Office page.
8. Add deterministic smoke coverage for identity stability, archetype/palette completeness, separation of state/risk channels and first-party provenance.
9. Add a Playwright screenshot workflow for the roster and full Basic/Lite page.
10. Run exact-head CI, download and visually review the screenshots, then update GitHub and Notion evidence.

## Reference adoption record

Reference: official Codex and Claude Code product interfaces plus the user-supplied geometric pixel roster.

Borrowed idea: compact task/agent command-center density, restrained geometric identity, stable list alignment and strong recognizability at small size.

Adoption class: reference-only visual-method adaptation.

First-party MIS module touched: optional UI projection and Agent art metadata only.

Authority boundary preserved: Agent identity, runtime, status, risk, workspace, task, run and permissions remain MIS-derived. The visual glyph has no authority and cannot mutate ledger state.

Verification: all glyph matrices, palette mappings and components are project-authored; no logo path, remote image, trademarked symbol or external production asset is included.

## Verification plan

- `python3 scripts/spatial_os_manifest_smoke.py`
- `python3 scripts/spatial_agent_identity_smoke.py`
- exact-head `UI build`
- exact-head `Backend deterministic smokes`
- screenshot workflow must produce:
  - `spatial-agent-glyph-roster.png`
  - `spatial-agent-basic-map.png`
- visual review must confirm at least eight distinct silhouettes and separate status/risk channels
- reduced-motion rendering must remain deterministic
- no backend, database, auth, approval, runtime, redaction, external-write or audit files may change

## Rollback plan

Close or revert the stacked branch. The parent Spatial OS foundation and development line remain unchanged. The Basic/Lite generic robot token can be restored independently without affecting the semantic contracts or MIS ledger.

## Plan verification

Verified before implementation:

- exact repository, latest development head, parent foundation branch/head and execution branch established from GitHub;
- canonical project files and current Notion Decision/Handoff read;
- existing implementation inspected: `AgentSprite.tsx` uses one generic robot silhouette and `ZoneInspector.tsx` lists Agents without visual identity;
- user reference analyzed as compact, distinct pixel silhouettes rather than palette-only variants;
- scope is UI/contracts/docs/CI evidence only and remains P2;
- no high-risk action, live runtime, external upload, credential change or authority-state migration is involved.

Plan status: `verified`.
