# Commercial TypeScript Worker

## Ownership Boundary

The commercial Worker is implemented in `ui/next-app/src/worker/` and runs on
Node.js 20 or newer. It talks only to the production
`/api/mis/agent-gateway/*` contract and never opens PostgreSQL directly.

Python and SQLite are not dependencies of this Worker. They remain available
for Free Local compatibility and trusted acceptance orchestration only.

The Worker currently owns the governed summary workflow:

1. pull and claim one workspace-bound task
2. retrieve bounded Knowledge evidence
3. submit and verify an Agent Plan
4. start a run
5. call real Hermes or OpenClaw after explicit confirmation
6. persist Runtime Event, Tool Call, Evaluation, Artifact, candidate Memory,
   Audit, and Plan Evidence Manifest records
7. request Human customer-delivery approval only when current evidence passes
8. publish a bounded Worker heartbeat

External writes remain fail closed. Until a runtime-specific PreparedAction
owner can bind prepare, Human approval, claim, execution, and terminal
reconciliation, the Worker records the blocked intent, terminalizes the run and
task as `blocked`, closes active Tool Calls, and settles the reservation at zero
without calling the provider.

## Source-Free BYOC Worker

The customer release bundle includes explicit `worker-hermes` and
`worker-openclaw` Compose profiles. Neither profile starts by default. After an
Agent is enrolled and its one-time token is stored in the corresponding
mode-0600 secret file, start exactly the required runtime:

```bash
docker compose --env-file deploy/byoc/.env -f deploy/byoc/compose.yaml \
  --profile worker-hermes up -d worker-hermes

docker compose --env-file deploy/byoc/.env -f deploy/byoc/compose.yaml \
  --profile worker-openclaw up -d worker-openclaw
```

The Hermes profile remains one hardened uid/gid 1000 Worker container. The
OpenClaw profile instead starts two services from the same immutable image:

- `worker-openclaw` runs the TypeScript Worker as uid/gid 1000. It receives the
  OpenClaw Agent token and the shared provider-socket volume, but no OpenClaw
  binary, config, state, or workspace mount.
- `openclaw-provider` runs the OpenClaw runtime as uid 1001/gid 1000. It receives
  only the read-only OpenClaw runtime, config, and workspace mounts, its private
  `/run/openclaw-state` tmpfs, and the shared provider-socket volume. It receives
  no Agent token, control-plane credential, Human Session HMAC key, or database
  secret.

Both containers drop all Linux capabilities, set `no-new-privileges`, use a
read-only root filesystem, and enable Docker init for descendant reaping. They
communicate only through `/run/agentops-openclaw/provider.sock` in a small shared
named tmpfs volume. Their different UIDs and separate filesystems prevent the
provider process from reading the Worker's Agent token. The provider joins a
separate egress network, has no host port, and does not join the control-plane
network. Compose starts the Worker only after both the provider socket and the
control plane are healthy. Commercial control-plane and Hermes URLs require
HTTPS.

Each Worker supervisor interrupts active provider calls and retry/poll waits,
then applies a bounded forced-stop fallback before Compose's grace period
expires. The OpenClaw provider is a separate Compose lifecycle rather than a
descendant of the Worker process.

## Run One Task

Install and verify the Next application first:

```bash
cd ui/next-app
npm ci
npm run typecheck
npm run test:commercial-worker-contract
```

Provide the Agent credential through an absolute path to a bounded regular
secret file. Commercial Worker credentials are rejected from command-line
arguments and environment values and are never written to the Worker receipt.

```bash
export AGENTOPS_BASE_URL="https://mis.example.com"
export AGENTOPS_WORKSPACE_ID="workspace-id"
export AGENTOPS_AGENT_ID="agent-id"
umask 077
install -d -m 700 "$HOME/.config/agentops/secrets"
printf '%s\n' '<agent-token>' > "$HOME/.config/agentops/secrets/commercial-worker-token"
export AGENTOPS_AGENT_TOKEN_SOURCE_FILE="$HOME/.config/agentops/secrets/commercial-worker-token"
export AGENTOPS_RUN_ESTIMATED_COST_USD="1.000000"
```

