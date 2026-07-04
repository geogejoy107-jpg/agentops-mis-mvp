# Spatial Research Art Adoption Packet Acceptance

## Scope

This slice applies the concrete open-source adoption packet flow to PR #23,
`design/spatial-research-district-art-v1`.

PR #23 is a draft, unstable art/source branch with generated PNG outputs,
Advanced Spatial UI routes, pathfinding, art manifests, CSS and semantic
mapping work. Some safe semantic ideas have already been rebuilt into main, but
the branch itself is not a direct merge candidate.

## Decision

- Intake lane: `incubator`
- Merge decision: `incubate_then_reimplement_first_party`
- Product claim: AgentOps MIS now has a governed intake packet for the Spatial
  Research District art source.
- Authority boundary: AgentOps MIS remains the workspace/task/run/approval/
  memory/artifact/evaluation/runtime-event/audit authority.
- Asset boundary: generated PNG outputs and art manifests from PR #23 are not
  imported by this slice.
- UI boundary: Advanced Spatial routes/pathfinding are not accepted into default
  Pixel Office without a separate first-party migration plan and UI smoke.

## Evidence

PR #23 current observed shape:

- Draft PR: yes
- Merge state: unstable
- Changed files: 26
- Additions/deletions observed: 3338 / 168
- Includes generated asset outputs:
  - `ui/start-building-app/src/assets/spatial/agent-art/v0/cozy-research-agent-v0.png`
  - `ui/start-building-app/src/assets/spatial/agent-art/v0/industrial-agent-units-v0.png`
  - `ui/start-building-app/src/assets/spatial/agent-art/v0/manifest.json`
- Includes UI route/surface changes:
  - `AdvancedSpatialOffice.tsx`
  - `AdvancedSpatialSurface.tsx`
  - `spatialPathfinding.ts`

## Verification

Commands run locally:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/open_source_adoption_packet_catalog_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/open_source_adoption_packet_spec_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/open_source_adoption_boundary_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/spatial_research_semantic_contract_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/release_evidence_packet_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/secret_scan_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile scripts/open_source_adoption_packet_catalog_smoke.py scripts/release_evidence_packet_smoke.py
git diff --check
```

## Acceptance Checklist

- Spatial Research art source adoption packet exists as JSON.
- Catalog smoke validates the packet fields, intake lane, raw-data omissions,
  evidence refs, verification commands and product claim limit.
- No generated PNG, art manifest, route rewrite, pathfinding implementation,
  `node_modules`, `dist`, cache, `.env`, token, DB, generated export, raw
  prompt, raw response, private message or full transcript is committed.
- Existing Pixel Office and spatial semantic-contract authority remain
  unchanged.

## Next Slice

If the product still wants the advanced spatial art direction, rebuild one
first-party source-only slice on current main: no PNG outputs, no direct PR #23
merge, no route replacement, and a UI smoke proving the formal MIS routes remain
authoritative.
