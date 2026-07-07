# Local Harness Proof Worker Console Acceptance

## Scope

This slice surfaces existing local harness proof readback in the Worker Console
at `/workspace/workers`.

It does not add a new runtime action, execute Hermes/OpenClaw, mutate the
ledger, change schema, or treat mock evidence as real AI proof.

## Product Behavior

The Worker Console now reads `local_harness_proof_readiness` from
`GET /api/local/readiness` through the existing `loadLocalReadiness()` loader and
shows:

- overall local harness proof status;
- fresh real-runtime adapter count for Hermes/OpenClaw;
- fresh mock fallback count;
- governed launch receipt summary counts for current/missing/stale receipts;
- per-adapter proof status, proof class, latest run id/status and freshness
  window;
- per-adapter governed launch receipt status with current/stale/missing
  readback and receipt id when available;
- copyable `agentops operator local-harness-proof --limit 8` command;
- copyable per-adapter `agentops operator action-receipts --limit 20` receipt
  readback command;
- read-only/no-live-execution/raw-prompt-omitted/token-omitted safety flags.

## Safety Boundary

The panel is a read-only operator surface:

- mock remains `mock_ci_fallback`;
- Hermes/OpenClaw rows are `real_runtime_ledger_readback` only for returned run
  ids with ledger evidence;
- the browser never calls live runtime probes from this panel;
- raw prompts, raw responses, credentials, private messages and full transcripts
  are not displayed or stored.

## Verification

Commands:

```bash
python3 scripts/worker_console_ui_smoke.py
python3 scripts/local_harness_proof_readback_smoke.py
python3 -m py_compile scripts/worker_console_ui_smoke.py
cd ui/start-building-app && npm run build
git diff --check
```

## Follow-On Slice

The next useful slice is a one-command operator packet that sequences governed
launch, receipt recording/readback, and local harness proof readback for a
selected adapter while keeping Hermes/OpenClaw live execution behind explicit
confirmation.
