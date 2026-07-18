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

## Real Host Observation

The installed Host is still the public preview.34 package. It is healthy and
serves the existing loopback and Tailscale Console. The preserved preview.33
LaunchAgent is loaded and starts the preview.34 package through the stable
`current` link; independently managed Hermes and OpenClaw Worker services are
also loaded. The corrective source read-only check recognizes that plist as the
exact supported legacy definition when evaluated with the installed Host home
and install root.

No live service mutation is part of this source acceptance. A new immutable
preview must pass exact-head CI and release-consumer checks before the real Host
is unloaded, upgraded, migrated with the new CLI, and loaded again.

## Remaining Release Gate

1. Commit and push the corrective source and exact regression.
2. Require exact-head backend and UI CI success.
3. Build and verify reproducible preview assets from clean tracked source.
4. Publish a new immutable prerelease; do not rewrite preview.34.
5. Back up the real Host ledger, unload Workers and Host, install the new
   prerelease, perform the confirmed legacy migration, then reload Host and
   Workers.
6. Verify exact installed commit, Host/Tailscale readiness, Worker freshness,
   and one new governed Hermes and OpenClaw task closure.
