# Star Office UI Adoption Packet Acceptance

## Scope

This slice creates the first concrete open-source adoption packet under
`docs/open_source_adoption_packets/` and validates it with a reusable catalog
smoke.

The selected base is Star Office UI because it is the current local pixel-office
visual reference. The packet keeps it as an optional local demo read model and
does not import third-party assets, code, build output, DB files, secrets or
generated artifacts.

## Decision

- Intake lane: `read_model`
- Merge decision: `incubate_as_read_model_reference`
- Product claim: local demo read model reference only
- Authority boundary: AgentOps MIS remains the workspace/task/run/approval/
  memory/artifact/evaluation/runtime-event/audit authority.
- Asset boundary: public or commercial Pixel Office assets must be original or
  separately licensed.

## Verification

Commands run locally:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/open_source_adoption_packet_catalog_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/open_source_adoption_packet_spec_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/open_source_adoption_boundary_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/local_open_source_experiment_base_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/release_evidence_packet_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/secret_scan_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile scripts/open_source_adoption_packet_catalog_smoke.py scripts/release_evidence_packet_smoke.py
git diff --check
```

## Local Observation

The local Star-Office-UI checkout exists at
`/Users/wuji/Documents/MIS/code/Star-Office-UI`, but it has local modified files
and contains visual assets. This slice intentionally does not read or copy those
assets into AgentOps MIS. The packet records only the adoption boundary and
verification contract.

## Acceptance Checklist

- Concrete Star Office adoption packet exists as JSON.
- Catalog smoke validates packet fields, intake lane, raw-data omissions,
  evidence refs, verification commands, claim limit and license boundary.
- CI and release evidence include the catalog smoke.
- No backend route, UI route, live runtime execution, DB read/write or connector
  call is added.
- No Star Office art assets, `node_modules`, `dist`, cache, `.env`, token,
  generated export, raw prompt, raw response, private message or full transcript
  is committed.

## Next Slice

Use the same adoption packet catalog for one more risky branch, such as the
Spatial Research District art source or UI v2 source branch, and decide whether
it remains an incubator, becomes a read model, or needs first-party
reimplementation.
