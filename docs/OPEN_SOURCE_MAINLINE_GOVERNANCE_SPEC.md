# Open Source Mainline Governance Spec

## Purpose

This spec fixes the merge priority for AgentOps MIS after the GitHub branch
cleanup wave. The mainline product goal is a local-first, runnable AgentOps MIS
that can manage real Hermes/OpenClaw/Agent Gateway work. Open-source base and
experiment branches may be merged into main when they strengthen that goal.
Commercial hosted-stack work must stay isolated unless the user explicitly
authorizes a commercial product lane.

## Product North Star

AgentOps MIS is a local-first control plane for human + AI work: humans use the
workspace/admin surfaces, agents use CLI/API/MCP work packets, and MIS remains
the first-party authority ledger for plans, tasks, runs, approvals, artifacts,
evaluations, memories, and audit evidence.

## Lane Priority

### P0: Local Open-Source And Runtime Base

Merge first when the slice is small, current-main based, locally runnable, and
does not move authority out of MIS:

- OSBI and open-source reference index.
- Local Open Source Experiment Base.
- Research Lab incubator and operator packets.
- Hermes/OpenClaw loop-bootstrap, loop-supervision, work packets, command
  center, action receipts, and bounded advance.
- Agent Gateway/worker loop surfaces that improve real local dogfooding.
- Spatial OS contracts, semantic maps, and Pixel Office authority readback.
- UI research specs and UI shell slices that preserve MIS routes and ledgers.
- Notion project-memory governance and external-base manifests as connector
  support, not ledger authority.

### P1: Product Hardening

Merge after P0 slices or when a P0 slice depends on it:

- Agent Plan integrity.
- Approval Wall prepared-action exact resume.
- Runtime connector trust and live-run gates.
- Workspace/scope enforcement.
- Knowledge retrieval evidence.
- SQLite reliability.
- Release evidence and deterministic CI that protect the local MVP.

### P2: Future Commercial / Hosted Stack

Do not treat this as local MVP mainline work by default:

- Hosted SaaS mode.
- Postgres storage cutover.
- BYOC deployment.
- Billing provider calls.
- Retention/destructive cleanup execution.
- Multi-tenant commercial admin/billing plans.
- Commercial release-promotion packets beyond local safety references.

Commercial material may be kept as future reference or safety gates only when
it is read-only, CI-safe, and explicitly labeled as outside the current local
MVP. It must not displace P0/P1 work.

## Branch Intake Rules

For every GitHub branch or PR under review, classify it before editing:

```text
lane: P0-local-open-source | P1-hardening | P2-commercial-future | reject
source_branch:
base_branch:
expected_user_value:
local_verification:
real_runtime_needed:
authority_boundary:
merge_strategy:
```

Use this decision table:

| Question | Required answer for mainline merge |
| --- | --- |
| Is the branch based on current `origin/main`? | Yes, or rebuild/cherry-pick into a new `codex/*-mainline` branch. |
| Does it improve local runnable AgentOps MIS? | Yes for P0/P1. |
| Does it require hosted/Postgres/BYOC/billing? | No, unless user explicitly switches to commercial lane. |
| Does it move authority to a third-party project? | No. MIS keeps first-party authority objects. |
| Can it be verified locally? | Yes: smoke, build, local API, or explicit real runtime dogfood. |
| Does it touch generated/local state? | No DB, `.env`, tokens, caches, `node_modules`, `dist`, sample exports. |
| Is the PR large/dirty/old? | Rebuild the smallest useful slice from current main. |

## Merge Strategy

Prefer rebuild over direct merge for old experiment branches:

1. Fetch current `origin/main`.
2. Create a fresh `codex/<slice>-mainline` branch or worktree.
3. Inspect the old branch diff.
4. Select the smallest product-useful slice.
5. Recreate or cherry-pick only that slice.
6. Run local verification.
7. Add acceptance docs or update existing docs.
8. Push a draft PR.
9. Wait for exact-head CI.
10. Merge only after local verification and CI agree.

Do not merge a large old branch only because it contains useful work. Useful
work is extracted; stale branch shape is discarded.

## Local Verification Standard

For P0/P1 claims, use the strongest available local evidence:

- Static/doc-only slice: focused smoke + `py_compile` + `secret_scan` +
  `git diff --check`.
- UI slice: Vite/Next build plus source smoke or Playwright snapshot when the
  route changes.
- API/CLI slice: isolated temp DB server-backed smoke.
- Runtime/dogfood slice: real Hermes/OpenClaw only when local runtimes are
  available and the action is explicitly confirmed; otherwise label evidence
  as offline/CI-safe fallback.

Mock evidence is allowed only as CI/offline fallback and must be labeled.

## Commercial Isolation Rule

Commercial branches and docs are not the default local MVP priority. They may
enter main only if one of these is true:

- The user explicitly authorizes commercial/hosted/Postgres/BYOC work.
- The slice is a read-only safety boundary that protects local MVP claims.
- The slice is moved into future-commercial docs and removed from local MVP
  readiness claims.

When commercial material enters main, it must say:

```text
commercial_lane: future/reference
local_mvp_readiness: unchanged
hosted_ready: false
billing_ready: false
postgres_required_for_local_mvp: false
live_external_side_effects_enabled: false
```

## Harness-Informed Engineering Rules

Borrow from Harness-style delivery platforms as architecture references, not
as authority replacements:

- Model delivery as typed entities and relationships, not raw API calls.
- Give agents structured work packets instead of a loose browser UI.
- Keep policy gates before side effects.
- Keep approvals inline with the work item and evidence chain.
- Expose CI/build/deploy/runtime context to agents through scoped connectors.
- Preserve local-first, first-party MIS ledgers for authority.

See `docs/research/HARNESS_ENGINEERING_RESEARCH_BRIEF.md`.

## Current Queue After This Spec

Primary queue:

1. Rebuild the remaining `codex/osbi-v1-1-mainline` loop/work-packet slices on
   top of current `origin/main`.
2. Decide whether PR #11 UI v2 should be rebuilt as a small shell/navigation
   slice or closed as superseded.
3. Decide whether PR #23 Spatial Research District art should be rebuilt as
   original-asset/product-safe slices or kept as design reference.
4. Keep commercial PR #22 and related commercial evidence work isolated unless
   the user reauthorizes commercial product work.

## Non-Goals

- No hosted deployment implementation.
- No billing provider integration.
- No Postgres migration.
- No BYOC installer.
- No direct merge of old large experiment branches.
- No third-party asset dumps.
- No replacement of MIS ledgers with an external DevOps or agent framework.
