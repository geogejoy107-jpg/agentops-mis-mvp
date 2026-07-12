# Private Host Lifecycle Acceptance

## Scope

This slice turns the production UI and human-auth foundations into a managed
repo-local product command:

```text
agentops host init
agentops host start
agentops host status
agentops host doctor
agentops host logs
agentops host restart
agentops host stop
agentops host console-url
agentops host tailscale-preview
```

It does not publish the Host, install Hermes/OpenClaw, or claim a packaged
customer release.

## Implemented Contract

- Host state lives outside the repository under `~/.agentops/host` by default.
- `AGENTOPS_HOST_HOME` supports isolated tests and controlled installations.
- Config, secret, log and PID files are created with private permissions.
- Initial API/Admin keys and Owner setup code use cryptographic randomness.
- The Owner setup code is displayed by first init and never reprinted by a
  repeated init.
- Host startup uses the production same-origin UI and does not run Vite.
- A prepackaged `--ui-dist` can run without `node_modules`.
- Background start owns one process group; stop targets only that group.
- Default Worker is mock; Hermes/OpenClaw still require
  `--confirm-live-workers`.
- Network publication remains `disabled` after init/start.
- Tailscale inspection is read-only and `tailscale-preview` only prints a Serve
  command plus `tailscale serve reset`; it never executes either command and
  never enables Funnel.
- `tailscale-apply` and `tailscale-revoke` remain side-effect free without
  `--confirm`; confirmed apply/reset update the private trusted-Origin config
  and require a Host restart.
- Host status, doctor, logs and console URL responses omit credential values.

## Verification

```bash
python3 -m py_compile agentops_mis_cli/host.py agentops_mis_cli/cli.py \
  scripts/run_local_stack.py scripts/private_host_lifecycle_smoke.py
python3 scripts/private_host_lifecycle_smoke.py
python3 scripts/run_local_stack_smoke.py
python3 scripts/human_browser_auth_smoke.py
python3 scripts/production_ui_host_smoke.py
python3 scripts/secret_scan_smoke.py
git diff --check
```

The lifecycle smoke used a temporary Host Home, temporary production UI,
temporary SQLite database and a free loopback port. It verified:

- private config and secret permissions;
- one-time setup-code output;
- repeat-init fail-closed behavior without secret output;
- background start and ready health;
- zero Worker mode for deterministic CI;
- publication disabled by default;
- running status readback;
- Tailscale preview-only/Funnel-disabled behavior;
- process-group stop and temporary-state cleanup.

No real Runtime, external connector, Tailscale configuration, user database,
prompt, response, private message or transcript was used.

## Known Limitations

- The command currently runs from the installed repository/Python package; a
  signed, versioned macOS Host bundle has not yet been produced.
- Tailscale Serve remains explicit and operator-confirmed; it is never enabled
  by init/start.
- Trusted Origin validation is implemented; richer trusted-proxy identity and
  forwarded-header handling remain pending.
- Account invitation, role management, password recovery and session/device
  revocation UI remain pending.
- `host logs` returns safe metadata and the local path, not live redacted tail.
- Host backup/update/uninstall commands remain Phase 4 work.
- Second-computer acceptance and real Hermes/OpenClaw remote-control evidence
  remain mandatory before product completion.

## Next Slice

Add trusted Origin/forwarded-proto handling, a confirmation-gated Tailscale
Serve apply/revoke command, then run the browser console from a second tailnet
device with no repository dependencies.
