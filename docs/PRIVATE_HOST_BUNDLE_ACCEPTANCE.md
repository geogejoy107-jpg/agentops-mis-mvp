# Private Host Bundle Acceptance

## Scope

This Phase 4 slice builds an unsigned macOS developer-preview bundle containing
the production UI and private Host runtime. It replaces “download the source
archive and configure a repository” with an integrity-checked installable
archive, but it is not yet a signed/notarized `.pkg` or `.dmg`.

## Build

```bash
cd ui/start-building-app
npm ci
npm run build
cd ../..
python3 scripts/build_private_host_bundle.py \
  --version 1.0.0-preview \
  --output-dir build/private-host
```

Outputs:

- `agentops-mis-private-host-<version>.tar.gz`;
- `agentops-mis-private-host-<version>.zip`;
- `agentops-mis-private-host-<version>.sha256.json`.
- `install-agentops-mis-private-host.sh` release-consumer bootstrap.

Generated archives and UI `dist` remain untracked.

## Bundle Contract

- Source selection starts from Git-tracked runtime files, not the dirty working
  directory.
- The production UI is copied from the explicit built `dist` directory.
- Runtime packages include CLI, core and runtime adapters plus the Python
  server, knowledge/static/config data and bounded scripts needed by Host mode.
- Each installed version includes the minimal SBOM, third-party notices,
  release provenance and Private Host operator runbook.
- `manifest.json` records product version, exact Git commit, build timestamp,
  platform, Python requirement, file sizes and SHA-256 for every payload and
  installer file.
- Archive-level SHA-256 values are emitted separately.
- The checksum manifest also covers the published release-consumer bootstrap.
- The release-consumer bootstrap pins one explicit GitHub tag, verifies the
  downloaded tar archive programmatically, rejects unsafe archive members,
  installs the bundle, and verifies installed version provenance. Optional
  `--init --start` remains loopback-only and does not create an Owner or enable
  live Runtimes/Tailscale.
- `.git`, `.env*`, DB/SQLite, token-named files, logs, caches, `node_modules`,
  `__pycache__`, `.agentops_runtime`, sample exports and local artifacts are
  excluded.
- Installer rejects missing, modified, undeclared or traversal paths before
  copying payload files.
- Default install path is `~/.local/share/agentops-mis`; the operator CLI shim
  is `~/.local/bin/agentops` and the service/daemon CLI shim is
  `~/.local/bin/agentops-worker`.
- Versioned payloads live below `versions/<version>` and `current` points to the
  active version.
- A verified update stages the new version, preserves the prior version through
  `previous`, and refuses to run while the managed Host PID is alive.
- Install/update and uninstall share the Host lifecycle lock with start/stop;
  lock contention fails closed before backup, version staging, or removal.
  The lock file is opened without following a final symlink and must be a
  regular file.
- Uninstall removes product files and shim but preserves `~/.agentops/host`
  user data unless `AGENTOPS_PURGE_DATA=true` is explicitly set.
- Install and Host initialization create bounded, non-secret ownership markers.
  A non-empty install root without a valid marker is accepted only through the
  legacy migration shape (`current` inside `versions` plus an exact product
  release manifest); arbitrary existing directories are never claimed.
  Uninstall refuses while the managed Host PID is alive, its PID record is
  invalid/unverifiable, or the shared lifecycle lock is held. It requires valid
  product/data ownership markers and rejects dangerous, overlapping, external,
  or symlinked removal roots.
- Both existing CLI shims must match the installer-generated content exactly
  before update or uninstall; modified and symlinked shims fail closed.
- Installer does not use the network or install Hermes, OpenClaw, Tailscale,
  Python or Node.

## Verification

```bash
python3 -m py_compile \
  scripts/build_private_host_bundle.py \
  scripts/private_host_bundle_smoke.py
bash -n packaging/macos/install.sh packaging/macos/uninstall.sh
python3 scripts/private_host_bundle_smoke.py
python3 scripts/private_host_release_consumer_smoke.py
git diff --check
```

The smoke uses temporary build/output/HOME/install/data directories and proves:

- tar.gz and zip forbidden-member/path-traversal scan;
- archive and per-file manifest checksums;
- modified payload rejection before installation;
- offline install and both CLI shim creations;
- direct execution of the installed `agentops-worker` command and Worker
  service-template generation without a repository or module fallback;
- installed `agentops host --help`;
- installed `agentops host init` and `agentops host doctor`;
- installed human-auth capable live Runtime ledger readback client;
- two versioned bundles upgrade and roll back through `current`/`previous`;
- rollback requires confirmation and creates a verified ledger backup;
- upgrade creates a verified ledger backup before switching binaries;
- Host ledger and user data survive the binary switch;
- production UI presence in the installed current version;
- installed SBOM, third-party notices, provenance and operator runbook;
- uninstall removes product files;
- uninstall preserves a pre-existing user-data sentinel.
- running-Host and invalid-PID uninstall attempts fail closed without removing
  the installed version or CLI shim;
- invalid-PID update, unrelated-root install, and modified operator/Worker shim uninstall
  attempts fail closed while preserving their sentinels;
- lifecycle-lock contention, missing ownership marker, and HOME-root purge
  attempts fail closed without removing product or user data;
- symlinked lifecycle-lock substitution is rejected by both installer and
  uninstaller without modifying the symlink target;
- a clean isolated HOME consumes release-shaped assets without a repository,
  verifies checksum/provenance, initializes and starts the Host, exposes the
  Owner bootstrap action, and stops cleanly.
- bundle-smoke Host instances register before each start and are stopped on
  normal exit, assertion failure, `SIGTERM`, or `SIGINT`; an intentional
  `SIGTERM` acceptance confirmed the new fixture Host exited while unrelated
  processes remained untouched.

No generated archive, DB, credential, log, cache, dependency directory, real
Runtime call or network publication is committed or retained by the smoke.

## Known Limitations

- Apple Developer ID signing, notarization, Gatekeeper validation and `.pkg` or
  `.dmg` UX are not complete.
- Target Mac must already provide Python 3.10 or newer.
- Tailscale and Hermes/OpenClaw remain explicit Host-side prerequisites.
- `.github/workflows/private-host-release.yml` manually publishes an existing
  exact-commit tag as a prerelease after rebuilding and re-running bundle and
  consumer smokes. It then downloads the published bootstrap and performs a
  clean-HOME install/init/start/status/stop gate against the real Release.
- Binary upgrade/rollback is covered for two bundles using the same schema;
  incompatible future schema changes still require a dedicated downgrade path.
- A real second Mac download/install/private-console acceptance remains pending.

## Next Slice

Complete the same download/install receipt on another physical Mac, then add
Apple signing/notarization only after the unsigned preview workflow is stable.
