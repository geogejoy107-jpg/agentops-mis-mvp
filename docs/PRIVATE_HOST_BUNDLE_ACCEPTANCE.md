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

Generated archives and UI `dist` remain untracked.

## Bundle Contract

- Source selection starts from Git-tracked runtime files, not the dirty working
  directory.
- The production UI is copied from the explicit built `dist` directory.
- Runtime packages include CLI, core and runtime adapters plus the Python
  server, knowledge/static/config data and bounded scripts needed by Host mode.
- `manifest.json` records product version, exact Git commit, build timestamp,
  platform, Python requirement, file sizes and SHA-256 for every payload and
  installer file.
- Archive-level SHA-256 values are emitted separately.
- `.git`, `.env*`, DB/SQLite, token-named files, logs, caches, `node_modules`,
  `__pycache__`, `.agentops_runtime`, sample exports and local artifacts are
  excluded.
- Installer rejects missing, modified, undeclared or traversal paths before
  copying payload files.
- Default install path is `~/.local/share/agentops-mis`; the CLI shim is
  `~/.local/bin/agentops`.
- Versioned payloads live below `versions/<version>` and `current` points to the
  active version.
- A verified update stages the new version, preserves the prior version through
  `previous`, and refuses to run while the managed Host PID is alive.
- Uninstall removes product files and shim but preserves `~/.agentops/host`
  user data unless `AGENTOPS_PURGE_DATA=true` is explicitly set.
- Installer does not use the network or install Hermes, OpenClaw, Tailscale,
  Python or Node.

## Verification

```bash
python3 -m py_compile \
  scripts/build_private_host_bundle.py \
  scripts/private_host_bundle_smoke.py
bash -n packaging/macos/install.sh packaging/macos/uninstall.sh
python3 scripts/private_host_bundle_smoke.py
git diff --check
```

The smoke uses temporary build/output/HOME/install/data directories and proves:

- tar.gz and zip forbidden-member/path-traversal scan;
- archive and per-file manifest checksums;
- modified payload rejection before installation;
- offline install and CLI shim creation;
- installed `agentops host --help`;
- installed `agentops host init` and `agentops host doctor`;
- two versioned bundles upgrade and roll back through `current`/`previous`;
- rollback requires confirmation and creates a verified ledger backup;
- upgrade creates a verified ledger backup before switching binaries;
- Host ledger and user data survive the binary switch;
- production UI presence in the installed current version;
- uninstall removes product files;
- uninstall preserves a pre-existing user-data sentinel.

No generated archive, DB, credential, log, cache, dependency directory, real
Runtime call or network publication is committed or retained by the smoke.

## Known Limitations

- Apple Developer ID signing, notarization, Gatekeeper validation and `.pkg` or
  `.dmg` UX are not complete.
- Target Mac must already provide Python 3.10 or newer.
- Tailscale and Hermes/OpenClaw remain explicit Host-side prerequisites.
- `.github/workflows/private-host-release.yml` can manually publish an existing
  exact-commit tag as a prerelease after rebuilding and re-running bundle smoke;
  no private Host preview release has yet been published from this branch.
- Binary upgrade/rollback is covered for two bundles using the same schema;
  incompatible future schema changes still require a dedicated downgrade path.
- A real second Mac download/install/private-console acceptance remains pending.

## Next Slice

Add a tag/manual GitHub Release workflow that builds the UI and bundle, reruns
the bundle smoke, uploads archives/checksums with exact-commit provenance, and
keeps publication manual until signing/notarization policy is decided.
