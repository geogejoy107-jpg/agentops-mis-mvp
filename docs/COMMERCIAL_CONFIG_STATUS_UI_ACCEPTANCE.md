# Commercial Config Status UI Acceptance

## Scope

This slice surfaces the read-only commercial config status in the Admin
Console, inside `/admin/connectors`.

It adds:

- `loadCommercialConfigStatus()` in `ui/start-building-app/src/app/data/liveApi.ts`
- `commercial-config-status-panel` in `RuntimeConnectors.tsx`
- `scripts/commercial_config_status_ui_smoke.py`
- CI and release-evidence wiring for that UI contract

## Product Behavior

The panel shows:

- current commercial config status
- edition and billing provider
- billing-call, cleanup-execution, raw-config-omission and token-omission gates
- cleanup approval and legal-hold gates
- enabled and disabled capabilities
- default/env source metadata without exposing raw config payloads

The loader uses an optional API fallback so the Connectors page stays usable
when an older local server does not yet expose `/api/commercial/config-status`.

## Safety Boundary

The UI is read-only. It does not mutate SQLite, call billing providers, expose
checkout/metering, execute cleanup, run live runtimes, display raw config files,
or show token material.

## Verification

Commands:

```bash
python3 scripts/commercial_config_status_ui_smoke.py
python3 scripts/commercial_config_status_smoke.py
python3 -m py_compile scripts/commercial_config_status_ui_smoke.py scripts/release_evidence_packet_smoke.py
cd ui/start-building-app && npm run build
python3 scripts/secret_scan_smoke.py
python3 scripts/release_evidence_packet_smoke.py
git diff --check
```

Expected result:

- `/admin/connectors` source contains `data-testid="commercial-config-status-panel"`
- panel renders edition, billing provider, approval/legal-hold gates and capability lists
- panel renders safety gates for read-only, no billing call, no cleanup execution, raw config omitted and token omitted
- live API loader normalizes omission/safety fields and uses optional fallback
- no token-like material is introduced

## Follow-up Slice

The narrow operator action follow-up is tracked in
`docs/COMMERCIAL_CONFIG_OPERATOR_ACTION_UI_ACCEPTANCE.md`. It points operators
from this panel to the exact CLI command (`agentops commercial config-status`)
and evidence docs while keeping billing, hosted mode, Postgres and cleanup
execution out of scope until production gates are current.
