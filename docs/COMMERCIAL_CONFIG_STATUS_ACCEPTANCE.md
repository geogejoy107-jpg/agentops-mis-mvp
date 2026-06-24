# Commercial Config Status Acceptance

## Scope

This slice adds a read-only status projection for the commercial config boundary:

- `GET /api/commercial/config-status`
- `agentops commercial config-status`
- `scripts/commercial_config_status_smoke.py`

It builds on the safe example configs and does not add billing, hosted mode,
Postgres, retention cleanup execution, or commercial write APIs.

## Product Behavior

The status projection summarizes:

- entitlement schema and edition
- billing provider and whether billing calls are enabled
- enabled and disabled capabilities
- retention windows
- cleanup approval and legal-hold gates
- legal-hold registry configuration
- source metadata for default example versus explicit env path

Raw config payloads are omitted from the response. External override paths are
not expanded into full local paths in the API response.

## Safety Boundary

The endpoint and CLI are read-only. They do not mutate SQLite, call billing
providers, expose checkout/metering, execute cleanup, delete data, run live
runtimes, or print tokens.

## Verification

Commands:

```bash
python3 scripts/commercial_config_status_smoke.py
python3 -m py_compile server.py agentops_mis_cli/agentops.py scripts/commercial_config_status_smoke.py scripts/release_evidence_packet_smoke.py
python3 scripts/commercial_config_boundary_smoke.py
python3 scripts/secret_scan_smoke.py
python3 scripts/release_evidence_packet_smoke.py
git diff --check
```

Expected result:

- API and CLI both return `operation: commercial_config_status`
- default edition is `free_local`
- billing provider is `none`
- hosted mode is disabled by default
- cleanup execution is disabled and approval/legal-hold gates are visible
- safety fields show read-only, no billing call, no cleanup execution, no live execution, raw config omitted, token omitted

## Next Slice

After this lands, the next commercial slice can expose the same read-only status
in the Admin Console. It should still avoid billing calls, Postgres mutation and
hosted-readiness claims until production gates and exact current-head CI are
current.
