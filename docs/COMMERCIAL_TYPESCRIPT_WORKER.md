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

External writes remain fail closed. The Worker records the intent without
calling the provider until a runtime-specific PreparedAction owner can bind
prepare, Human approval, claim, execution, and terminal reconciliation.

## Run One Task

Install and verify the Next application first:

```bash
cd ui/next-app
npm ci
npm run typecheck
npm run test:commercial-worker-contract
```

Provide the Agent credential through the environment. Credentials are rejected
as command-line arguments and are never written to the Worker receipt.

```bash
export AGENTOPS_BASE_URL="https://mis.example.com"
export AGENTOPS_WORKSPACE_ID="workspace-id"
export AGENTOPS_AGENT_ID="agent-id"
export AGENTOPS_AGENT_TOKEN="<agent-token>"
```

Run Hermes:

```bash
npm run worker:commercial -- \
  --adapter hermes \
  --confirm-run
```

Run OpenClaw:

```bash
export OPENCLAW_BIN="$(command -v openclaw)"
npm run worker:commercial -- \
  --adapter openclaw \
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
`SIGINT` or `SIGTERM`.

```bash
npm run worker:commercial -- \
  --adapter hermes \
  --confirm-run \
  --daemon \
  --poll-interval-ms 5000
```

`--max-tasks` can bound a maintenance or acceptance run. High or critical risk
tasks require `--allow-high-risk`; external-write detection still remains
PreparedAction-gated.

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