Run Hermes:

```bash
npm run worker:commercial -- \
  --adapter hermes \
  --estimated-cost-usd "$AGENTOPS_RUN_ESTIMATED_COST_USD" \
  --confirm-run
```

Run OpenClaw:

```bash
export OPENCLAW_BIN="$(command -v openclaw)"
npm run worker:commercial -- \
  --adapter openclaw \
  --estimated-cost-usd "$AGENTOPS_RUN_ESTIMATED_COST_USD" \
  --confirm-run
```

Loopback HTTP is accepted only with an explicit local-development gate:

```bash
export AGENTOPS_BASE_URL="http://127.0.0.1:3001"
export AGENTOPS_ALLOW_INSECURE_LOOPBACK=true
```

Do not use that gate for hosted or shared deployments.

## Daemon Mode

The daemon uses the same one-task transaction repeatedly and stops cleanly on
`SIGINT`, `SIGTERM`, or `SIGHUP`. Provider calls and retry/poll sleeps receive a
cancellation signal, while post-provider failure evidence is still reconciled.
The BYOC Worker supervisor forwards shutdown to its TypeScript Worker process
group and applies a bounded forced-stop fallback inside the Compose grace
period. Under the OpenClaw profile, Compose supervises the provider sidecar
independently and the Worker cancels provider work over the Unix socket.

```bash
npm run worker:commercial -- \
  --adapter hermes \
  --estimated-cost-usd "$AGENTOPS_RUN_ESTIMATED_COST_USD" \
  --confirm-run \
  --daemon \
  --poll-interval-ms 5000
```

`--max-tasks` can bound a maintenance or acceptance run. High or critical risk
tasks require `--allow-high-risk`; external-write detection still remains
PreparedAction-gated.

The estimate is reserved transactionally against the workspace's concurrent,
monthly-run, and monthly-cost limits. It must be positive, cannot be supplied
as start-time `cost_usd`, and terminal heartbeat cost cannot exceed the
reservation. Until an adapter supplies a trusted provider billing receipt, the
Worker settles the approved estimate instead of reporting an unverified zero.
The estimate is a trusted Worker-side worst-case bound, not an Agent Gateway
token's provider-spend authority. Provider credentials remain inside the
Worker/runtime boundary, and the Gateway rejects any observed or settled cost
above the reservation.

Before applying the v10 cost-authority migration to an existing installation,
drain non-enrollment runs in `running` or `waiting_approval`. The migration
fails before changing the schema when such a run exists, so an operator can
reconcile it on the previous version and retry without a partial cutover.

## Evidence Semantics

A successful receipt requires all of the following:

- `provider_call_performed=true`
- `dry_run=false`
- governed Knowledge evidence consumed
- current Plan Evidence Manifest verification passed
- all required ledger records persisted

If the provider ran but later evidence persistence fails, the Worker returns:

- `provider_call_performed=true`
- `ledger_evidence_complete=false`
- `manual_reconciliation_required=true`
- no Plan Evidence Manifest or customer-delivery approval claim

That state must be reconciled before any retry. Mock adapters and deterministic
contracts are CI evidence only; commercial product acceptance requires frozen
source plus explicitly confirmed real Hermes and OpenClaw runs.

## Real Runtime Acceptance

Run the frozen-source acceptance harness against an isolated PostgreSQL
database and the production Next.js server. Its current receipt contract is
`nextjs_postgres_real_worker_human_review_v5`:

```bash
python3 scripts/nextjs_postgres_real_worker_human_review_smoke.py \
  --postgres-dsn "postgresql://<user>:<password>@127.0.0.1:<port>/<database>" \
  --worker-implementation typescript \
  --adapter hermes \
  --adapter openclaw
```

The Python process is test orchestration only. A passing commercial receipt
must report the TypeScript Worker started, the Python Worker and Python API did
not start, a real provider call ran with `dry_run=false`, and `source_commit`
matches the clean candidate `HEAD`. The harness rejects tracked or untracked
worktree changes before execution and requires the tracked source fingerprint
and Git identity to remain unchanged for the full run.

