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
- per-adapter proof status, proof class, latest run id/status and freshness
  window;
- copyable `agentops operator local-harness-proof --limit 8` command;
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
python3 -m py_compile scripts/worker_console_ui_smoke.py
cd ui/start-building-app && npm run build
git diff --check
```

## Next Slice

After this readback is visible, the next product-level slice is to let the
operator launch the local harness proof command through an already governed
worker/task path, not a browser-only shortcut.
