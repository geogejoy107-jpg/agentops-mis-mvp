# Release Provenance

## Scope

This file records provenance for the local AgentOps MIS MVP release evidence
packet. It focuses on code, package metadata, Pixel Office visuals and
commercial-build exclusions.

## First-Party Sources

| Area | Source | Evidence |
|---|---|---|
| Backend/API | `server.py` | Local MIS ledger, governance APIs and workflow endpoints. |
| CLI/worker | `agentops_mis_cli/` | Installable `agentops` and `agentops-worker` entrypoints. |
| UI | `ui/start-building-app/src/` | Vite/React local UI. |
| Pixel Office | `ui/start-building-app/src/app/components/pages/PixelOffice.tsx`, `ui/start-building-app/src/app/components/pixel/` | Native AgentOps MIS React/CSS visualizer and customer dispatch entry. |
| Knowledge/runbooks | `knowledge/`, `docs/` | Human/agent-readable doctrine, bases and runbooks. |

## Pixel Office Provenance

The production Pixel Office surface is a first-party implementation. It uses:

- React components;
- CSS borders, gradients, grid textures and absolute positioning;
- Lucide icons through package dependencies;
- MIS API data from the local AgentOps backend.

It does not use copied Star-Office-UI art assets, paid tilesets, bitmap sprites,
third-party scene JSON, or external virtual-office engines.

Star-Office-UI is kept only as an optional legacy local link through
`VITE_STAR_OFFICE_URL`. The link is not enabled by default and is not a source
of authority for tasks, runs, approvals, memory, evaluations, artifacts or
audits.

## Commercial Build Exclusion

Commercial/public distribution is blocked unless the following stay true:

- Product source under `ui/start-building-app/src` and `ui/start-building-app/public`
  contains no copied `.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.svg`, `.ico`,
  `.aseprite`, `.tmx`, `.tsx`, `.json` scene asset pack, sprite sheet or tile
  atlas for Pixel Office.
- `VITE_STAR_OFFICE_URL` remains an optional external local link only.
- Any future original Pixel Office asset pack lives under `assets/pixel-office/`
  and includes `LICENSE.md`, creator/source notes and export notes before use.
- Root `LICENSE`, `pyproject.toml`, UI `package.json`, this provenance file and
  `docs/THIRD_PARTY_NOTICES.md` agree that this repository is a proprietary
  local MVP unless a later written license overrides it.

## Verification

Run:

```bash
python3 scripts/license_provenance_smoke.py
python3 scripts/pixel_office_visualizer_boundary_smoke.py
```

These checks are release evidence, not a substitute for final legal review.
