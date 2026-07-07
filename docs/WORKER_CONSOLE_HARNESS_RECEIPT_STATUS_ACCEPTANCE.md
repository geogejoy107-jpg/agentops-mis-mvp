# Worker Console Harness Receipt Status Acceptance

## Scope

This slice surfaces the local harness governed-launch receipt readback in the
Worker Console. It does not execute shell commands, call Hermes/OpenClaw, write
the ledger, or change the local harness proof backend.

## Change

- `liveApi.ts` now preserves per-adapter `governed_launch.receipt_status`.
- `liveApi.ts` now preserves top-level
  `governed_launch_packet.receipt_summary`.
- `/workspace/workers` shows:
  - current launch receipt count;
  - missing launch receipt count;
  - stale launch receipt count;
  - a proof that receipt presence is not runtime success;
  - per-adapter receipt match/status.
- `worker_console_ui_smoke.py` guards the type, normalizer and UI markers.

## Safety

- Browser readback remains read-only.
- The UI copies commands only; it does not execute them.
- Receipt state is displayed as operator coordination evidence, not as
  Hermes/OpenClaw runtime success.
- Raw prompts, raw responses and tokens remain omitted.

## Verification

```bash
python3 scripts/worker_console_ui_smoke.py
cd ui/start-building-app && npm run build
git diff --check
python3 scripts/secret_scan_smoke.py
```
