# Agent Plan — Spatial Research District Art & MIS Semantics v1

- Plan ID: `plan-spatial-research-district-art-v1-2026-06-24`
- Repository: `geogejoy107-jpg/agentops-mis-mvp`
- Latest development branch verified: `codex/agent-gateway-kb-demo`
- Latest development commit verified before work: `896ee1aa288f2733aa9c147ced6a9c2d5c8622d0`
- Parent feature branch: `design/spatial-agent-identity-v0`
- Parent feature commit: `32d5d2c93e7c48cad7523f3ee5a772efeab6a556`
- Execution branch: `design/spatial-research-district-art-v1`
- Risk level: `low`
- Approval required: `false`
- Human direction: refine the Advanced pixel-art line, make the in-world Agents visibly derive from the same compact identity glyphs used by the sidebar, improve layout and visual quality, and ensure every meaningful district/facility/workspace object has an explicit AgentOps MIS meaning.

## Current milestone and priority boundary

The canonical development line remains `READY_TO_MERGE`; P0 keep-green gates and P1 knowledge/module work retain priority. This is an isolated P2 stacked UI slice and does not modify the release line, backend, database, runtime, approval, redaction, auth, external-write or audit semantics.

## Task understanding

The previous Advanced visual prototype proved Canvas rendering and L0–L3 scene changes, but it remained too diagrammatic:

- generic full-body characters did not visually match the compact Agent glyph identities;
- many buildings, rooms and props were decorative labels rather than MIS projections;
- the right rail and world used different identity grammars;
- oversized labels and heavy panels competed with the map;
- visual state was weakly coupled to MIS metrics.

This cycle replaces that prototype with one coherent art and semantics system.

## Required design principles

1. **One Agent identity pipeline.** The same `SpatialAgentVisualIdentity` must drive the sidebar crest, mini portrait and in-world character crest/palette.
2. **Meaning before decoration.** Every non-decorative landmark, workstation and prop must declare its MIS authority kind, route, projected signal and interaction.
3. **State is not identity.** Agent identity, runtime, operational status and risk remain separate visual channels.
4. **Semantic zoom changes information.** L0–L3 must change scene contents, query scope and available interactions rather than only scale the image.
5. **World is not authority.** Spatial objects navigate to or summarize formal MIS records; they do not own Agent, task, run, tool, approval, memory, artifact, evaluation, audit or delivery state.
6. **Original art only.** No commercial game tiles, marketplace sprites, proprietary logos or copied UI assets.

## Mapping model

Major semantic objects will cover the full MIS chain:

```text
Agent Hall / identity crests      → Agent registry
Task Noticeboard                  → Task ledger
Plan Table                        → Agent Plan / task binding
Run Forge / terminals             → Run ledger
Tool Workshop                     → Tool-call ledger
Approval Gate                     → Approval inbox / prepared-action wall
Evidence Archive / trays          → Artifact and evidence surfaces
Memory Orchard / cabinets         → Reviewed memory and candidates
Evaluation Greenhouse / bench     → Evaluation room
Runtime Dock                      → Runtime connectors
Audit Bell / clock                → Audit center
Delivery Post / crates            → Reports and delivery evidence
Mission Control                   → Control Tower
```

Decorative terrain is explicitly non-semantic. It may support wayfinding but cannot imply authority state.

## Relationship classification

- `updates`: Spatial OS Foundation v0; Spatial Agent Identity v0; approved two-tier renderer Decision; Advanced Research District prototype
- `supersedes`: the rough generic-character and label-only Advanced visual prototype
- `duplicate_of`: none
- `conflicts_with`: none confirmed

## Proposed files

- `ui/start-building-app/src/app/spatial/agentGlyphGeometry.ts`
- `ui/start-building-app/src/app/components/pixel/SimpleAgentGlyph.tsx`
- `ui/start-building-app/src/app/spatial/researchDistrictSemanticMap.ts`
- `ui/start-building-app/src/app/spatial/advancedSpatialModel.ts`
- `ui/start-building-app/src/app/spatial/researchDistrictArtV1.ts`
- `ui/start-building-app/src/app/components/spatial/AdvancedSpatialSurface.tsx`
- `ui/start-building-app/src/app/components/pages/AdvancedSpatialOffice.tsx`
- `ui/start-building-app/src/app/App.tsx`
- `ui/start-building-app/src/app/components/layout/Sidebar.tsx`
- `ui/start-building-app/scripts/capture-spatial-art-v1.mjs`
- `scripts/spatial_research_semantics_smoke.py`
- `.github/workflows/spatial-research-art-evidence.yml`
- `docs/design/SPATIAL_RESEARCH_DISTRICT_ART_V1.md`
- `docs/project/SPATIAL_RESEARCH_DISTRICT_ART_V1_HANDOFF.md`

## Execution steps

1. Extract glyph geometry/palettes into a renderer-neutral module and make both React glyphs and Canvas characters consume it.
2. Define the typed semantic object registry with routes, authority kinds, projected signals, interaction mode and L0–L3 placement.
3. Implement a cohesive warm research-village palette, scene composition, terrain, building silhouettes, interiors and semantic props.
4. Render in-world Agents as full pixel characters with the exact same identity crest/palette used by the sidebar.
5. Bind visible signals to the projected snapshot: active runs, approvals, blocked work, memory candidates, audit events and Agent states.
6. Replace oversized labels with signboards, inspector metadata and optional semantic overlays.
7. Implement hover/select hit regions and a semantic inspector that explains each object's MIS meaning and formal route.
8. Add the Advanced route and navigation while preserving `/workspace/pixel-office` as Basic/Lite fallback.
9. Add deterministic smoke checks for route validity, mapping completeness, shared glyph geometry and authority boundaries.
10. Add desktop/compact and L0–L3 screenshot evidence, run exact-head CI, visually review, then update GitHub and Notion handoffs.

## Verification plan

- `python3 scripts/spatial_os_manifest_smoke.py`
- `python3 scripts/spatial_agent_identity_smoke.py`
- `python3 scripts/spatial_research_semantics_smoke.py`
- exact-head `UI build`
- exact-head existing backend deterministic smokes
- screenshot workflow must produce desktop, compact, semantic L0–L3 and mapping-inspector evidence
- every semantic route must exist in `App.tsx`
- every non-decorative object must have an `agentops-mis` authority reference and route
- Canvas Agent crest geometry must come from the same module as `SimpleAgentGlyph`
- no external image URL, commercial asset name or copied logo path

## Rollback plan

Close or revert the isolated branch. Remove the Advanced route and files; Basic/Lite remains available at `/workspace/pixel-office`. No schema or MIS authority-state migration is required.

## Verification before execution

- exact repository, development head, parent branch/head and execution branch verified from GitHub;
- Project State, Decision Log, Backlog, Handoff, AGENTS, Project Spec, Agent Workflow and Base Index read from the exact current development head;
- current Agent identity implementation and prior Advanced local prototype inspected;
- approved Notion Spatial OS Decision and Foundation Handoff reviewed;
- current deficiency classified as an update/superseding visual implementation, not a new authority subsystem;
- plan remains low-risk UI/docs/CI work and requires no high-risk approval.

Plan status: `verified`.
