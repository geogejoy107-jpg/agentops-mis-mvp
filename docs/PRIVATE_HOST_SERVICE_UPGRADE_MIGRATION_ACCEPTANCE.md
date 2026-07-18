# Private Host Service Upgrade Migration Acceptance

## Problem

The preview.34 package installed successfully and the Host data remained
healthy, but its CLI could not replace the preview.33 LaunchAgent definition.
preview.34 introduced the private `--managed-launch-agent` process-identity
gate, so the preserved preview.33 plist was no longer byte-equal to the current
template. Falling back to the previous CLI restored service availability, but
that is a recovery procedure rather than a product-grade upgrade path.

## Corrective Contract

The current source supports one bounded legacy migration:

- current exact managed definitions retain their existing behavior;
- the only accepted legacy bytes are the immediately previous Host-only
  definition without `--managed-launch-agent`;
- the legacy file must be owned by the current user with exact mode `0600`, be
  a regular file rather than a symlink, live in a current-user-owned directory
  that is not group/other writable, contain no credential-like material and use
  the exact managed paths;
- launchd must report the legacy service unloaded;
- when the exact legacy service is loaded, the current CLI permits only an
  explicitly confirmed unload; load and restart remain blocked;
- mutation still requires both `--overwrite` and `--confirm-install`;
- replacement uses the existing atomic writer and must pass the current exact
  post-write service check.

The source continues to reject arbitrary same-label definitions, changed
commands, added environment values, credential-bearing files, path edits,
unsafe file modes/directories, symlinks, unverified launchctl state and loaded
legacy services.

## Verification

```bash
python3 -m py_compile agentops_mis_cli/host.py \
  scripts/private_host_background_service_smoke.py
python3 scripts/private_host_background_service_smoke.py
python3 scripts/private_host_lifecycle_smoke.py
python3 scripts/private_host_managed_restart_supervisor_smoke.py
python3 scripts/private_host_relay_managed_restart_rollback_smoke.py
git diff --check
```

The background-service smoke uses a temporary Host home, service path and fake
launchctl. It proves an unloaded exact legacy definition migrates to the
current template, while a loaded exact legacy definition and every edited
variant remain unchanged and fail closed.

## Preview 35 Release And Real Upgrade

`v1.6.0-private-host-preview.35` was published from exact commit
`6424ec144013517b21438cd7e528c6db106a0a5e`. Both exact-head backend jobs and
both production UI jobs passed. The five candidate assets were reproducible,
matched their Draft downloads byte-for-byte, and passed an isolated
no-repository install/start/status/stop receipt before publication.

The real preview.34 Host ledger was backed up and verified before maintenance.
The independent Hermes and OpenClaw services were explicitly unloaded first.
The preview.35 release payload then exercised the new unload-only path against
the loaded exact previous service definition. launchd reported the service
unloaded and the Host stopped; no plist or Tailscale mutation occurred during
that action.

The public bootstrap downloaded and verified preview.35, preserved user data,
created another pre-update backup and reported preview.34 as the previous
version. The installed preview.35 CLI first returned a successful dry-run
legacy migration plan. The separate confirmed overwrite atomically replaced
the previous plist, and readback proved the current exact definition, unloaded
state and no credential material. A confirmed load returned the Host to ready,
the private Tailscale route remained ready with Funnel disabled, and both
independent Worker services were reloaded with fresh idle heartbeats.

This closes the specific service-upgrade migration defect without modifying
the immutable preview.34 release. It does not claim signed/notarized packaging,
physical logout/reboot persistence or unattended automatic upgrades.
