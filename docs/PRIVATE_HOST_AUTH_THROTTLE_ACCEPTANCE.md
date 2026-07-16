# Private Host Authentication Throttle Acceptance

Status: local product slice implemented; internet Relay exposure still blocked by proxy/transport gates

## Contract

Human Login and one-time Pairing now use persistent, source-independent
throttling. The Host intentionally does not collect IP addresses, User-Agent
strings, raw usernames or raw pairing secrets.

- Login has a per-username-hash bucket (8 failures) and endpoint-global bucket
  (100 failures) in a five-minute window.
- Pairing has a per-secret-hash bucket (8 failures) and endpoint-global bucket
  (60 failures), so rotating random invitation strings does not bypass the
  gate.
- A threshold response is bounded `429 too_many_attempts` with numeric
  `retry_after_seconds`, an HTTP `Retry-After` header and omission flags.
- A successful login clears only its subject bucket. It does not erase the
  endpoint-global failure history.
- Active blocks survive Host restarts because only hashed bucket keys, scope,
  counts and bounded timestamps are stored in SQLite.
- Buckets older than one day are pruned during later failures.
- Throttle outcomes write bounded `human_auth.login_throttled` or
  `human_auth.pairing_throttled` audit actions without raw authentication input.

## Verification

```bash
python3 -m py_compile server.py agentops_mis_core/human_auth.py \
  scripts/human_auth_throttle_smoke.py
python3 scripts/human_auth_throttle_smoke.py
python3 scripts/human_browser_auth_smoke.py
python3 scripts/human_console_pairing_smoke.py
python3 scripts/secret_scan_smoke.py
```

The isolated smoke proves subject reset after a successful login, bounded
subject blocking, correct-password rejection during an active block, global
Pairing blocking across 60 rotated unknown strings, `Retry-After`, hashed-only
persistence, bounded audit actions and absence of IP/User-Agent/raw auth input.
It uses a temporary database, fixture-only values and no Runtime.

## Remaining Internet Gates

- fail-closed Host/SNI/Origin and forwarded-header policy;
- deployed outbound Relay with application TLS terminating on the Host;
- physical second-computer task/disconnect/revoke acceptance at one exact
  release.

This receipt does not authorize a non-loopback bind, public quick tunnel,
Tailscale Funnel or production Relay exposure.
