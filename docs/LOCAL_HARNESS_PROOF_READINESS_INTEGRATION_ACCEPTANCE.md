# Local Harness Proof Readiness Integration Acceptance

## Purpose

This slice makes local task harness proof visible through the existing local
readiness surface:

```bash
agentops local readiness
GET /api/local/readiness
```

It does not replace `agentops operator local-harness-proof`; it summarizes that
read model inside local readiness so operators and demo scripts can see harness
proof posture without discovering a separate command first.

## Added Readiness Fields

`/api/local/readiness` now includes:

- `local_harness_proof_readiness`;
- evidence counters for fresh proof, real-runtime proof, mock fallback,
  latest-failed adapters and missing adapters;
- `local_harness_proof` gate with next action
  `agentops operator local-harness-proof --limit 8`.

## Verification

Run:

```bash
python3 scripts/local_readiness_smoke.py --isolated-fixture
python3 -m py_compile server.py scripts/local_readiness_smoke.py
git diff --check
```

Observed local result:

```text
local_readiness_smoke --isolated-fixture: ok
api_status: attention
cli_status: attention
gate_count: 11
secret_leaked: false
```

## Safety

- Readiness remains read-only.
- The local harness proof read model does not execute live Hermes/OpenClaw.
- No DB, credentials, raw prompts, raw responses, private transcripts,
  `node_modules`, `dist`, cache or generated artifacts are committed.
