# Local Harness Proof Governed Launch Acceptance

## Scope

This slice adds a governed launch packet to the existing local harness proof
readback.

It does not execute Hermes/OpenClaw, mutate the ledger, add a new runtime,
change schema, or make the browser a direct agent executor.

## Behavior

`GET /api/operator/local-harness-proof` and the embedded
`local_harness_proof_readiness` payload now include:

- per-adapter `governed_launch`;
- top-level `governed_launch_packet`;
- `preview_command` through `agentops workflow customer-worker-task`;
- `confirmed_command` with `--confirm-run` for Hermes/OpenClaw only;
- `evidence_readback_command` pointing back to
  `agentops operator local-harness-proof --limit 8`;
- `receipt_preview_command` and `receipt_record_command` using
  `agentops operator record-action-receipt`;
- `receipt_readback_command` pointing to
  `agentops operator action-receipts --limit 20`;
- per-adapter `action_signature` for launch-packet receipt correlation;
- per-adapter `receipt_status` with current/stale/missing match state;
- top-level `receipt_summary` for governed launch packet readback;
- read-only/no-live-execution/raw-prompt-omitted/raw-response-omitted/token
  omission flags.

The direct `scripts/local_task_harness.py` command remains as a developer
fallback in `next_action`; the product-facing launch path is the Agent Gateway
customer-worker workflow.

## Safety Contract

- Mock launch remains CI/offline fallback.
- Hermes/OpenClaw launch requires explicit `--confirm-run`.
- The readback endpoint only returns copyable commands; it does not run shell,
  call live adapters, write the ledger, or store raw prompts/responses.
- `receipt_record_command` records that an operator used or inspected the launch
  packet; it still does not execute the launch command.
- `receipt_status` proves receipt readback only. It must not be presented as
  Hermes/OpenClaw run success.
- A run only counts as proof after the readback sees completed
  run/tool/runtime/evaluation/audit/artifact/verified-plan-evidence rows for the
  returned run id.

## Verification

Commands:

```bash
python3 scripts/local_harness_proof_readback_smoke.py
python3 scripts/local_readiness_smoke.py --isolated-fixture
python3 scripts/worker_console_ui_smoke.py
python3 -m py_compile server.py scripts/local_harness_proof_readback_smoke.py scripts/worker_console_ui_smoke.py
cd ui/start-building-app && npm run build
git diff --check
```

## Next Slice

Expose launch-packet receipt status in the Worker Console as a compact operator
hint while keeping the machine-readable API/CLI packet as the authority.
