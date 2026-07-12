# Local Harness Governed Live Acceptance

## Scope

This slice connects the local-harness-proof governed launch packet to a manual
live dogfood path.

It does not add a new runtime, bypass `--confirm-run`, start Hermes/OpenClaw,
store raw prompts/responses, or make receipt presence equal runtime success.

## Operator Flow

Preview, read-only:

```bash
python3 scripts/local_harness_governed_live_acceptance.py \
  --base-url http://127.0.0.1:8787 \
  --adapter openclaw
```

Confirmed local live run:

```bash
python3 scripts/local_harness_governed_live_acceptance.py \
  --base-url http://127.0.0.1:8787 \
  --adapter openclaw \
  --confirm-live \
  --auto-service-closure
```

For Hermes:

```bash
python3 scripts/local_harness_governed_live_acceptance.py \
  --base-url http://127.0.0.1:8787 \
  --adapter hermes \
  --confirm-live \
  --auto-service-closure \
  --request-timeout 900
```

## Behavior

The script:

1. Reads `GET /api/operator/local-harness-proof`.
2. Extracts the adapter `governed_launch.confirmed_command`.
3. In preview mode, returns the command and exact receipt readback contract only.
4. With `--confirm-live`, executes the governed
   `agentops workflow customer-worker-task ... --confirm-run` command against
   the operator-provided `--base-url`.
5. With `--auto-service-closure`, first records the existing fast
   service-check receipt/readback gate through
   `agentops operator service-closure --fast --run-service-check --confirm-record`.
   This records local service-check evidence only; it does not execute
   service-control and does not call the live runtime.
6. Verifies run/tool/evaluation/runtime/audit/artifact/memory/approval/
   plan-evidence counts from the customer-worker response.
7. Records a scoped `local_harness_proof.governed_launch` action receipt.
8. Reads that receipt back with exact `source`, `action_id`, and
   `action_signature` filters.
9. Reads `local-harness-proof` again and requires the adapter receipt status to
   be `current`.

## Safety Contract

- Preview mode is read-only and must not mutate runs, runtime events or audit
  logs.
- Live mode requires `--confirm-live`; the underlying runtime command still
  includes `--confirm-run`.
- `--auto-service-closure` is explicit and limited to service-check
  receipt/readback recording. It never runs launchd/systemd load/restart and
  never calls Hermes/OpenClaw.
- The script targets an existing `--base-url`; it does not start a temporary
  server for live dogfood because live evidence should enter the operator's
  selected MIS ledger.
- Receipt readback proves RECORD-stage governed launch evidence only. Product
  proof still requires completed run/tool/runtime/evaluation/audit/artifact/
  plan-evidence rows.

## Verification

CI-safe preview smoke:

```bash
python3 scripts/local_harness_governed_live_acceptance_smoke.py
```

Manual live verification, when Hermes/OpenClaw are authorized and available:

```bash
python3 scripts/local_harness_governed_live_acceptance.py \
  --base-url http://127.0.0.1:8787 \
  --adapter openclaw \
  --confirm-live \
  --auto-service-closure
```

## Known Limits

- The smoke intentionally does not call Hermes/OpenClaw.
- Live success is scoped to the returned adapter/run id.
- Opaque runtime internals remain summary-only until the runtime exposes deeper
  tool-event traces.
- A confirmed live request that is blocked by loop supervision is not counted
  as `live_execution_performed`. The script reports the blocking gate and keeps
  the result failed until a completed run id and evidence readbacks exist.

## Current Local Dogfood Note

The current local OpenClaw dogfood pass produced product-grade local ledger
evidence:

- run id: `run_gw_c38283f47a7c`
- task id:
  `tsk_customer_worker_task_openclaw_local_task_harness_proof_openclaw_20260708044857638049`
- artifact id: `art_customer_worker_task_run_gw_c38283f47a7c`
- plan evidence manifest id: `pem_52bcdcbe2d3d9d7e`
- service-check receipt id: `oar_4831f0c6f4ec`
- governed launch receipt id: `oar_f276556b61a2`
- governed launch receipt match: `current`

Readback counts from the confirmed live runner:

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

The pass also fixed a target-binding bug in the first
`--auto-service-closure` implementation: the CLI default agent id was used for
the service-check receipt instead of the adapter worker agent id. The runner
now passes `--service-check-agent-id agt_worker_daemon_<adapter>` so the local
service-check receipt targets the same worker used by the governed launch
packet.

Important boundary: `receipt_status.match=current` proves the governed launch
packet receipt was recorded and read back exactly. It does not by itself prove
runtime success. Runtime proof comes from the completed run id plus run/tool/
runtime/evaluation/audit/artifact/plan-evidence readbacks above.
