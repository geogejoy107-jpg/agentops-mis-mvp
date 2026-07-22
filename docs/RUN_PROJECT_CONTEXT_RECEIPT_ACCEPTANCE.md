# Run Project Context Receipt Acceptance

Status: source implementation complete; exact-head CI and packaged Host upgrade
are separate release gates.

## Product Purpose

Project Knowledge and approved Memory already feed the transient Agent Worker
Context Packet. The Run detail page now makes that use visible to a Human
operator instead of showing only a generic Memory count.

The read-only Project Context Receipt shows:

- whether Worker knowledge retrieval is ready;
- consumed Worker tool-call count;
- Context Packet block count and hash;
- safe project Knowledge paths;
- exact approved Memory IDs used by the run;
- resulting Run Memory ID, type, review status and source reference;
- pending Memory-review count and a link to Human Memory review;
- omission proof for queries, snippets, raw content, context bodies, full
  transcripts, raw prompts, raw responses and tokens.

## Authority And Privacy Boundary

- The UI reads `GET /api/operator/evidence-report?run_id=<run_id>&limit=1`.
- The report is derived from existing MIS tool-call, Memory, Run and Audit
  evidence. It does not create or approve Memory and does not mutate the
  ledger.
- Knowledge summaries and approved Memory bodies remain transient Worker
  context. The receipt persists and displays only bounded IDs, hashes, counts,
  paths and omission booleans.
- Candidate Memory remains non-authoritative until a Human approves or rejects
  it in the Memory Library.
- A non-Worker run is labeled not applicable instead of being presented as
  proof that project context was consumed.

## Verification

```bash
python3 scripts/run_detail_evidence_ui_smoke.py
python3 scripts/worker_knowledge_evidence_consumption_smoke.py
python3 scripts/secret_scan_smoke.py
git diff --check
```

The React production build remains an exact-head CI requirement. Local package
or npm installation should not be attempted on a Host that is below the
documented storage floor.

## Release Boundary

The installed `v1.6.0-private-host-preview.41` predates this Run-detail panel.
Do not attribute the visible Project Context Receipt to that package until a
later exact commit is packaged and installed.