The receipt also binds the immutable Next.js release artifact before startup,
after acceptance, and after cleanup. Next runtime state under `.next/cache` and
`.next/trace` is explicitly omitted from that release hash and reported in
`next_runtime_mutable_artifact_paths_omitted`.

The same acceptance provisions distinct migrator, runtime, and entitlement
administrator database identities. Normal fixture and product writes use the
restricted runtime. The BYOC entitlement administrator receives only its admin
DSN, the operator password, the control-plane HTTPS URL, and non-secret operator
identity/Origin configuration. The request URL is provided through
`AGENTOPS_ENTITLEMENT_CONTROL_PLANE_URL`; optional Origin/CSRF binding uses
`AGENTOPS_ENTITLEMENT_CONTROL_PLANE_ORIGIN`. It waits for control-plane health
and requires the workspace-scoped v11 challenge route before the one-shot
command starts; the legacy direct-table path therefore fails closed when that
API is absent. Non-loopback requests require HTTPS, and the Compose-internal
plain HTTP service address is not a commercial authentication channel. It never
receives the runtime/migrator DSN or Human Session HMAC key. Preflight response
bodies are not read, and URLs, cookies, CSRF values, passwords, and challenge
tokens are not logged. Next receives only the runtime DSN, while the TypeScript
Worker receives no database or Human Session credential. Caller
`DATABASE_URL`, libpq `PG*`, Postgres component, and secret-file variables are
removed before child-process launch.

Provider-visible assistant text and provider error detail are never persisted as
summaries. Adapters return fixed omission text, and the Commercial Worker
independently replaces adapter summary/error fields before writing runtime,
tool, run, artifact, audit, or receipt evidence. The retained provider evidence
is limited to bounded execution metadata and a SHA-256 payload hash.

A success receipt is emitted only after the `.next` artifact hash remains
unchanged before startup, after acceptance, and after teardown, and after the
ephemeral schemas and restricted roles are absent from the PostgreSQL catalog.

### Exact-Head Promotion Status

Keep the harness receipt outside the repository, validate it against the exact
candidate commit, then publish two bounded GitHub commit status contexts:

```bash
head_sha="$(git rev-parse HEAD)"
receipt="$(mktemp -t agentops-real-runtime.XXXXXX.json)"

python3 scripts/nextjs_postgres_real_worker_human_review_smoke.py \
  --postgres-dsn "postgresql://<user>:<password>@127.0.0.1:<port>/<database>" \
  --worker-implementation typescript \
  --adapter hermes \
  --adapter openclaw > "$receipt"

node scripts/commercial-runtime-status.mjs validate \
  --receipt "$receipt" --sha "$head_sha"
node scripts/commercial-runtime-status.mjs publish \
  --receipt "$receipt" --sha "$head_sha"
rm -f "$receipt"
```

Publishing requires an authenticated `gh` CLI identity with commit-status write
authority. It creates `agentops/real-hermes` and `agentops/real-openclaw` only
after the receipt proves real non-dry-run provider calls, TypeScript Worker plus
PostgreSQL ownership, verified manifests, Human delivery decisions, settled
cost reservations, fixture cleanup, and no Python Worker/API. A new commit has
no inherited runtime authority and must run the acceptance again.

The publisher hashes the exact receipt bytes once, writes a bounded attestation
as an exact-commit GitHub comment, and points both statuses to that comment. The
promotion gate verifies the repository owner as publisher, the exact commit,
shared receipt digest, status descriptions, target URL, and current attestation
body. It does not trust same-named contexts from another publisher.

This is an operator attestation whose trust root is the authorized repository
owner. It proves exact-commit consistency, publisher identity, and receipt
integrity after publication; it is not a provider-signed proof that makes a
malicious repository owner unable to fabricate an input receipt. Independent
provider-signed or fixed GitHub App evidence remains required before treating
the status as third-party-verifiable execution provenance.
