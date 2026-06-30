# Spatial Zone Authority Readback Acceptance

## Scope

This slice implements the safe UI follow-up from the Research District semantic
contract: Pixel Office Zone Inspector now reads the semantic object for the
focused zone and displays authority metadata.

It adds:

- `semantic-authority-readback` in `ZoneInspector.tsx`
- `scripts/spatial_zone_authority_readback_smoke.py`
- CI and release-evidence wiring for the UI readback contract

## Product Behavior

When an operator selects or hovers a Pixel Office zone, the inspector shows:

- authority class
- authority kind
- formal AgentOps MIS route
- route authority
- visual non-ledger boundary
- localized semantic description

This makes the map more useful for customer demos because each room explains
which MIS object owns the truth, instead of acting like a decorative second
system.

## Safety Boundary

This slice is read-only UI. It does not mutate SQLite, start runtimes, call
Hermes/OpenClaw, create approvals, add a new ledger, or copy any third-party
visual assets.

## Verification

Commands:

```bash
python3 scripts/spatial_zone_authority_readback_smoke.py
python3 scripts/spatial_research_semantic_contract_smoke.py
python3 -m py_compile scripts/spatial_zone_authority_readback_smoke.py scripts/spatial_research_semantic_contract_smoke.py scripts/release_evidence_packet_smoke.py
python3 scripts/secret_scan_smoke.py
python3 scripts/release_evidence_packet_smoke.py
git diff --check
cd ui/start-building-app && npm run build
```

Expected result:

- Zone Inspector imports `RESEARCH_DISTRICT_SEMANTIC_BY_ZONE`
- `semantic-authority-readback` renders authority class, authority kind, formal route and visual boundary
- route authority remains `agentops-mis`
- visual authority remains `spatial-map-is-not-ledger`
- no third-party asset reference or live runtime marker is introduced

## Next Slice

The next Spatial slice can add an original first-party sprite/art manifest
pipeline or a small visual regression smoke for the Pixel Office map. Do not
copy Star Office or other third-party assets into the repo.
