# Private Host Background Service Acceptance

## Scope

This slice adds an optional macOS user-level LaunchAgent for the AgentOps MIS
Host control plane. It is deliberately separate from Worker services and from
the graphical `AgentOps MIS.app` launcher.

The service command is fixed to:

```text
agentops host start --foreground --no-workers
```

It keeps the local Host available after login/restart, but never installs or
starts Hermes/OpenClaw and never authorizes live Agent execution.

## Command Contract

```bash
agentops host service-install
agentops host service-install --confirm-install
agentops host service-check
agentops host stop
agentops host service-control --action load|unload|restart
agentops host service-control --action <action> --confirm-control
agentops host service-remove
agentops host service-remove --confirm-remove
```

- Install, launchctl control and removal are preview-only by default.
- Install writes `~/Library/LaunchAgents/dev.agentops.mis.private-host.plist`
  only after `--confirm-install`; writing does not load the service.
- The file is mode `0600` and contains only Host/install paths plus
  `PYTHONPATH`. It contains no machine key, Admin key, setup code, browser
  Session, CSRF value or Runtime credential.
- The service follows the packaged `current` link so a verified update does not
  pin a stale release directory.
- Load is blocked while an independently managed Host process is already
  running. Repeated confirmed load is an idempotent no-op.
- An existing file can be overwritten only when its complete bytes match the
  expected managed definition. An unknown or edited file fails closed.
- Removal is blocked while launchd reports the service loaded.
- The product uninstaller refuses to continue while the default service file is
  present, preventing a leftover restart loop after binary removal.
- Raw plist content and launchctl output are omitted from command responses.

## Verification

```bash
python3 -m py_compile agentops_mis_cli/host.py \
  scripts/private_host_background_service_smoke.py
python3 scripts/private_host_background_service_smoke.py
python3 scripts/private_host_lifecycle_smoke.py
python3 scripts/private_host_bundle_smoke.py
python3 scripts/release_evidence_packet_smoke.py
python3 scripts/secret_scan_smoke.py
git diff --check
```

The isolated smoke uses a temporary Host home, service path and fake launchctl
state. It proves dry-run install, confirmed write, exact host-only arguments,
private mode, credential omission, read-only check, dry-run control, confirmed
load/restart/unload, duplicate-load idempotency, loaded-removal blocking,
confirmed removal and unknown-file overwrite rejection.

## Local Service Staging Receipt

On 2026-07-14, preview.19 first rendered the installation plan in dry-run mode,
then wrote the default managed LaunchAgent only after the explicit
`--confirm-install` gate. Readback proved:

- the file is a safe regular plist with mode `0600`;
- its bytes exactly match the packaged managed definition;
- no credential-like material is present;
- the service command remains Host-only and starts no Worker;
- launchd has not loaded the service.

The existing manually started Host and its one Hermes plus one OpenClaw Worker
were intentionally left running. No service-control action, Runtime task or
ledger mutation was performed. The plist is staged for a later controlled
Host-only persistence exercise; staging alone is not logout/reboot proof.

## Known Limits

- This is an unsigned macOS preview, not a signed/notarized installer service.
- CI validates the launchd contract with an isolated fake launchctl. Physical
  logout/reboot persistence still requires a clean macOS account or VM receipt.
- The service keeps only the MIS Host control plane alive. Hermes/OpenClaw
  Worker services remain independent and require their own explicit live-run
  confirmation. Same-Mac Worker services can use the credential-free
  `local_config` reference described in
  `docs/PRIVATE_HOST_WORKER_SERVICE_ACCEPTANCE.md`; this does not change the
  Host-only service command.
- Browser UI controls for service installation are not included in this slice;
  the existing `.app` remains the normal low-friction way to initialize, start
  safely and open the same React Workspace.

## Next Gate

On a clean macOS account, install the exact prerelease, confirm the service,
load it only after stopping any independently managed Host, log out/reboot, and
record that the same Workspace becomes reachable without any live Worker
starting implicitly.
