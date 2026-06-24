# Commercial Config Boundary Acceptance

## Scope

This slice extracts a small, mergeable commercial-readiness boundary from the
larger commercial migration branch without taking the Postgres, Next.js,
billing, or hosted-mode implementation.

It adds safe example config:

- `config/entitlements.example.json`
- `config/retention-controls.example.json`

It also adds:

- `scripts/commercial_config_boundary_smoke.py`
- CI and release-evidence wiring for that smoke

## Product Boundary

The examples describe future commercial configuration while keeping the current
product in local-first mode:

- default edition is `free_local`
- billing provider is `none`
- billing calls, checkout and metering export are disabled
- local SQLite/worker/Agent Gateway/Pixel Office remain enabled
- hosted mode, Postgres, SSO, multi-workspace and confirmed external export are
  disabled by default
- retention cleanup is approval-gated, legal-hold gated and non-executable

## Safety Boundary

This slice does not add billing calls, hosted deployment, Postgres storage,
commercial APIs, cleanup endpoints, or destructive retention behavior. It is
an offline config contract plus static validation.

## Verification

Commands:

```bash
python3 scripts/commercial_config_boundary_smoke.py
python3 -m py_compile scripts/commercial_config_boundary_smoke.py scripts/release_evidence_packet_smoke.py
python3 scripts/secret_scan_smoke.py
python3 scripts/release_evidence_packet_smoke.py
git diff --check
```

Expected result:

- `free_local` is the default edition
- no billing provider or billing call is enabled
- no hosted/shared capability is enabled by default
- destructive cleanup/delete support is disabled
- legal-hold registry is represented
- no token-like material appears in config examples

## Next Slice

The next commercial extraction should connect this config boundary to a
read-only status API or CLI preview. It should still avoid billing calls,
Postgres mutation and release-grade claims until exact current-head CI, local
runtime evidence and commercial receipt promotion gates are current.
