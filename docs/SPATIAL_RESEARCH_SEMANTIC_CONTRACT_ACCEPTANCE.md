# Spatial Research Semantic Contract Acceptance

## Scope

This slice rebuilds the safe part of the Spatial Research District experiment
onto current `main`: a route-bound semantic contract for the existing Pixel
Office zones.

It adds:

- `ui/start-building-app/src/app/spatial/researchDistrictSemanticContract.ts`
- `scripts/spatial_research_semantic_contract_smoke.py`
- CI and release-evidence wiring for the smoke

## Product Boundary

The spatial/pixel map is a customer-facing operating map, not an authority
system. Every semantic room points back to a formal AgentOps MIS page and
authority class:

- Agent registry
- Task ledger
- Run ledger
- Tool-call ledger
- Approval Wall
- Memory review
- Evaluation gates
- Runtime connectors
- Audit log
- External bases
- Templates
- Incident review

## Safety Boundary

This slice does not copy the image assets from the older Spatial Research
District art branch. It does not add PNG/JPEG/WebP/GIF files, remote asset URLs,
canvas engines, or a new page. It is a typed semantic contract plus a static
smoke gate.

## Verification

Commands:

```bash
python3 scripts/spatial_research_semantic_contract_smoke.py
python3 -m py_compile scripts/spatial_research_semantic_contract_smoke.py scripts/release_evidence_packet_smoke.py
git diff --check
```

Expected result:

- one semantic object per Pixel Office zone
- each semantic object derives `formalRoute` from `PIXEL_ZONES`
- each route exists in `App.tsx`
- the contract states `routeAuthority: "agentops-mis"`
- the contract states `visualAuthority: "spatial-map-is-not-ledger"`
- no third-party visual asset references

## Next Slice

After this contract lands, the next safe Spatial branch extraction is either:

- a small UI readback that displays the semantic authority class in the Zone
  Inspector, or
- an original first-party sprite/art manifest pipeline that does not commit
  copied third-party assets.
