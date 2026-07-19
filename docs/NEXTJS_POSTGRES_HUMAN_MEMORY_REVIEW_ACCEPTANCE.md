# Next.js/Postgres Human Memory Review Acceptance

## Commercial Ownership

Team and Enterprise direct mode owns Human Session establishment, validation,
logout, candidate listing, and candidate Memory Review in Next.js/TypeScript
with Postgres persistence. `AGENTOPS_DEPLOYMENT_MODE=production`, or a standard
`next start` process with `NODE_ENV=production` and no explicit deployment
mode, defaults to this path. `AGENTOPS_CONTROL_PLANE_MODE=proxy` is an explicit
rollback only in `local` or `free_local` deployment mode
(`AGENTOPS_TS_CONTROL_PLANE_MODE` remains a compatibility alias). Commercial
production rejects the generic catch-all with `typescript_route_owner_required`;
Human Memory Review also returns `human_session_direct_route_required` instead
of downgrading a Human decision to the Python compatibility actor. Unknown
deployment-mode values fail configuration closed.

The Python/SQLite `server.py` schema intentionally does not define
`workspace_memberships`, `human_login_credentials`, `human_sessions`,
`human_login_throttle`, or `human_memory_review_requests`. These commercial
tables have one owner: the checksummed Postgres migration executed by the
Node/TypeScript control plane.

The Human Session cookie is `agentops_human_session`. The browser receives an
opaque token in an `HttpOnly; SameSite=Strict` cookie, while Postgres stores only
an HMAC hash. HTTPS origins receive `Secure`; literal loopback HTTP origins do
not. State-changing requests require an exact configured Origin/Host match and
an HMAC-derived CSRF token bound to the same session. Agent Gateway tokens and
workspace administration keys are rejected rather than translated into a Human
identity.

Single-membership Sessions may infer their workspace. Multi-membership Sessions
must select one explicitly before tenant reads or review decisions. Login and
logout write one audit event per active membership using the same opaque Session
reference, so every affected workspace receives the auth event and a caller
cannot choose its sole audit attribution. Logout remains available after all
memberships are disabled and then writes only an unscoped global audit event.

The Free Local Next-to-Python rollback bridge treats this cookie name as
reserved. Both the catch-all proxy and dedicated control-plane proxy remove
`agentops_human_session` from outbound `Cookie` headers while preserving machine
`Authorization`, and suppress any upstream `Set-Cookie` that tries to set the
reserved name. Other compatibility cookies may pass through.

The 16 legacy Workspace mutation bridges exist only for explicit Free Local
rollback. Before parsing a form or contacting Python, each bridge requires an
exact Origin/Host match and rejects cross-site Fetch Metadata. The legacy
approval and memory-review forms also accept only the exact `approve` or
`reject` decision; unknown values fail before any upstream request.

Workspace authorization comes only from the locked
`workspace_memberships(workspace_id,user_id)` row. `users.role` is not an
authorization source. `viewer` and `operator` may read their workspace candidate
queue; only `approver` and `owner` may approve or reject. The UI applies the same
role boundary, but the API remains authoritative.

## First Owner

The commercial first-deployment bootstrap is a local Node/TypeScript/Postgres
CLI, not an HTTP route:

```bash
cd ui/next-app
AGENTOPS_POSTGRES_DSN=postgresql://... npm run migrate:postgres
AGENTOPS_POSTGRES_DSN=postgresql://... npm run schema:readiness
AGENTOPS_POSTGRES_DSN=postgresql://... npm run bootstrap:owner -- \
  --workspace-id acme \
  --username owner \
  --display-name "Workspace Owner"
```

The default prompt is hidden and requires confirmation. Non-interactive secret
managers may pipe exactly one line with `--password-stdin`; password argv flags
are rejected. The transaction takes a global bootstrap advisory lock, fails
closed if any Owner membership already exists, and atomically creates the user,
active Owner membership, fixed-parameter scrypt credential, and a truthful
`actor_type=system` bootstrap audit. No session is created and no password,
salt, hash, DSN, or setup code is returned. Bootstrap validates the exact
`20260719_workspace_read_models_v2` schema and catalog before it reads or
derives the Owner password.

The original `20260718_human_session_memory_review_v1` migration remains
immutable. The append-only `20260719_workspace_read_models_v2` migration adds
the nullable `audit_logs.workspace_id` binding plus a validated constraint that
requires every scoped row to match the workspace copied into hashed metadata.
The core DDL has bounded lock and statement timeouts. Its supporting index is
created after the receipt transaction with `CREATE INDEX CONCURRENTLY`; a
failed online stage can be retried from the exact current receipt. The migration
runner accepts only a missing receipt, the exact v1 receipt, or the exact
current receipt; any other receipt fails before v2 DDL is executed.
TypeScript audit writers must supply the workspace explicitly; the same value
is included in hashed metadata, and tenant reads require both copies to match.
Legacy rows without a trustworthy binding stay unscoped and are excluded from
tenant reads. They may enter a workspace read model only after an approved
migration supplies an auditable, trusted workspace mapping; v2 never guesses one.

This is intentionally global first-deployment bootstrap. Subsequent workspace,
membership, invitation, credential rotation, recovery, and user lifecycle
provisioning are not implemented by this slice and remain a release gap. Do not
reuse the bootstrap CLI as a general user administration mechanism.

## Review Transaction

