# Local Harness Proof Readback Acceptance

## Purpose

This slice turns the local task harness from "a command that can execute" into
"a proof surface that MIS can read back."

It adds a read-only operator projection for local task harness evidence:

```bash
agentops operator local-harness-proof --freshness-hours 72 --limit 8
GET /api/operator/local-harness-proof?freshness_hours=72&limit=8
```

The readback does not start Hermes, OpenClaw, workers, shell commands or live
runtimes. It only reads existing MIS ledger evidence.

## Product Boundary

- `mock` evidence is classified as `mock_ci_fallback`.
- `hermes` and `openclaw` evidence is classified as
  `real_runtime_ledger_readback` only for the returned run ids.
- This is not the stricter customer-worker live acceptance gate. It does not
  require `customer_worker_result` artifacts or approval rows.
- Customer delivery acceptance still belongs to
  `agentops operator live-product-readiness`.

## Required Evidence

A passing local harness proof row requires:

- completed run;
- completed adapter tool call;
- passing evaluation;
- runtime event;
- audit log;
- artifact/report;
- verified plan-evidence manifest.

Memory candidates and approvals are exposed as optional warnings because this
surface proves harness execution evidence, not customer delivery approval.

## Verification

Run:

```bash
python3 scripts/local_harness_proof_readback_smoke.py
python3 scripts/agent_task_harness_engineering_spec_smoke.py
python3 -m py_compile server.py agentops_mis_cli/*.py scripts/local_harness_proof_readback_smoke.py scripts/agent_task_harness_engineering_spec_smoke.py scripts/release_evidence_packet_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/local_task_harness_smoke.py
python3 scripts/secret_scan_smoke.py
git diff --check
```

Observed local result:

```text
local_harness_proof_readback_smoke: ok
workspace_id: harness-proof-smoke
ledger_mutated: false
live_execution_performed: false
token_omitted: true
```

## Safety

- No credentials are read or stored.
- No private messages, full transcripts, raw prompts or raw responses are
  stored.
- No local DB, `.env`, cache, `dist`, `node_modules` or generated artifact is
  committed.
- Readback uses Agent Gateway `tasks:read` auth and workspace scoping.

## Next Slice

Use this read model in operator readiness and Run/Agent surfaces so a human can
see whether the latest local task harness proof is mock fallback, stale, failed
or fresh real-runtime evidence.
