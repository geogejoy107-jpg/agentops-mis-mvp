# Commercial Agent Gateway Core Owner Status

Status date: 2026-07-24

## Owned Production Boundary

The following `/api/mis` routes have specific Next.js route files and direct
TypeScript/PostgreSQL owners:

- `GET /agent-gateway/tasks/pull`
- `GET /agent-gateway/tasks/:taskId`
- `POST /agent-gateway/tasks/:taskId/claim`
- `POST /agent-gateway/agent-plans`
- `GET /agent-gateway/agent-plans/:planId/verify`
- `POST /agent-gateway/runs/start`
- `POST /agent-gateway/runs/:runId/heartbeat`
- `POST /agent-gateway/tool-calls`
- `POST /agent-gateway/evaluations/submit`
- `POST /agent-gateway/artifacts`
- `POST /agent-gateway/plan-evidence-manifests`

Production execution uses the shared Agent Gateway token/session authority,
PostgreSQL transactions, row and advisory locks, workspace/agent/task/run
bindings, bounded JSON bodies, immutable replay checks, and the append-only
audit/runtime ledgers. These owners do not start or proxy to Python.

Python proxy compatibility is limited to an explicit
`AGENTOPS_DEPLOYMENT_MODE=free_local` plus
`AGENTOPS_CONTROL_PLANE_MODE=proxy` selection. It is not a production fallback.

## Plan And Receipt Binding

Agent Plan hashes use the current Python canonical JSON byte contract,
including `plan_version`. Verification persists `verified_at` and
`verification_result_hash`. Non-mock run start requires the current persisted
verification and writes both `runs.agent_plan_id` and `runs.plan_hash`.

Evidence writes recheck that run binding. Plan evidence manifests bind the
current plan hash and verification-result hash and reject caller-supplied stale
hashes. Artifact content is omitted; a lowercase SHA-256 digest is stored.
Sensitive JSON keys and token-like values are redacted before ledger storage.

## Acceptance

`agent-gateway-core-postgres-contract.ts` creates a disposable PostgreSQL
schema, applies the current migration runner, and covers:

- bearer token and child session authentication
- cross-workspace and cross-agent denial
- pull and two-agent claim concurrency
- Agent Plan create, canonical verification, and hash drift
- run-to-plan binding and cross-agent heartbeat denial
- tool, evaluation, artifact, and manifest immutable replay
- stale manifest plan-hash rejection
- raw prompt, raw response, and token omission
- zero requests to a configured Python upstream observer

`agent-gateway-core-production-boundary.ts` statically verifies the specific
route ownership, bounded bodies, explicit Free Local proxy switch, and absence
of Python process/proxy calls in production owners.

## Still Not Owned By This Slice

This slice does not migrate or claim production ownership for:

- Knowledge routes
- Agent register or agent heartbeat
- Gateway audit write
- Runtime Events write
- Memory routes
- Prepared Action routes
- Human approval decisions
- read-model and supervision routes outside the task detail above

Because the current Worker also uses some of those routes, this status is not a
fresh-main real Hermes/OpenClaw closed-loop or commercial release claim. That
acceptance must run only after the remaining Worker-required owners are
integrated on one frozen commit.
