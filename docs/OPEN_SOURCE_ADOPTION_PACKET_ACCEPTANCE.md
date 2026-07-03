# Open Source Adoption Packet Acceptance

## Scope

This slice adds a machine-checkable adoption packet contract for open-source
bases, GitHub branches, local experiments, UI references, runtime adapters and
Harness-style engineering references.

It is docs-and-static-gate only. It does not add backend routes, UI routes,
runtime execution, DB reads/writes, connector calls, generated exports or
third-party code/assets.

## Verification

Commands run locally:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 scripts/open_source_adoption_packet_spec_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/open_source_adoption_boundary_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/open_source_mainline_governance_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/release_evidence_packet_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 scripts/secret_scan_smoke.py
PYTHONDONTWRITEBYTECODE=1 python3 -m py_compile scripts/open_source_adoption_packet_spec_smoke.py scripts/release_evidence_packet_smoke.py
git diff --check
```

All commands passed locally before this acceptance record was added.

## Acceptance Checklist

- Adoption packet fields are explicit and smoke-verified.
- Intake lanes cover research packet, incubator, adapter, read model,
  first-party migration and reject.
- Harness-informed constraints preserve MIS as the authority ledger.
- Raw prompts, raw responses, credentials, private messages, full transcripts,
  local DBs, generated exports, tokens and customer raw documents are omitted.
- CI and release evidence include the new smoke.
- No DB, `.env`, cache, `node_modules`, `dist`, generated export, raw prompt,
  raw response, private message or full transcript is committed.

## Known Limitation

This slice defines the adoption packet contract. It does not yet select a real
experimental branch and run it through the packet from intake to merge/reject.

## Next Slice

Pick one local experimental/open-source-base worktree and create its first
adoption packet with a local smoke result, then decide whether it should remain
in incubator, become an adapter/read model, or be reimplemented first-party.
