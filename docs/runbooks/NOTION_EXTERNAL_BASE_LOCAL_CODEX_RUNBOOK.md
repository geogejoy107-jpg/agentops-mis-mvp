# Local Codex Runbook: Notion Data Governance and External Base v0

## Purpose

Use this runbook on the local development machine to finish and verify Draft PR #19 without weakening the AgentOps MIS authority, approval, workspace, redaction, or audit boundaries.

This runbook covers two separate stages:

1. **Stage A — finish PR #19:** synchronize the branch, resolve documentation conflicts, run offline validation, and attach evidence.
2. **Stage B — later connector implementation:** add read-only governed ingestion and approval-gated candidate writeback in a separate reviewed plan/PR.

Do not silently combine Stage B into PR #19.

## Pinned starting context

```text
Repository: geogejoy107-jpg/agentops-mis-mvp
Feature branch: feat/notion-governance-external-base-v0
Draft PR: #19
Target branch: codex/agent-gateway-kb-demo
PR base observed when opened: 9fc10a67694013c277a30847d72917c6845016c5
Feature head before this runbook: c67001859dc1db169eb8fcfba4f4612ffb0be953
Agent Plan evidence: Issue #14
```

These SHAs are historical evidence, not permission to assume the branch is unchanged. Codex must print and verify the actual refs before modifying files.

## Mandatory preflight

Codex must begin its response with:

```text
Repository:
Branch:
Commit:
Current milestone:
Current objective:
Relevant approved decisions:
Open P0/P1 items:
Risks / unknowns:
```

Read in this order before editing:

1. `docs/project/PROJECT_STATE.md`
2. `docs/project/DECISIONS.md`
3. `docs/project/BACKLOG.md`
4. `docs/project/HANDOFF.md`
5. `AGENTS.md`
6. `PROJECT_SPEC.md`
7. `AGENT_WORKFLOW.md`
8. `BASE_INDEX.md`
9. `docs/NOTION_DATA_GOVERNANCE_AND_EXTERNAL_BASE_V0.md`
10. `config/external_bases/notion_project_ledger.json`
11. `knowledge/bases/notion_project_ledger.md`
12. Issue #14 and PR #19

Verify refs:

```bash
git fetch --all --prune
git status --short --branch
git rev-parse HEAD
git rev-parse origin/codex/agent-gateway-kb-demo
git log -1 --oneline HEAD
git log -1 --oneline origin/codex/agent-gateway-kb-demo
```

If repository, branch, or commit cannot be verified, stop and report it as `Unknown`. Do not infer values from this runbook or chat history.

## Stage A — finish Draft PR #19

### A1. Use an isolated worktree

From the main clone:

```bash
git fetch --all --prune
git worktree add ../agentops-mis-notion-v0 feat/notion-governance-external-base-v0
cd ../agentops-mis-notion-v0
```

If the worktree already exists, inspect it rather than deleting it automatically.

### A2. Synchronize the target branch

Prefer merging the current target into the shared feature branch; avoid rewriting published history unless the project owner explicitly chooses rebase and force-push.

```bash
git fetch origin
git checkout feat/notion-governance-external-base-v0
git merge --no-ff origin/codex/agent-gateway-kb-demo
```

Conflict rules:

- Current GitHub files are authoritative for branch/commit/code/test facts.
- Preserve the newest reviewed `PROJECT_STATE.md`, `DECISIONS.md`, `BACKLOG.md`, and `HANDOFF.md` content from the target branch.
- Add only the delta introduced by PR #19.
- Do not replace newer P0 priorities with the External Base work.
- Do not add a new connector subsystem if an existing Notion/base connector already covers the responsibility.
- Record unresolved semantic conflicts instead of choosing silently.

After conflict resolution:

```bash
git status
git diff --check
git commit
```

### A3. Expected PR #19 files

At minimum, verify these paths:

```text
config/external_bases/notion_project_ledger.json
docs/NOTION_DATA_GOVERNANCE_AND_EXTERNAL_BASE_V0.md
knowledge/bases/notion_project_ledger.md
scripts/external_base_manifest_smoke.py
docs/runbooks/NOTION_EXTERNAL_BASE_LOCAL_CODEX_RUNBOOK.md
```

The branch may also update `BASE_INDEX.md`, `docs/project/BACKLOG.md`, and `docs/project/HANDOFF.md`. Those updates must remain additive and fact-based.

### A4. Offline validation

Run:

```bash
python3 -m json.tool config/external_bases/notion_project_ledger.json >/dev/null
python3 -m py_compile scripts/external_base_manifest_smoke.py
python3 scripts/external_base_manifest_smoke.py
git diff --check origin/codex/agent-gateway-kb-demo...HEAD
```

Expected manifest result:

```text
ok = true
schema_version = agentops.external_base.v0
base_id = base_notion_project_ledger
provider = notion
live_sync_enabled = false
errors = []
```

Then inspect repository instructions and run all relevant CI-safe tests for the exact latest branch. Do not guess commands that are no longer present. Typical historical checks include:

