# Local Codex Runbook: Notion External Base v0

## Purpose

This runbook covers the local, dependency-free Notion Project Ledger external-base v0. It is a governance contract and knowledge-base entry, not a live sync connector.

## Authority Boundary

- GitHub remains authority for repository, branch, commit, pull request, diff, code, and test facts.
- AgentOps MIS SQLite/API remains authority for tasks, runs, tool calls, approvals, artifacts, evaluations, memory review, and audit facts.
- Notion Project Ledger is a reviewed project-memory and presentation base for decisions, risks, backlog, handoff, and candidate deltas.
- ChatGPT Project material remains context until reviewed.

Do not treat Notion `Inbox` or `Proposed` rows as canonical execution state.

## Safety Defaults

- No Notion token, cookie, API key, private message, raw prompt, raw response, full transcript, or customer raw content belongs in this repo.
- `implementation.live_sync_enabled` must stay `false` in v0.
- External writes require prepared action, explicit confirmation, and idempotency before any future live connector work.
- Destructive external actions are blocked.

## Local Validation

Run from the repo root:

```bash
python3 -m json.tool config/external_bases/notion_project_ledger.json >/dev/null
python3 -m py_compile scripts/external_base_manifest_smoke.py
python3 scripts/external_base_manifest_smoke.py
git diff --check
```

Expected manifest result:

```json
{
  "ok": true,
  "schema_version": "agentops.external_base.v0",
  "base_id": "base_notion_project_ledger",
  "provider": "notion",
  "live_sync_enabled": false,
  "errors": []
}
```

## Files

- `config/external_bases/notion_project_ledger.json`: machine-readable external-base contract.
- `docs/NOTION_DATA_GOVERNANCE_AND_EXTERNAL_BASE_V0.md`: governance and roadmap.
- `knowledge/bases/notion_project_ledger.md`: indexed knowledge-base entry.
- `scripts/external_base_manifest_smoke.py`: offline validator.
- `BASE_INDEX.md`: base registry index entry.

## Future Connector Plan

Future live connector work must be a separate reviewed slice:

1. Read-only governed ingestion for scoped, reviewed records.
2. Workspace/project ACL and provenance checks.
3. Source record ID, source URL, version/hash, and retrieval evidence.
4. Conflict/staleness queue instead of silent overwrite.
5. Approval-gated candidate writeback only after prepared-action resume.
6. Human-only canonical promotion.

## Rollback

Rollback is additive and local:

1. Remove the manifest and knowledge entry.
2. Remove the validator from CI.
3. Remove the `BASE_INDEX.md` entry.
4. Leave runtime ledgers untouched.
