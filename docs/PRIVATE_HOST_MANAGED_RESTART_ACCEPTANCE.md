# Private Host Managed Restart Acceptance

Date: 2026-07-18

## Result

The source Private Host now has a locally accepted Owner-to-supervisor managed
Relay restart path:

1. Human Session Owner prepares and explicitly confirms one exact transition.
2. The control core creates a private receipt and transactionally applies the
   active Relay and Host target configs.
3. The ledger audit commits and the server sends `202 Accepted` with
   `Connection: close`.
4. Only after the complete body flushes, the backend submits one action/ref/
   sequence/revision-bound request to the exact current Host parent.
5. The parent stops only its owned stack child, reloads config/secrets, launches
   a replacement and validates stack readiness, loopback health and enabled or
   disabled Relay runtime state.
6. Success finalizes the receipt. Failure stops the failed replacement, restores
   both original configs, relaunches the previous Host and records
   `rolled_back`; failed recovery records `rollback_failed`.

A manual foreground Host returns `manual_restart_required` and receives no
automatic process authority. A second Relay transition is blocked while a
manual, failed or nonterminal receipt is active.

## Verification

The following local checks pass against temporary Host homes and fake process/
service boundaries:

```bash
python3 scripts/private_host_relay_restart_receipt_smoke.py
python3 scripts/private_host_relay_control_core_smoke.py
python3 scripts/private_host_relay_cli_control_smoke.py
python3 scripts/private_host_relay_owner_control_smoke.py
python3 scripts/private_host_post_response_action_smoke.py
python3 scripts/private_host_managed_restart_supervisor_smoke.py
python3 scripts/private_host_relay_managed_restart_rollback_smoke.py
python3 scripts/private_host_background_service_smoke.py
python3 scripts/private_host_lifecycle_smoke.py
python3 scripts/private_host_relay_lifecycle_smoke.py
python3 scripts/human_browser_auth_smoke.py
python3 scripts/private_host_relay_owner_control_ui_smoke.py
python3 scripts/secret_scan_smoke.py
```

The production React build also passes. Existing bundle-size warning remains.

## Safety Evidence

- broken response: no restart request; both configs restored;
- failed rollback: receipt enters terminal `rollback_failed` and control remains
  fail closed instead of reporting an idle or available transition surface;
- failed transition consumption after target apply: both configs restore and
  the receipt records `rolled_back` before returning a bounded failure;
- exact request: current stack child parent, exact service/template and loaded
  label required; the supervisor reads the kernel Unix peer PID and accepts only
  the exact direct `server.py` backend child;
- lifecycle serialization: the parent holds the Host lifecycle file lock from
  receipt acceptance through replacement health or rollback, so concurrent
  start/restart cannot create a second stack;
- post-flush callback failure: while the parent has not accepted ownership, the
  response path restores both configs and records `rolled_back`;
- replay: stale transaction sequence/revision rejected;
- target runtime failure: old Host relaunched after byte-for-byte config restore;
- replacement termination failure: no second stack is launched; the receipt is
  fail closed as `rollback_failed` for later reconciliation;
- isolation: no Tailscale call, Worker command or unrelated PID operation;
- privacy: HTTP/UI/audit omit config bytes, filesystem paths, material digests,
  certificates, credentials and raw runtime content;
- installation: current installed preview, Tailscale and Hermes/OpenClaw service
  processes were not modified by these tests.

## Open Before Release

- prove the bounded post-restart audit projection from the exact installed
  release candidate; deterministic coverage is recorded in
  `PRIVATE_HOST_RESTART_AUDIT_RETENTION_ACCEPTANCE.md`;
- publish and install a versioned release candidate with the new exact
  LaunchAgent template;
- deploy Relay/DNS/certificate infrastructure and bind SNI routes to current
  authenticated Host tunnels;
- complete physical MacBook browser-only pairing, disconnect/reconnect and real
  Hermes/OpenClaw task evidence.

No deployed Relay or `remote_ready` claim is made by this acceptance.
