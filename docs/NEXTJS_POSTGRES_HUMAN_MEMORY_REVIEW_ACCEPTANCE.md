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
`20260719_approval_kind_bindings_v4` schema and catalog before it reads or
derives the Owner password.

The append-only `20260718_human_session_memory_review_v1`,
`20260719_workspace_read_models_v2`, and
`20260719_human_approval_decisions_v3` migrations remain immutable. The v2
migration adds the nullable `audit_logs.workspace_id` binding plus a validated
constraint that requires every scoped row to match the workspace copied into
hashed metadata. The core DDL has bounded lock and statement timeouts. Its
supporting index is created after the receipt transaction with `CREATE INDEX
CONCURRENTLY`; a failed online stage can be retried from the exact current
receipt. The v3 migration adds durable workspace/user idempotency receipts for
Human approval decisions.

The current append-only `20260719_approval_kind_bindings_v4` migration makes
`approval_kind` explicit, required, and free of a database default. Its five
allowed values are `run_execution`, `tool_execution`, `prepared_action`,
`agent_enrollment`, and `customer_delivery`. Kind is immutable after insertion;
the approval ID and its task, run, tool, and requesting-agent execution bindings
are immutable as well. Approval rows are append-only, terminal decisions cannot
return to pending, and task/run/tool identity parents cannot be rebound behind an
approval. Audit rows are database append-only. Legacy approvals, including rows
with a prefilled kind, are classified only from deterministic child rows or
trusted audit actions; an unclassified, mismatched-prefill, or
customer-delivery-shaped row without trusted evidence aborts the migration
instead of being guessed. Deferred, initially-deferred relationship triggers on approvals, Prepared
Actions, and enrollment requests validate INSERT, UPDATE, and DELETE edges
across task, run, workspace, agent, tool call, and kind-specific child rows. A
unique enrollment-request index enforces one enrollment binding per approval.
Once a `customer_delivery` approval is decided, Postgres seals the old and new
sides of tool-call, evaluation, artifact, Agent Plan, and plan-manifest writes.
The evidence trigger shares a row lock with the Human decision, so an in-flight
evidence transaction and the terminal approval serialize. Evidence cannot be
appended, mutated, deleted, or rebound away from the decided run. The current
`20260724_customer_delivery_run_unique_v5` migration aborts without deleting or
merging rows when a run already has duplicate `customer_delivery` approvals,
then adds a partial unique index over `approvals(run_id)`.
`human_memory_schema_readiness_v5` validates the exact catalog, and
`human_memory_schema_v1_v2_v3_v4_to_v5_upgrade_v1` proves exact v1, v2, v3,
and v4 receipts upgrade to v5, including concurrent database enforcement. The
migration runner accepts only a missing receipt, an exact v1-v4 receipt, or the
exact current v5 receipt; any other receipt fails before newer DDL is executed.
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

### Approval Decision Transaction

Commercial approval decisions use the same Human Session authority through
`POST /api/mis/approvals/:approval_id/approve|reject` and the HTML fallback at
`POST /workspace/approvals/review`. Both paths require the selected workspace,
exact Origin, CSRF token, and a durable `Idempotency-Key`; only `approver` and
`owner` memberships may decide. Free Local retains the guarded Python
compatibility path, while production always calls the TypeScript/Postgres owner.

The transaction locks the Human Session and membership, request idempotency,
approval, task, run, linked tool call, Prepared Action or enrollment request,
and any customer-delivery plan evidence in one stable order. It records the
actual Human `user_id`, updates linked state, and appends workspace-bound audit
and runtime evidence atomically. Same-key replay is unchanged and emits no
duplicate evidence; different decisions, key rebinding, cross-workspace IDs,
machine credentials, stale linked state, and concurrent losing requests fail
closed.

Approving a Prepared Action only unlocks its exact resume state and never calls
the provider. High or critical ordinary tool approvals without a bound Prepared
Action return `prepared_action_required`. Enrollment approval changes only the
request and synthetic task/run; it never issues or exposes a token. Customer
delivery approval revalidates the current workspace-bound plan-evidence manifest
and requires the locked run to be completed inside the decision transaction.
Manifest steps are always derived from the locked Agent Plan. Verification reads
the complete workspace-bound tool, evaluation, and run/task artifact ledger.
Audit IDs are server-derived and cannot be caller-selected. A caller cannot hide
failed, waiting, or additional evidence by declaring only successful evidence
IDs.
Expired approvals cannot authorize an action.

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
Approval-request retention, expiry reconciliation, TypeScript entitlement
ownership, Prepared Action resume, enrollment credential issue, production
customer-delivery approval creation, and lower-risk execution receipts remain
explicit blockers; successful schema and decision contracts do not close those
execution and lifecycle gates.
This smoke also uses synthetic `source_type=manual` candidates. Separate
exact-head Hermes/OpenClaw and Agent Gateway evidence does not close the Human
Review bridge until a real Worker `source_type=run_log`, `source_ref=run_gw_*`
candidate is reviewed through this Human Session path with `actor_type=user`
and exactly one runtime event.

## Verification

