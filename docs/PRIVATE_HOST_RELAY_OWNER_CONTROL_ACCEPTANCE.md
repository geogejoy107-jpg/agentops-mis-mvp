# Private Host Relay Owner Control Acceptance

Date: 2026-07-18

## Product Slice

The existing Account and access Workspace page now exposes a bounded Remote
Console control for an authenticated Owner. The Owner first prepares an exact
`enable` or `disable` transition, then confirms the short-lived in-memory
transition reference. Confirmation executes the exact prepared config change
once and reports that a Host service restart is required.

This is a local configuration-control slice. It does not provision or deploy a
Relay, generate certificates, restart the installed Host, publish a remote URL,
or claim browser-only remote readiness.

## HTTP Contract

```http
GET  /api/host/relay
POST /api/host/relay/transitions
POST /api/host/relay/transitions/{transition_ref}/confirm
```

- All routes require a Human Session with the `owner` role in `private_host`
  mode.
- Both POST routes require exact Origin validation and the Human Session CSRF
  token.
- Agent Gateway API keys, Host machine credentials and anonymous callers do not
  authorize these routes.
- Request bodies accept only `{"action":"enable"}` or
  `{"action":"disable"}`.
- Responses and audit metadata omit config paths, hostnames, ports, routes,
  certificate material, private digests and machine credentials.

## Verification

```bash
python3 -m py_compile \
  server.py \
  agentops_mis_cli/host.py \
  agentops_mis_cli/relay_control.py \
  scripts/private_host_relay_control_core_smoke.py \
  scripts/private_host_relay_cli_control_smoke.py \
  scripts/private_host_relay_owner_control_smoke.py
python3 scripts/private_host_relay_control_core_smoke.py
python3 scripts/private_host_relay_cli_control_smoke.py
python3 scripts/private_host_relay_owner_control_smoke.py
cd ui/start-building-app && npm run build
```

The deterministic core smoke proves private `0700`/`0600` material, prepare
without mutation, non-executing confirmation, single-use execution, bounded
TTL, action/ref/material mismatch rejection, replay rejection, exact
enable/disable config projection, Tailscale field preservation, transactional
rollback after an injected second-write failure, bounded public errors and zero
runtime network/subprocess use.

The server-backed smoke uses an isolated Host home and temporary SQLite ledger.
It proves anonymous, non-Owner, machine-bearer, missing-CSRF and wrong-Origin
denial; Owner prepare and confirm; replay rejection; config preservation; and
bounded prepare/execute/failure audit events. It does not contact Tailscale or a
Relay.

## Known Limitations

- The confirmed transition returns `restart_required:true`; this slice does not
  restart the installed or current Host process.
- No deployed Relay, DNS, certificate lifecycle, credential provisioning or
  Relay-side SNI routing exists yet.
- `remote_ready` must remain false until deployed-Relay and physical
  browser-only acceptance are both complete.
- The current installed preview remains on its earlier source package and is
  intentionally not upgraded by this acceptance.

## Next Slice

Add an exact-definition, rollback-aware managed Host restart worker for a
confirmed Relay transition. Then implement Relay-side SNI routing and deploy a
non-authority Relay before running physical second-computer browser acceptance.
