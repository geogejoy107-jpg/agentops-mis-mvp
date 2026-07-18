# Private Host Managed Restart Supervisor Acceptance

Date: 2026-07-18

## Accepted Slice

The exact managed LaunchAgent foreground Host can now supervise its owned
`run_local_stack.py` child and accept one bounded internal replacement request.
The parent stops only that child, reloads the current private Host config and
secrets from disk, waits for the inherited readiness signal plus loopback health,
and writes a new private service-instance record.

This is an internal lifecycle primitive. The Owner Relay confirmation route does
not invoke it yet, the restart receipt is not yet bound to the request, and
automatic rollback is not yet integrated.

## Authority And Isolation

- The LaunchAgent file must match the exact generated Host-only template.
- The exact service label must be loaded and the supervisor parent must be
  launchd.
- The hidden managed flag is accepted only with `--foreground --no-workers`.
- The backend requester must be a direct child of the exact current stack child.
- The private service-instance record binds supervisor PID, stack child PID,
  exact label and exact template hash.
- The Unix socket and instance record are mode `0600`; their directory is a
  same-owner, non-symlink directory in exact mode `0700`.
- A manual foreground Host has no automatic restart authority.
- No shell, Tailscale command, Worker command or unrelated PID operation is
  used.

## Verification

```bash
python3 -m py_compile \
  agentops_mis_cli/host.py \
  scripts/private_host_managed_restart_supervisor_smoke.py
python3 scripts/private_host_managed_restart_supervisor_smoke.py
python3 scripts/private_host_background_service_smoke.py
python3 scripts/private_host_lifecycle_smoke.py
python3 scripts/private_host_relay_lifecycle_smoke.py
git diff --check
```

Results:

- exact service gate: pass;
- manual foreground rejection: pass;
- unrelated same-user requester rejection: pass;
- unsafe/symlink/wrong-mode run directory rejection: pass;
- one request creates one replacement child: pass;
- stubborn owned child receives bounded terminate then kill: pass;
- replacement reloads changed allowed-origin/cookie configuration: pass;
- service-instance and public result redaction: pass;
- existing LaunchAgent, Host and Relay lifecycle regressions: pass.

All tests use a temporary Host home and fake child/service boundaries. The
installed Host, Tailscale profile, Hermes/OpenClaw services and local database
were not changed.

## Remaining Integration

- bind each internal request to one private restart transaction sequence and
  transition ref;
- mark response-flushed/restart-requested/validating/healthy states durably;
- validate enabled or disabled Relay runtime after replacement;
- restore both Relay and Host config byte-for-byte and relaunch the old stack on
  failure;
- reconcile crash-interrupted receipts before normal managed startup;
- wire the Owner confirmation response through the existing post-response hook.
