# Commercial Migration Clean-Room Breakdown

## Final Product Boundary

The commercial control plane is a first-party AgentOps MIS service with this
production stack:

- Next.js 16 App Router
- TypeScript on Node.js 20 or newer
- PostgreSQL 16
- explicit Hermes and OpenClaw runtime adapters
- Human Session, RBAC, approval, audit, and evidence authority owned by MIS

Python and SQLite remain supported only for Free Local, deterministic test
orchestration, migration verification, and an explicitly selected rollback
path. A production or shared deployment must never proxy a control-plane
mutation to Python or treat SQLite as commercial authority.

## Source Strategy

The historical commercial migration branch diverged before current `main` and
is an evidence/reference lane. It must not be merged or rebased wholesale.

Every production owner is rebuilt as a small commit from current `origin/main`.
The integration sequence is:

1. prove the production boundary fails closed
2. add explicit PostgreSQL schema and migration ownership
3. add one TypeScript route owner at a time
4. prove the route without a Python upstream
5. run real Hermes and OpenClaw acceptance on a frozen source commit
6. promote only after current-head CI, upgrade, rollback, and BYOC gates pass

Old code may inform behavior and negative tests, but old schema assumptions,
receipt shapes, authentication shortcuts, and generated artifacts are not
authoritative.

## Non-Negotiable Rules

- Production writes are Next.js/TypeScript/PostgreSQL only.
- Unknown production routes return a bounded fail-closed response.
- Free Local Python proxying uses an explicit allowlist and loopback binding.
- Production startup requires a valid PostgreSQL DSN and current schema
  checksum; it cannot silently fall back to Python or SQLite.
- Agent credentials may request Human review but may not approve, reject,
  assign an approver, or forge Human audit attribution.
- Workspace, task, run, agent, plan, manifest, approval, and prepared-action
  bindings are checked at every ownership boundary.
- Raw prompts, responses, transcripts, provider output, credentials, tokens,
  and private messages are never committed as evidence.
- Mock evidence is CI fallback only. Product-readiness claims require real,
  explicitly confirmed Hermes and OpenClaw provider calls.
- Release, handoff, and merge authority remain false until all listed gates are
  current for the exact source commit.

## Migration Lanes

### Lane 0: Runtime Boundary

Own the commercial Next entry point, explicit deployment mode, loopback-only
Free Local startup, and production Python-proxy denial.

Exit gate:

- production build starts through the packaged command
- unknown production reads and writes fail closed
- upstream Python receives zero production requests
- Free Local proxies only allowlisted operations

### Lane 1: PostgreSQL Schema And Startup

Own an explicit current-main baseline, ordered migrations, checksums,
transactional locking, readiness checks, backup, restore, and BYOC bootstrap.

Exit gate:

- fresh PostgreSQL 16 bootstrap passes
- migration reapply is idempotent
- checksum/version drift fails closed
- ambiguous historical data rolls back atomically
- production startup cannot bypass readiness

### Lane 2: Agent Identity And Plans

Own Agent Gateway token/session authentication, workspace and scope binding,
task/run lifecycle, Agent Plan submission/verification, and evidence manifests.

Exit gate:

- token and session values are hash-only at rest
- current plan version, plan hash, verification timestamp, and verification
  result hash bind the run and manifest
- cross-workspace and cross-agent requests fail closed
- no Python process is needed

### Lane 3: Customer Delivery And Human Review

Own customer-delivery approval requests, Human Session/RBAC/CSRF decisions,
replay behavior, and task/read-model transitions.

Exit gate:

- only completed real Hermes/OpenClaw runs with current verified evidence can
  create a pending delivery approval
- one run has at most one customer-delivery approval
- Agent self-approval is impossible
- Human decisions are same-origin, session-bound, workspace-scoped, and audited

### Lane 4: Prepared Actions

Own preparation, Human approval, claim leases, provider execution receipts,
response-loss reconciliation, and terminal no-retry behavior.

Exit gate:

- `action_id`, action hash, plan, approval, task, run, and requester bindings
  are immutable
- concurrent claims have one durable winner
- success, failure, and unknown outcomes are append-only
- an outcome that may have executed cannot be retried automatically
- raw provider output is omitted

### Lane 5: Read Models And Supervision

Own workspace task/run detail, run graph, tool/evaluation/artifact/audit reads,
operator supervision, Memory review, and evidence packets.

Exit gate:

- every read is workspace-authoritative
- machine credentials cannot impersonate Human actors
- browser workflows have complete production-owned replacements
- retired Python routes have parity evidence

### Lane 6: Enrollment And Entitlements

Own enrollment request/approval, one-time token issue, session lifecycle,
commercial entitlements, quotas, and policy decisions.

Exit gate:

- issued tokens are shown once and stored hash-only
- concurrent issue has one winner
- entitlement denial is fail-closed and audited
- safe Human rejection remains available during entitlement failure

### Lane 7: Deployment And Promotion

Own container/BYOC packaging, configuration, upgrade, backup/restore, rollback,
observability, retention, release evidence, and promotion.

Exit gate:

- a clean customer environment installs without repository-local state
- upgrade and rollback preserve authority data
- current-head GitHub CI and supply-chain receipts pass
- frozen-source real Hermes and OpenClaw acceptance passes
- no release claim depends on an old branch or mock runtime

## Current Integration State

As of 2026-07-24:

- Lane 0 is implemented and locally accepted on the fresh-main integration
  branch.
- Lane 1 has an explicit current-main PostgreSQL baseline and v1-v5 bridge
  accepted against real PostgreSQL 16; the TypeScript runner/readiness owner is
  still in progress.
- The Worker has an explicit, default-off customer-delivery review request, but
  the fresh-main TypeScript/PostgreSQL approval owner is still in progress.
- Historical real Hermes/OpenClaw evidence is valid for the evidence branch
  only. Fresh-main real-runtime acceptance has not yet been claimed.
- Lanes 2 through 7 remain partially open. Release, handoff, and merge authority
  are false.

## Definition Of Done

The migration is complete only when every production mutation and required read
has a TypeScript/PostgreSQL owner, all Python production fallbacks are removed
or explicitly disabled, customer installation and rollback are proven, and the
same frozen commit passes both real Hermes and OpenClaw closed-loop acceptance.
