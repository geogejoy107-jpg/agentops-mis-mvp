# Harness Governed Live Proof Acceptance

## Scope

This acceptance note covers the local Harness engineering slice that adds:

- Harness engineering product constraints spec.
- CI-safe governed live preview smoke.
- Manual governed local harness live runner.
- Release-evidence packet entries.
- OpenClaw local live dogfood evidence.

## Verification Commands

Run locally:

```bash
python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py && git diff --check
python3 scripts/harness_engineering_product_constraints_smoke.py
python3 scripts/local_harness_governed_live_acceptance_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/secret_scan_smoke.py
```

Manual live command used:

```bash
python3 scripts/local_harness_governed_live_acceptance.py \
  --base-url http://127.0.0.1:8787 \
  --adapter openclaw \
  --confirm-live \
  --auto-service-closure \
  --request-timeout 900
```

## Local Live Result

The confirmed OpenClaw path completed on the local MIS ledger:

- run id: `run_gw_c38283f47a7c`
- artifact id: `art_customer_worker_task_run_gw_c38283f47a7c`
- service-check receipt id: `oar_4831f0c6f4ec`
- governed launch receipt id: `oar_f276556b61a2`
- governed launch receipt status: `verified`
- governed launch receipt match: `current`

Evidence counts:

| Evidence | Count |
| --- | ---: |
| tool calls | 1 |
| runtime events | 15 |
| evaluations | 1 |
| audit logs | 12 |
| artifacts | 2 |
| memory candidates | 2 |
| approvals | 1 |
| plan evidence manifests | 1 |

## Fixed During Acceptance

The first live attempt exposed a target-binding issue in
`--auto-service-closure`: the closure command inherited the CLI client default
agent id instead of the adapter worker id. The runner now passes
`--service-check-agent-id agt_worker_daemon_<adapter>` so service-check receipt
readback is bound to the same worker used by the governed launch packet.

## Claim Limits

- This proves local OpenClaw governed live execution for the recorded run id.
- It does not prove Hermes governed live execution.
- It does not make receipt presence equal runtime success.
- It does not commit raw prompts, raw responses, credentials, DB files,
  generated exports, node modules, dist, or caches.

