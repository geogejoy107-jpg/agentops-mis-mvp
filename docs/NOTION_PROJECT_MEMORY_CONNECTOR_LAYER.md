# Notion Project Memory Connector Layer

## Purpose

Notion Project Memory is the collaboration layer for human operators and Web GPT conversations. AgentOps MIS remains the execution governance system for agent work, runtime evidence, approvals, artifacts, evaluations, and audit.

This document turns the current Notion Project Knowledge Hub, Project Control Center, Project Ledger, and Data Governance Policy into a product boundary that can be implemented safely later without confusing Notion with the MIS authority ledger.

## Current Notion Surfaces

| Surface | Role in the product |
| --- | --- |
| MIS Project Knowledge Hub | Human-readable project library and navigation hub for course materials, docs, media assets, roadmap, and knowledge index. |
| MIS Project Control Center | Operating page for branch, commit, decision, risk, handoff, and external base status. |
| MIS Project Ledger | Reviewed project memory database with Inbox, Proposed, Approved Canon, P0, Risks, Decisions, Tasks, and Handoffs views. |
| Data Governance Policy | Boundary rules for authority class, source system, lifecycle, verification state, classification, evidence hash, and external base ID. |
| External Base Registry | Registry for provider, scope, authority role, approval policy, classification, and connector capability. |

These surfaces are useful because Web GPT can read and write them through Notion, while local Codex and local agents can verify code/runtime truth through GitHub and AgentOps MIS.

## Authority Model

| Object | Authority source | Notion role | MIS role |
| --- | --- | --- | --- |
| Code, branch, commit, PR, diff, tests | GitHub | Reference and project-state summary | Link evidence only |
| Task, run, tool call, approval, artifact, evaluation, audit | AgentOps MIS SQLite/API | Summary, link, candidate follow-up | Primary authority |
| Reviewed project decision, requirement, risk, backlog, handoff | Notion Project Ledger plus `docs/project/` | Collaboration authority after review | May ingest as candidate/project context |
| Raw chat, model suggestion, temporary idea | ChatGPT Project / conversations | Context or candidate only | Never authority until reviewed |
| External connector capability and scope | External Base Registry plus versioned manifest | Human-readable registry | Enforced connector trust/readiness gate |

Notion is allowed to become the product-memory collaboration layer. It must not become the source of truth for runtime execution, approval wall state, delivery readiness, or audit evidence.

## Web GPT Collaboration Flow

Use Notion as the bridge when a Web GPT conversation produces useful project state:

1. Web GPT or a human captures a short project delta into Notion Project Ledger.
2. The delta starts as `Status=Inbox` or `Status=Proposed`, `Canonical=false`, and `Authority Class=Candidate` unless it is already backed by verified evidence.
3. Required metadata is filled before the entry can influence work:
   - `Source System`
   - `Data Domain`
   - `Data Classification`
   - `Lifecycle`
   - `Verification State`
   - `Data Steward`
   - `External Base ID` when applicable
   - `Evidence Hash` or source link when available
4. Local Codex/MIS reads the item as a candidate, compares it with GitHub and MIS ledger evidence, and records conflicts or duplicate relationships.
5. A human reviewer promotes the item to `Approved` or `Implemented` only when evidence matches.
6. MIS may create tasks, memory candidates, or agent plans from approved or explicitly selected proposed items, but external content cannot auto-promote itself.

## Connector Modes

### v0: Read/Preview Only

- Search or fetch Notion Project Ledger entries.
- Map entries into MIS candidate objects.
- Store only IDs, URLs, summaries, hashes, source system, verification state, and classification.
- Do not import raw private conversation text or full page bodies into committed repo state.
- Do not write back to Notion automatically.

### v1: Candidate Import

- Import `Inbox` and `Proposed` ledger entries into MIS review queues.
- Create `memory` candidates or project-context records with source references.
- Mark stale/conflicted entries when GitHub or MIS ledger evidence disagrees.
- Require human approval before a Notion item changes task priority, delivery status, approval state, or canonical project state.

### v2: Evidence Backlink

- Write back safe MIS evidence summaries to Notion:
  - run ID
  - task ID
  - artifact ID
  - approval ID
  - evaluation ID
  - audit hash
  - GitHub commit/PR link
- Use prepared action approval for any real Notion write.
- Omit credentials, full prompts, full raw responses, private transcripts, and customer raw content.

### v3: Controlled Bidirectional Sync

- Sync approved project state and handoff metadata with conflict detection.
- Require workspace scope, ACL, connector trust policy, and per-field authority mapping.
- Never sync MIS runtime authority fields from Notion into completed/approved state without evidence checks.

## Field Mapping

| Notion Project Ledger field | MIS mapping |
| --- | --- |
| Ledger ID | `external_object_links.external_object_id` or candidate metadata |
| Title | candidate title or task title |
| Summary | candidate summary, redacted and hash-backed |
| Type | candidate type or task category |
| Status | Notion review state; not MIS run/task state authority |
| Priority | candidate priority; requires review before task priority update |
| Module | MIS domain/module tag |
| Source System | connector source metadata |
| Authority Class | candidate/canonical/evidence/artifact/context classification |
| Data Domain | MIS object domain mapping |
| Data Classification | disclosure and sync policy |
| Verification State | quality gate for import/use |
| Evidence Hash | hash comparison and audit metadata |
| Branch / Commit / Repository | GitHub verification input |
| Next Action | candidate task suggestion |

## Safety Rules

- Notion tokens stay in environment variables or the Notion OAuth connector, never in repo or ledger payloads.
- Real Notion writes require explicit confirmation and prepared-action approval.
- Project-memory import is not allowed to ingest full private chats, full transcripts, full prompts, full raw responses, or raw customer material.
- Notion `Approved` is not enough for runtime claims; runtime claims must be verified against MIS runs, runtime events, evaluations, artifacts, and audit logs.
- Conflicted or stale Notion items must be treated as blocked candidates.
- `Canonical=true` in Notion means project-memory canonical, not execution-ledger canonical.

## Current Product Use

For now, use Notion as a collaboration channel with Web GPT:

- Web GPT can help organize project deltas, decisions, risks, and handoffs in Notion.
- Codex can read Notion as context, then verify against local repo and MIS ledger before acting.
- MIS can export safe summaries back to Notion through the existing dry-run/prepared-action export path.
- The user can use Notion to coordinate across conversations, while MIS keeps the agent execution record.

## Implementation Notes

Existing local support:

- `GET /api/integrations/notion/status`
- `GET /api/integrations/notion/export-preview`
- `POST /api/integrations/notion/dry-run-export`
- `POST /api/integrations/notion/export-confirmed`
- `POST /api/integrations/notion/import-preview`
- `POST /api/integrations/notion/sync-memory-candidates`
- `POST /api/integrations/notion/sync-tasks`
- `POST /api/integrations/notion/export-report`

Next implementation slice should add a read-only Project Ledger preview:

- `GET /api/integrations/notion/project-memory/status`
- `POST /api/integrations/notion/project-memory/preview`
- `POST /api/integrations/notion/project-memory/import-candidates`

The first slice should remain dry-run/read-only unless the user explicitly authorizes a live Notion write path.

## Acceptance

- Notion Project Memory is documented as a Web GPT collaboration layer.
- MIS runtime ledger remains authoritative for execution evidence.
- External Base Registry / manifest model remains the bridge between Notion and MIS.
- Existing Notion export remains safe by default.
- Future live writes require prepared-action approval and token omission.
- CI can verify this boundary without calling Notion or storing credentials.
