# Notion MIS Project Ledger

## Base identity

- Base ID: `base_notion_project_ledger`
- Provider: Notion
- Project: `agentops-mis`
- Ledger database: `24467ea0-d176-4e40-957c-dcc1ca55db53`
- Ledger data source: `collection://7ba689c1-61ea-4641-8a88-9ac20ce4efed`
- Registry database: `3d61d50f-f460-4068-9e78-fd7c5b584799`
- Manifest: `config/external_bases/notion_project_ledger.json`

## Authority boundary

This base contains reviewed project-governance records and candidate Project Delta records.

Use GitHub for repository, branch, commit, pull request, diff, code, and test facts. Use AgentOps MIS SQLite/API for task, run, tool call, approval, artifact, evaluation, memory-review, and audit facts. ChatGPT Project material is context until reviewed.

## Retrieval rules

1. Prefer records with status `Approved` or `Implemented` and verification state `Verified`.
2. Treat `Inbox` and `Proposed` records as candidate context only.
3. Recheck code facts against GitHub and execution facts against AgentOps MIS.
4. Preserve `External Base ID`, source record ID, source URL, branch, commit, verification time, and evidence hash.
5. When sources disagree, surface a conflict instead of silently replacing one source with another.
6. Do not ingest private raw conversation content or customer material without an approved scope and redaction policy.

## Capabilities

```yaml
read: true
search: true
write: true
sync: false
webhook: false
write_policy: confirm
canonical_promotion: human_review_only
```

## Validation

```bash
python3 scripts/external_base_manifest_smoke.py
```

Live synchronization is intentionally disabled in v0. The next implementation phase must add workspace/project isolation, provenance, idempotency, conflict handling, approval-resume, and audit evidence before enabling connector writes.