```bash
export AGENTOPS_POSTGRES_DSN=postgresql://...
export AGENTOPS_TEST_POSTGRES_DSN="$AGENTOPS_POSTGRES_DSN"
python3 -B scripts/nextjs_postgres_human_memory_review_smoke.py \
  --postgres-dsn "$AGENTOPS_POSTGRES_DSN"
cd ui/next-app
npm run test:human-scrypt-contract
npm run test:human-schema-contract
npm run test:human-schema-upgrade-contract
npm run test:memory-review-idempotency-contract
npm run test:approval-decision-contract
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
`nextjs_production_python_proxy_fail_closed_v2` builds an isolated production
artifact, starts it with `next start`, checks the 13 explicitly expected compiled
API route keys, and drives 30 explicitly enumerated requests: one catch-all, ten
direct reads, two approval decisions, one Agent Gateway customer-delivery
request, and 16 legacy Workspace writes. Those 30
requests leave the reachable fake Python upstream counter at zero; this is scoped
evidence for the named compiled routes and requests, not a claim about every
production route. The v1 contract ID remains an output compatibility marker.
`nextjs_postgres_real_worker_human_review_v1` builds Next before any database or
runtime secret is introduced, hashes the `.next` artifact, starts it with
`next start`, and proves the tracked source fingerprint is unchanged. It runs in
production Postgres mode but never starts `server.py`. The existing Worker CLI uses a
hash-stored parent token from its environment, executes real Hermes and
OpenClaw adapters, writes run/tool/evaluation/artifact/audit/plan-evidence
receipts, proposes one `run_log` memory candidate per real run, and then proves
the candidate is visible and idempotently approved through an Owner Human
Session. Each real Worker produces a real completed run, its bounded evidence,
and a verified plan-evidence manifest. With an explicit opt-in flag and
`approvals:request` scope, each Worker then calls the production Agent Gateway
route; its TypeScript/Postgres owner revalidates the completed run and manifest
and creates one pending `customer_delivery` approval. The Human Session decides
the approval and replays the same decision without duplicate evidence. The
output records `worker_created_delivery_approvals: true` and
`delivery_approval_creation_source:
production_next_typescript_postgres_agent_gateway_route`.
Customer-delivery approval revalidation reads the actual run and requires a
matching Hermes/OpenClaw model provider, a completed non-dry-run provider-call
Worker tool, a matching rule evaluation, no `llm_mock` evaluation, a chained
SHA-256 audit for every artifact, chained plan/tool/evaluation audits, and the
bound `agent_worker.task_processed` audit. This raises the evidence floor but is
not a signed process-identity attestation.
It distinguishes `python_api_started: false` from Python test orchestration and
reports `real_runtime_execution_performed: true`; credentials, raw prompts, and
raw responses are omitted. A separate ephemeral guard run, which is never used
for an approved delivery, receives a failed tool, failed evaluation, and
additional artifact. The acceptance rejects forged `expected_steps` and
caller-selected audit IDs before persistence, proves a success-only manifest is
blocked by the authoritative complete-run evidence set, and requires the
production customer-delivery request to return
`409 verified_plan_evidence_manifest_required` without creating an approval or
advancing linked state.
The original real approved delivery remains untouched; append attempts for its
tool, evaluation, artifact, and manifest evidence all return
`409 customer_delivery_evidence_sealed` with zero persistence.

CI runs `nextjs_postgres_worker_task_pull_claim_v1` against Postgres to guard
scope binding, tenant isolation, bounded claim bodies, same-agent replay, and
single-winner claim concurrency. CI does not claim real Runtime execution;
the live cross-contract command remains required release evidence.

A local pre-commit run on this migration worktree observed both real OpenClaw
and Hermes provider calls with `dry_run=false`, one idempotent Human memory
decision and one production TypeScript/Postgres customer-delivery request plus
decision per completed run, cross-workspace 403 responses, and no Python API
process. This is engineering observation only: the committed blocker file
intentionally carries no subject SHA, execution timestamp, or receipt identity.
Commercial promotion still requires a fresh external exact-HEAD
OpenClaw/Hermes command receipt after the final commit plus the remaining
release gates.

The post-commit evidence path is data-driven and intentionally cannot run with
candidate-controlled harness code. After this workflow is present on protected
`main`, an operator manually dispatches
`.github/workflows/commercial-real-runtime-acceptance.yml` with an exact
candidate SHA and branch. One checkout pins the trusted `main` harness and a
second checkout pins the candidate. The trusted smoke and receipt generator test
the candidate source, recording distinct builder and subject SHAs. The private
runner labelled `agentops-real-runtime` must expose real Hermes/OpenClaw, an
isolated Postgres DSN, and Python through the protected
`commercial-real-runtime` environment. The workflow signs the hash-only receipt
with GitHub OIDC/Sigstore provenance, uploads only hashes, the offline
attestation bundle, and bounded diagnostics, and never uploads raw provider
output or credentials.
Download both files outside the repository and validate them with:

```bash
python3 scripts/commercial_migration_readiness.py \
  --human-memory-runtime-receipt /path/outside/repo/human-memory-real-runtime.json \
  --human-memory-runtime-attestation /path/outside/repo/human-memory-real-runtime.attestation.json
```

The checker resolves only `exact_head_real_runtime_receipt_missing`, and only
when `gh attestation verify` binds the receipt digest and SLSA predicate to the
pinned repository and trusted-main signer workflow/digest; the signed receipt
binds the candidate subject SHA separately. GitHub must report the referenced
run as a successful completed `workflow_dispatch` at the same builder SHA,
attempt, workflow path, repository, and allowlisted `main` ref;
the receipt is no older than 24 hours; the local worktree is clean at the same
HEAD; both adapters were explicit; the expected contract passed without a skip;
and hash-only runtime security claims prove non-dry-run provider calls, complete
tool/evaluation/artifact evidence, server-derived audit evidence, transactional
delivery revalidation, and post-decision evidence sealing. Runtime credentials are
not job-wide and dependency lifecycle scripts are disabled before the bounded
live step. The trusted builder has no release authority until the workflow is on
protected `main`, the environment enforces independent review, and the verifier
binary trust and signed Runtime identity blockers are closed. All unrelated blockers remain open. A missing receipt leaves the
checker usable for local engineering; an explicitly supplied invalid or
unattested receipt fails the readiness contract.
