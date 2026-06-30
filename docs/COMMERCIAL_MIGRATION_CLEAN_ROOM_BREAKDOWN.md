# Commercial Migration Clean-Room Breakdown

## Scope

PR #22 (`codex/commercial-migration-closed-loop`) is not safe to merge as a
single branch. The latest GitHub readback shows:

- merge state: `CONFLICTING`
- changed files: `254`
- additions: `55257`
- deletions: `1129`
- old green CI from 2026-06-24, before the current mainline commercial and
  spatial slices landed

This document turns that large branch into a clean-room extraction plan. Future
work should rebuild small product slices from current `origin/main`, using PR
#22 as reference evidence only, instead of rebasing and merging the full branch.

## Non-Negotiable Rules

- Do not merge PR #22 directly.
- Do not copy generated docs, DB files, caches, `node_modules`, `dist`, `.env`,
  local SQLite files, or secret-bearing config.
- Do not introduce hosted, billing, Postgres, destructive cleanup, or remote
  worker claims without a dedicated acceptance gate.
- Keep each extraction slice reviewable: normally 2-8 files, focused smoke,
  acceptance doc, and CI/release-evidence wiring.
- Preserve MIS authority boundaries: commercial config, workspace/RBAC,
  storage, worker fleet, external bases, approvals, audit, and evidence packets
  must stay first-party AgentOps MIS objects.

## Extraction Lanes

### Lane 1: Commercial Read Models

Goal: expose read-only commercial status packets without billing or cleanup.

Candidate artifacts:

- commercial status/readiness summaries
- current evidence status projections
- CLI readback commands

Gate:

- no billing provider call
- no cleanup execution
- no hosted-readiness claim
- `token_omitted=true`

### Lane 2: Workspace And RBAC Scope

Goal: scope human/admin read APIs by workspace without breaking local demo.

Candidate artifacts:

- workspace-scoped task/run/tool/eval/audit reads
- memory/session/enrollment visibility rules
- fail-closed workspace spoofing smoke

Gate:

- cross-workspace reads fail closed
- local single-workspace demo remains usable
- no raw token/session hash exposure

### Lane 3: Storage Boundary

Goal: centralize SQLite read/write helpers before any Postgres adapter claim.

Candidate artifacts:

- `repo_*` helpers for task/run/memory/approval/evaluation/artifact/audit
- storage boundary map
- isolated SQLite parity smoke

Gate:

- no Postgres dependency required for local MVP
- helper parity proves old and new code paths return equivalent safe read models
- migrations remain reversible or previewable

### Lane 4: Commercial Evidence Packets

Goal: produce operator evidence packets for promotion review.

Candidate artifacts:

- release/handoff/current-evidence packet generators
- exact-head CI readback
- rerun bundle previews

Gate:

- packets are generated from current source, not stale tracked snapshots
- no raw logs, prompts, responses, DBs or secrets
- exact current-head CI is required before promotion claims

### Lane 5: UI Route Retirement And Parity

Goal: retire legacy/admin duplicate routes only after workspace replacements
are proven.

Candidate artifacts:

- route inventory
- UI/API parity matrix
- legacy route alias smoke

Gate:

- every retired route has a workspace replacement
- browser users still have a visible path to tasks/runs/approvals/evidence
- no iframe or generated UI dump is introduced

### Lane 6: Deployment And BYOC Readiness

Goal: document local/customer deployment without claiming hosted SaaS readiness.

Candidate artifacts:

- local deployment runbook
- BYOC acceptance smoke
- production auth fail-closed smoke

Gate:

- production/shared mode fails closed without configured admin credentials
- customer-server mode is explicit and does not ingest secrets into repo
- billing remains disabled until a separate billing gate exists

## Recommended Order

1. Lane 1 commercial read models
2. Lane 4 evidence packets
3. Lane 2 workspace/RBAC scope
4. Lane 3 storage boundary
5. Lane 5 UI route retirement
6. Lane 6 deployment/BYOC readiness

This order keeps demo/product usefulness visible while avoiding a big-bang
commercial migration.

## Next Slice

Start with Lane 1 or Lane 4. Rebuild from current `origin/main`, bring over only
the smallest necessary source ideas from PR #22, and verify with a new smoke plus
release-evidence wiring before opening a PR.