The mutation lock order is session, workspace membership, idempotency key,
memory, global audit chain. A successful transition stores the hashed
idempotency key and request hash, changes exactly one `candidate` to `approved`
or `rejected`, assigns the real Human `user_id`, emits one `actor_type=user`
audit, and emits one runtime event. Same-request replay is unchanged; conflicting
key reuse or a second terminal decision fails with `409`.

Foreign and missing memory IDs return the same workspace-scoped `404`. Body
limits are enforced incrementally before authentication or database access,
including requests without `Content-Length`. Audit/runtime evidence omits
credentials, session tokens, CSRF values, idempotency keys, raw request bodies,
and canonical memory content.

Session and membership rows stay locked through the mutation. A revocation that
wins its row lock causes the waiting review to fail without memory, request,
audit, or runtime-event writes.
Malformed `blocked_until` values remain blocked, malformed login-window values
enter the block state, malformed Human Session `expires_at` values expire, and
Agent Gateway Sessions require a non-null valid expiry. Corrupted timestamp
state therefore cannot fail open; long-lived parent tokens may still explicitly
use a null expiry.

## Release Gates

Production ingress must apply a trusted-proxy-aware source-IP rate limit to
Human sign-in. The in-process admission limit bounds scrypt/DB work in one
Next.js process and does not replace the edge control. Scheduled retention for
expired/revoked sessions and completed review idempotency rows, plus a
precompiled Owner bootstrap production artifact, are not complete in this
slice. `docs/HUMAN_MEMORY_REVIEW_RELEASE_BLOCKERS.json` keeps those gaps
machine-readable and forbids release or closed-loop claims while they remain
open. It also records that all remaining UI/read-model APIs need explicit
TypeScript/Postgres owners now that the production Python catch-all is blocked.
This smoke also uses synthetic `source_type=manual` candidates. Separate
exact-head Hermes/OpenClaw and Agent Gateway evidence does not close the Human
Review bridge until a real Worker `source_type=run_log`, `source_ref=run_gw_*`
candidate is reviewed through this Human Session path with `actor_type=user`
and exactly one runtime event.

## Verification

```bash
python3 -B scripts/nextjs_postgres_human_memory_review_smoke.py
cd ui/next-app
npm run test:human-scrypt-contract
npm run test:human-schema-contract
npm run test:memory-review-idempotency-contract
npm run typecheck
npm run build
```

`nextjs_postgres_human_memory_review_v1` starts an isolated Postgres schema and
the real Next.js server without starting the Python API. It executes the
Node/TypeScript Owner bootstrap twice, verifies the second attempt fails,
exercises raw chunked body truncation, Origin/cookie/CSRF/session/RBAC behavior,
tenant hiding, idempotent and competing reviews, session/membership revocation
races, exact audit/runtime evidence, proxy cookie isolation in both directions,
and a Playwright UI flow at desktop and mobile viewports.
Browser acceptance loads opaque session cookies through a temporary
owner-only Playwright storage-state file that is deleted immediately after
loading; generated Human passwords and session cookies are never passed in
process arguments.

## Real Worker Bridge

The durable Worker path is owned route-by-route by Next/TypeScript/Postgres for
`register`, `tasks/pull`, `tasks/:task_id/claim`, `heartbeat`, and `audit`, in
addition to the existing plan/run/tool/evaluation/artifact/memory/manifest
routes. Next rewrites the canonical CLI path `/api/agent-gateway/*` to the
same direct TypeScript handlers under `/api/mis/agent-gateway/*`; Free Local
continues to proxy these routes to the Python/SQLite control plane.

Run the live cross-contract acceptance against an isolated Postgres schema and
locally authorized Runtime processes:

```bash
python3 -B scripts/worker_provider_call_evidence_smoke.py
python3 -B scripts/nextjs_production_python_proxy_fail_closed_smoke.py
python3 -B scripts/nextjs_postgres_real_worker_human_review_smoke.py \
  --postgres-dsn postgresql://agentops@127.0.0.1:5432/agentops
```

`worker_provider_call_evidence_v1` is a no-API unit contract: both live adapters
must report `provider_call_performed: true` and `dry_run: false`, while their
unconfirmed paths must report the inverse and retain the confirmation gate.
`nextjs_production_python_proxy_fail_closed_v1` starts a real Next process with
a reachable fake Python upstream and proves an unowned production route returns
503 without sending any upstream request.
`nextjs_postgres_real_worker_human_review_v1` starts Next in production
Postgres mode but never starts `server.py`. The existing Worker CLI uses a
hash-stored parent token from its environment, executes real Hermes and
OpenClaw adapters, writes run/tool/evaluation/artifact/audit/plan-evidence
receipts, proposes one `run_log` memory candidate per real run, and then proves
the candidate is visible and idempotently approved through an Owner Human
Session. The output distinguishes `python_api_started: false` from Python test
orchestration and reports `real_runtime_execution_performed: true`; credentials,
raw prompts, and raw responses are omitted.

CI runs `nextjs_postgres_worker_task_pull_claim_v1` against Postgres to guard
scope binding, tenant isolation, bounded claim bodies, same-agent replay, and
single-winner claim concurrency. CI does not claim real Runtime execution;
the live cross-contract command remains required release evidence.

The migration branch has also passed this cross-contract independently with
the real OpenClaw and Hermes adapters: both provider calls were non-dry-run,
each resulting `run_log` candidate was approved exactly once through Human
Session, cross-workspace access returned 403, and the Python API was never
started. This closes the bridge-implementation blocker; commercial promotion
still requires fresh exact-HEAD OpenClaw and Hermes receipts after the final
commit plus the remaining release gates.
