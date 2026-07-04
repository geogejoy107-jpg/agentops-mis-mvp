# UI v2 Adoption Packet Acceptance

## Scope

This slice applies the concrete adoption packet flow to PR #11,
`design/gemini-ui-v2-implementation`.

PR #11 is a draft/dirty UI implementation source branch with Mission Control,
semantic design-system components, AppShell v2, command palette, context bar,
responsive screenshot capture and workflow changes. It is useful product design
evidence, but it is not a direct merge candidate.

## Decision

- Intake lane: `first_party_migration`
- Merge decision: `rebuild_as_first_party_slices`
- Product claim: AgentOps MIS now has a governed UI v2 reference packet.
- Authority boundary: AgentOps MIS current workspace/task/run/approval/memory/
  evaluation/runtime-event/audit pages remain authoritative.
- UI boundary: no AppShell, route, Mission Control, read-model, screenshot CI or
  generated evidence workflow from PR #11 is accepted by this slice.

## Evidence

PR #11 current observed shape:

- Draft PR: yes
- Merge state: dirty
- Changed files: 31
- Additions/deletions observed: 4327 / 31
- Includes UI shell and design-system source:
  - `AppShellV2.tsx`
  - `CommandPalette.tsx`
  - `ContextBar.tsx`
  - `PrimaryNav.tsx`
  - `MetricCard.tsx`
  - `PageHeader.tsx`
  - `Pills.tsx`
  - `States.tsx`
- Includes Mission Control source:
  - `MissionControl.tsx`
  - `WorkPackagesPanel.tsx`
  - `AttentionPanel.tsx`
  - `WorkforcePanel.tsx`
  - `ActivityPanel.tsx`
  - `PixelPreviewPanel.tsx`
- Includes responsive screenshot capture workflow/source:
  - `tools/capture-ui-v2.mjs`
  - `.github/workflows/ui-v2-bootstrap.yml`
  - `.github/workflows/ui-v2-validation.yml`

## Verification

Commands run locally:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/open_source_adoption_packet_catalog_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/open_source_adoption_packet_spec_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/open_source_adoption_boundary_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/ui_research_spec_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/release_evidence_packet_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/secret_scan_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile scripts/open_source_adoption_packet_catalog_smoke.py scripts/release_evidence_packet_smoke.py
git diff --check
```

## Acceptance Checklist

- UI v2 source branch adoption packet exists as JSON.
- Catalog smoke validates the packet fields, intake lane, raw-data omissions,
  evidence refs, verification commands and product claim limit.
- No AppShell v2, Mission Control component, route replacement, screenshot
  artifact, workflow rewrite, `node_modules`, `dist`, cache, `.env`, token, DB,
  generated export, raw prompt, raw response, private message or full transcript
  is committed.
- Existing AgentOps MIS UI routes and authority pages remain unchanged.

## Next Slice

Pick one UI v2 pattern and rebuild it as a current-main first-party slice. The
highest-value candidate is a small Mission Control read-only summary panel that
uses existing MIS APIs and links back to formal Run Ledger, Approval Gate,
Agent Registry and Pixel Office pages.
