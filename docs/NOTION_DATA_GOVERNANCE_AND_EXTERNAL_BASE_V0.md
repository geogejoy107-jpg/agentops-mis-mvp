# Notion Data Governance and External Base v0

> Status: bounded v0 implementation
> Owner: Project Owner
> Source PR: #19 rebuilt onto current `main`
> Implementation branch: `codex/notion-external-base-mainline`
> Target branch: `main`

## 1. Purpose

This work turns the existing Notion Project Ledger into a governed project-information base and gives AgentOps MIS a versioned contract for recognizing that base.

It does **not** make Notion the execution ledger. Authority remains split by data object:

| Data object | Authority |
|---|---|
| Repository, branch, commit, PR, diff, tests | GitHub |
| Task execution, run, tool call, approval, artifact, evaluation, memory review, audit | AgentOps MIS SQLite/API |
| Reviewed project state, decisions, requirements, risks, backlog, handoff | Notion Project Ledger plus `docs/project/` |
| Raw conversation context and model-generated ideas | ChatGPT Project; candidate context only |

The v0 objective is therefore:

```text
Notion registry and governance metadata
-> versioned External Base manifest
-> Markdown knowledge-base entry
-> offline validation
-> later approval-gated connector work
```

## 2. MIS Requirements

### Stakeholders

- Project owner: decides authority, approval, retention, and priority.
- Human operator/reviewer: classifies and reviews project deltas.
- AI agent: retrieves approved knowledge and proposes candidate records.
- Developer/operator: maintains connector and schema contracts.
- Auditor/customer reviewer: verifies provenance without receiving raw private content.

### Functional requirements

1. Register each external project source with a stable `base_id`.
2. Declare provider capabilities: read, search, write, sync, webhook.
3. Declare authority roles and scope.
4. Classify project records by domain, sensitivity, lifecycle, and verification state.
5. Distinguish candidate records from canonical records.
6. Preserve source, branch, commit, evidence hash, steward, and verification date.
7. Require explicit confirmation for external writes.
8. Make the integration contract version-controlled and testable.

### Non-functional requirements

- Local-first and dependency-free validation.
- No credential storage in GitHub or Notion registries.
- No raw prompts, raw model responses, private transcripts, or unredacted customer content by default.
- Workspace/ACL and provenance are mandatory before live ingestion.
- Idempotent external write contract.
- Additive rollout and reversible changes.

## 3. Data Governance Model

The Project Ledger adds these governance dimensions:

| Field | Purpose |
|---|---|
| `Authority Class` | Candidate, Canonical, Evidence, Artifact, or Context |
| `Source System` | Notion, GitHub, AgentOps MIS, ChatGPT Project, Local, or Other |
| `Data Domain` | Project State, Decision, Backlog, Handoff, Code, Run, Audit, Knowledge, Customer, or Integration |
| `Data Classification` | Public, Internal, Confidential, or Controlled |
| `Lifecycle` | Capture, Review, Active, Stale, or Archive |
| `Verification State` | Unverified, Verified, Stale, or Conflicted |
| `Data Steward` | Role responsible for review and maintenance |
| `External Base ID` | Stable link to the External Base Registry |
| `Last Verified At` | Freshness and revalidation evidence |
| `Evidence Hash` | Compact evidence/version fingerprint |

Lifecycle:

```text
Capture -> Classify -> Review -> Approve -> Active -> Reverify -> Archive
```

Quality gates:

- completeness;
- consistency;
- accuracy;
- timeliness;
- traceability;
- uniqueness.

A record retrieved from Notion is not execution authority merely because it was found. `Inbox` and `Proposed` remain candidate context. Only reviewed `Approved` or evidence-backed `Implemented` records are eligible to guide canonical project state.

## 4. External Base Registry

The Notion `External Base Registry` records:

- stable Base ID and provider;
- authority roles;
- connection status;
- read/search/write/sync/webhook capabilities;
- approval policy;
- data classification;
- workspace/project/repository/branch/data-source scope;
- owner, verification date, review date, and notes.

Initial registered bases:

1. `base_notion_project_ledger`
2. `base_github_agentops_mis`
3. `base_chatgpt_project_context`
4. `base_agentops_mis_local`

The registry stores metadata only. It does not store tokens or credentials.

## 5. Machine-Readable Contract

Manifest:

```text
config/external_bases/notion_project_ledger.json
```

The manifest declares:

- resource IDs;
- authority roles;
- capability flags;
- approval policy;
- governance rules;
- Notion field mapping;
- ingestion and export constraints;
- implementation paths and v0 live-sync state.

The manifest is the versioned contract between project governance and future connector implementation. It does not itself execute a sync.

## 6. Immediate MIS Integration Path

Knowledge entry:

```text
knowledge/bases/notion_project_ledger.md
```

The current MIS already indexes Markdown under `knowledge/` and `docs/` using SQLite FTS5. Adding the governed base entry makes the source discoverable through the existing knowledge path without introducing a second runtime or storing Notion content in an ungoverned way.

Validation:

```bash
python3 scripts/external_base_manifest_smoke.py
```

The validator checks:

- schema and required fields;
- capability booleans;
- approval and destructive-action policy;
- candidate/canonical separation;
- provenance and workspace-ACL requirements;
- raw prompt/transcript/credential prohibitions;
- live sync disabled in v0;
- absence of credential-like keys.

## 7. Relationship to Existing Notion Connector Work

The repository already contains Notion preview/export and approval-resume work. This v0 does not create a competing connector. It adds the missing project-source governance contract:

```text
Existing connector execution path
+ External Base Registry
+ versioned manifest
+ data-quality and authority metadata
+ governed knowledge entry
```

Future connector work should consume the manifest rather than hard-code a second source model.

## 8. Roadmap

### v0 — Registry and contract

- Notion governance schema and views;
- External Base Registry;
- Data Governance Policy;
- versioned manifest;
- Markdown knowledge entry;
- offline validator.

### v1 — Read-only governed ingestion

- fetch only scoped records;
- ingest only `Approved` / `Implemented` plus provenance;
- enforce workspace/project ACL;
- record source version/hash and retrieval evidence;
- mark stale/conflicted records instead of silently overriding.

### v2 — Approval-gated candidate writeback

- create only `Inbox` / `Proposed` by default;
- prepared action, action hash, explicit confirmation, idempotency key;
- return Notion page ID and evidence to MIS;
- human-only canonical promotion.

### v3 — Incremental synchronization

- polling or webhook cursor;
- conflict detection and reconciliation queue;
- retry/dead-letter state;
- connector health and freshness metrics.

### v4 — Multi-workspace governance

- per-workspace ACL and access tags;
- data-quality dashboard;
- stewardship review queue;
- retention and archival policies;
- connector policy packages.

## 9. Explicit Non-Goals for v0

- no automatic two-way sync;
- no credentials or connector tokens;
- no automatic canonical promotion;
- no replacement of GitHub or MIS authority;
- no customer/private raw-content ingestion;
- no destructive Notion schema cleanup;
- no change to the current P0 hardening order.

## 10. Rollback

- GitHub: close/revert the feature PR.
- Notion: archive the new registry/policy pages; leave additive fields unused unless explicit deletion is approved.
- Runtime: no production/runtime state is changed by v0.