```bash
python3 -m py_compile server.py scripts/*.py
python3 scripts/demo_acceptance.py
npm run build --prefix ui/start-building-app
```

Run them only after confirming the paths and commands still exist in the current branch. Live Hermes/OpenClaw, external upload, deployment, or destructive tests require separate confirmation.

### A5. Security and scope review

Reject the change if any of these are true:

- a token, secret, password, cookie, API key, or private content is committed;
- live synchronization is enabled in v0;
- Notion becomes execution/audit authority;
- `Inbox` or `Proposed` records are treated as canonical;
- external writes bypass prepared action and approval;
- workspace/project scope or provenance is omitted from future ingestion;
- raw customer content, private transcripts, or raw model exchanges are persisted by default;
- the change displaces the current P0 hardening order without an approved priority decision.

Useful local scans, when installed:

```bash
gitleaks detect --source . --no-git --redact
rg -n "(token|secret|password|api[_-]?key|private[_-]?key)" config docs knowledge scripts
```

Review findings manually; words in policy documentation are not themselves credentials.

### A6. Update evidence

After validation, update PR #19 with:

- exact feature branch HEAD;
- exact target HEAD used for synchronization;
- commands run and exit status;
- changed-file list;
- remaining failures or skipped live tests;
- confirmation that live sync remains disabled;
- confirmation that no credentials or private raw content were committed.

Update Issue #14 with the same concise verification evidence.

Do not mark the PR ready or merge it solely because documentation exists. The exact head must pass the relevant checks.

## Stage B — local connector implementation in a separate plan

Stage B starts only after a new Agent Plan is created, reviewed, and approved. Search the current implementation first. Update the existing connector/base subsystem rather than creating a duplicate.

### B1. Target capability

Implement **read-only governed ingestion** first:

```text
Notion Project Ledger
-> scoped fetch/search
-> field-map normalization
-> authority/status filter
-> provenance and content hash
-> workspace/project ACL
-> candidate or knowledge document
-> retrieval evidence
```

Do not start with bidirectional sync.

### B2. Required behavior

The implementation should consume:

```text
config/external_bases/notion_project_ledger.json
```

Minimum behavior:

1. Load and validate the manifest at startup or command invocation.
2. Refuse unknown schema versions.
3. Fetch only the configured database/data source and project scope.
4. Normalize fields through `field_map`; do not hard-code a second mapping.
5. In canonical retrieval mode, accept only `Approved` and `Implemented` records.
6. Preserve `base_id`, source record/page ID, source URL, updated time, verification state, authority class, branch, commit, and evidence hash.
7. Enforce workspace/project visibility before indexing or returning results.
8. Treat missing/invalid authority or provenance as a validation failure, not as trusted content.
9. Make repeated ingestion idempotent using stable source ID plus content hash.
10. Record run/tool/audit evidence in AgentOps MIS; Notion is not the execution ledger.

### B3. Candidate writeback, only after read-only ingestion

Candidate writeback must:

- create only `Inbox` or `Proposed` records by default;
- use a prepared action bound to normalized arguments, policy version, action hash, approval, checkpoint, and idempotency key;
- execute once after approval;
- return Notion page ID and evidence to MIS;
- prohibit automatic promotion to `Approved`, `Implemented`, or `Canonical=true`;
- avoid destructive schema/page operations.

### B4. Tests required for connector work

Add or update tests for:

- valid/invalid manifest;
- unknown schema version;
- field mapping;
- `Approved`/`Implemented` allow-list;
- `Inbox`/`Proposed` exclusion from canonical retrieval;
- workspace/project denial;
- missing provenance;
- duplicate content/idempotent retry;
- stale/conflicted record handling;
- redaction;
- prepared-action approval and exactly-once writeback;
- Notion/API failure and retry without duplicate side effects.

Use fixtures or a fake transport in CI. Real Notion calls belong in a separately confirmed integration test.

## Definition of done

### PR #19

- feature branch synchronized with the exact current target;
- conflicts resolved without replacing newer canonical project state;
- expected files present;
- manifest and Python validation pass;
- relevant repository tests pass or remaining failures are explicitly recorded;
- PR and Issue contain exact branch/commit evidence;
- live sync remains disabled;
- no credentials or private raw content committed.

### Later connector PR

- approved Agent Plan exists;
- existing connector architecture was searched and reused;
- read-only governed ingestion works with ACL and provenance;
- tests cover authority, isolation, idempotency, redaction, and failures;
- external writeback remains disabled unless separately approved and verified.

## End-of-cycle report

Codex must finish with:

```text
Repository:
Branch:
Commit:
What changed:
What did not change:
Verification:
Remaining failures:
Backlog/Handoff updates:
```

Then provide a concise Project Delta with exactly one type from:

```text
Decision | Proposal | Requirement | Task | Risk | Evidence | Question | Handoff
```

Include `duplicate_of`, `updates`, `supersedes`, or `conflicts_with` where applicable. If no durable fact changed, write:

```text
本轮无权威状态变化。
```
