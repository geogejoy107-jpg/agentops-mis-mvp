#!/bin/sh
set -eu

BUNDLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_ROOT=${AGENTOPS_INSTALL_ROOT:-"$HOME/.local/share/agentops-mis"}
BIN_DIR=${AGENTOPS_BIN_DIR:-"$HOME/.local/bin"}
DATA_ROOT=${AGENTOPS_HOST_HOME:-"$HOME/.agentops/host"}
APP_DIR=${AGENTOPS_APP_DIR:-"$HOME/Applications"}
INSTALL_APP=true
if [ "${AGENTOPS_NO_APP_INSTALL:-}" = "1" ]; then
  INSTALL_APP=false
fi

if [ "$(uname -s)" != "Darwin" ] && [ "${AGENTOPS_BUNDLE_INSTALLER_TEST_MODE:-}" != "1" ]; then
  echo "this unsigned Private Host bundle supports macOS only" >&2
  exit 2
fi
python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required")
PY

python3 - "$BUNDLE_DIR" "$INSTALL_ROOT" "$BIN_DIR" "$DATA_ROOT" "$APP_DIR" "$INSTALL_APP" <<'PY'
import json
import fcntl
import hashlib
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

bundle = Path(sys.argv[1]).resolve()
install_root = Path(sys.argv[2]).expanduser().resolve()
bin_dir = Path(sys.argv[3]).expanduser().resolve()
data_root = Path(sys.argv[4]).expanduser().resolve()
raw_app_dir = Path(sys.argv[5]).expanduser()
install_app = sys.argv[6].lower() == "true"
if raw_app_dir.is_symlink():
    raise SystemExit("unsafe symlinked application directory")
app_dir = raw_app_dir.resolve()
manifest_path = bundle / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
version = str(manifest["version"])
if not version or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in version):
    raise SystemExit("invalid bundle version")
target = install_root / "versions" / version
app_bundle = app_dir / "AgentOps MIS.app"
launcher_marker_payload = {
    "schema_version": 1,
    "product": "AgentOps MIS Private Host Launcher",
    "managed": True,
}

if install_app:
    home = Path.home().resolve()
    try:
        app_relative = app_dir.relative_to(home)
    except ValueError:
        raise SystemExit("application directory is outside HOME; install refused")
    if not app_relative.parts:
        raise SystemExit("unsafe application directory")
    managed_roots = (install_root, bin_dir, data_root)
    if any(
        app_dir == root
        or app_dir in root.parents
        or root in app_dir.parents
        for root in managed_roots
    ):
        raise SystemExit("application directory overlaps another managed root")
    if app_bundle.exists() or app_bundle.is_symlink():
        launcher_marker = app_bundle / "Contents" / "Resources" / "agentops-mis-launcher.json"
        try:
            existing_launcher_marker = json.loads(launcher_marker.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raise SystemExit("existing AgentOps MIS application ownership cannot be verified")
        if app_bundle.is_symlink() or not app_bundle.is_dir() or launcher_marker.is_symlink() or existing_launcher_marker != launcher_marker_payload:
            raise SystemExit("existing AgentOps MIS application ownership cannot be verified")

lock_path = data_root.parent / ".agentops-mis-host-lifecycle.lock"
lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
lock_descriptor = os.open(
    lock_path,
    os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
    0o600,
)
lock_metadata = os.fstat(lock_descriptor)
if not stat.S_ISREG(lock_metadata.st_mode):
    os.close(lock_descriptor)
    raise SystemExit("Host lifecycle lock is not a regular file; install refused")
os.fchmod(lock_descriptor, 0o600)
try:
    fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    os.close(lock_descriptor)
    raise SystemExit("Host lifecycle operation is active; install refused")

pid_path = data_root / "run" / "host.pid.json"
if pid_path.is_file():
    try:
        pid_payload = json.loads(pid_path.read_text(encoding="utf-8"))
        pid = int(pid_payload.get("pid") or 0) if isinstance(pid_payload, dict) else 0
    except (OSError, ValueError, json.JSONDecodeError):
        raise SystemExit("cannot verify Host process state; update refused")
    if pid <= 0:
        raise SystemExit("invalid managed Host PID record; update refused")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    except PermissionError:
        raise SystemExit("cannot verify Host process state; update refused")
    else:
        raise SystemExit("AgentOps MIS Host is running; stop it before installing an update")

def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()

declared = set()
for record in manifest.get("files", []):
    relative = Path(str(record["path"]))
    if relative.is_absolute() or ".." in relative.parts:
        raise SystemExit("unsafe path in bundle manifest")
    source = bundle / relative
    if not source.is_file():
        raise SystemExit(f"missing bundle file: {relative}")
    if source.stat().st_size != int(record["size"]) or digest(source) != record["sha256"]:
        raise SystemExit(f"bundle integrity check failed: {relative}")
    declared.add(relative.as_posix())

actual = {
    path.relative_to(bundle).as_posix()
    for path in bundle.rglob("*")
    if path.is_file() and path.name != "manifest.json"
}
if actual != declared:
    raise SystemExit("bundle contains undeclared or unverified files")

current = install_root / "current"
previous = install_root / "previous"
old_current = current.resolve() if current.is_symlink() else None
if current.exists() and not current.is_symlink():
    raise SystemExit("unsafe non-symlink current install path")

install_marker = install_root / ".agentops-mis-install.json"
expected_install_marker = {
    "schema_version": 1,
    "product": "AgentOps MIS Private Host",
    "managed": True,
}
if install_marker.exists():
    try:
        existing_marker = json.loads(install_marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SystemExit("installed product ownership marker is invalid")
    if install_marker.is_symlink() or existing_marker != expected_install_marker:
        raise SystemExit("installed product ownership marker is invalid")
elif install_root.is_dir() and any(install_root.iterdir()):
    allowed_legacy_entries = {"current", "previous", "versions"}
    actual_entries = {entry.name for entry in install_root.iterdir()}
    legacy_manifest = old_current / "release-manifest.json" if old_current else None
    try:
        legacy_payload = json.loads(legacy_manifest.read_text(encoding="utf-8")) if legacy_manifest else {}
        old_current.relative_to((install_root / "versions").resolve()) if old_current else None
    except (OSError, ValueError, json.JSONDecodeError):
        legacy_payload = {}
    if actual_entries - allowed_legacy_entries or legacy_payload.get("product") != "AgentOps MIS Private Host":
        raise SystemExit("non-empty install root lacks a valid product ownership marker")

shim = bin_dir / "agentops"
worker_shim = bin_dir / "agentops-worker"

def shim_content(module):
    quoted_current = shlex.quote(str(current))
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        f"cd {quoted_current}\n"
        f"PYTHONPATH={quoted_current} exec python3 -m {module} \"$@\"\n"
    )

for candidate, module in ((shim, "agentops_mis_cli"), (worker_shim, "agentops_mis_cli.worker")):
    if candidate.exists() or candidate.is_symlink():
        if candidate.is_symlink() or not old_current:
            raise SystemExit(f"existing {candidate.name} shim ownership cannot be verified")
        try:
            existing_shim = candidate.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            raise SystemExit(f"existing {candidate.name} shim ownership cannot be verified")
        if existing_shim != shim_content(module):
            raise SystemExit(f"existing {candidate.name} shim ownership cannot be verified")
if target.exists():
    raise SystemExit(f"version is already installed: {version}")
pre_update_backup = None
if old_current:
    database = data_root / "data" / "agentops_mis.db"
    backup_utility = old_current / "scripts" / "agentops_local_backup.py"
    if database.is_file():
        if not backup_utility.is_file():
            raise SystemExit("installed version lacks the required pre-update backup utility")
        backup_dir = data_root / "backups"
        process = subprocess.run(
            [
                sys.executable,
                str(backup_utility),
                "create",
                "--db-path",
                str(database),
                "--backup-dir",
                str(backup_dir),
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        try:
            backup_payload = json.loads(process.stdout)
        except json.JSONDecodeError:
            backup_payload = {}
        if process.returncode != 0 or backup_payload.get("ok") is not True:
            raise SystemExit("verified pre-update ledger backup failed")
        pre_update_backup = backup_payload.get("backup_path")
target.parent.mkdir(parents=True, exist_ok=True)
stage = Path(tempfile.mkdtemp(prefix=f".install-{version}-", dir=target.parent))
try:
    shutil.copytree(bundle / "payload", stage, dirs_exist_ok=True, symlinks=False)
    shutil.copy2(manifest_path, stage / "release-manifest.json")
    stage.rename(target)
finally:
    if stage.exists():
        shutil.rmtree(stage)

def atomic_symlink(link, destination):
    temporary = link.with_name(link.name + ".next")
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(destination)
    os.replace(temporary, link)

if not install_marker.exists():
    marker_stage = install_root / ".agentops-mis-install.json.next"
    marker_stage.write_text(json.dumps(expected_install_marker, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    marker_stage.chmod(0o600)
    os.replace(marker_stage, install_marker)
install_marker.chmod(0o600)

if old_current and old_current != target:
    atomic_symlink(previous, old_current)
atomic_symlink(current, target)

bin_dir.mkdir(parents=True, exist_ok=True)

def atomic_write_shim(candidate, content):
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{candidate.name}.",
        suffix=".next",
        dir=candidate.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o755)
        os.replace(temporary, candidate)
    finally:
        temporary.unlink(missing_ok=True)

for candidate, module in ((shim, "agentops_mis_cli"), (worker_shim, "agentops_mis_cli.worker")):
    atomic_write_shim(candidate, shim_content(module))

launcher_installed = False
if install_app:
    app_dir.mkdir(parents=True, exist_ok=True)
    stage_parent = Path(tempfile.mkdtemp(prefix=".agentops-mis-app-", dir=app_dir))
    stage_app = stage_parent / "AgentOps MIS.app"
    contents = stage_app / "Contents"
    macos = contents / "MacOS"
    resources = contents / "Resources"
    macos.mkdir(parents=True)
    resources.mkdir(parents=True)
    launcher_source = target / "packaging" / "macos" / "launcher.py"
    if not launcher_source.is_file():
        raise SystemExit("installed release lacks the managed macOS launcher")
    shutil.copy2(launcher_source, resources / "launcher.py")
    (resources / "launcher.py").chmod(0o644)
    launcher_config = {
        "schema_version": 1,
        "product": "AgentOps MIS Private Host Launcher",
        "version": version,
        "agentops_path": str(shim),
        "bin_dir": str(bin_dir),
        "current_path": str(current),
        "host_home": str(data_root),
        "install_root": str(install_root),
        "python_path": str(Path(sys.executable).resolve()),
        "default_port": 18878,
        "credentials_included": False,
    }
    (resources / "launcher-config.json").write_text(
        json.dumps(launcher_config, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (resources / "launcher-config.json").chmod(0o644)
    (resources / "agentops-mis-launcher.json").write_text(
        json.dumps(launcher_marker_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (resources / "agentops-mis-launcher.json").chmod(0o644)
    (contents / "Info.plist").write_text(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n"
        "<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n"
        "<plist version=\"1.0\">\n"
        "<dict>\n"
        "  <key>CFBundleDisplayName</key><string>AgentOps MIS</string>\n"
        "  <key>CFBundleExecutable</key><string>agentops-mis-launcher</string>\n"
        "  <key>CFBundleIdentifier</key><string>dev.agentops.mis.private-host</string>\n"
        "  <key>CFBundleName</key><string>AgentOps MIS</string>\n"
        "  <key>CFBundlePackageType</key><string>APPL</string>\n"
        f"  <key>CFBundleShortVersionString</key><string>{version}</string>\n"
        "  <key>CFBundleVersion</key><string>1</string>\n"
        "  <key>LSUIElement</key><true/>\n"
        "</dict>\n"
        "</plist>\n",
        encoding="utf-8",
    )
    executable = macos / "agentops-mis-launcher"
    final_launcher_source = app_bundle / "Contents" / "Resources" / "launcher.py"
    executable.write_text(
        "#!/bin/sh\n"
        "set -eu\n"
        f"exec {shlex.quote(str(Path(sys.executable).resolve()))} {shlex.quote(str(final_launcher_source))} \"$@\"\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    backup_app = app_dir / ".AgentOps MIS.app.previous"
    if backup_app.exists() or backup_app.is_symlink():
        shutil.rmtree(stage_parent)
        raise SystemExit("stale AgentOps MIS application update state; install refused")
    previous_app = False
    try:
        if app_bundle.exists():
            app_bundle.rename(backup_app)
            previous_app = True
        stage_app.rename(app_bundle)
    except Exception:
        if previous_app and backup_app.exists() and not app_bundle.exists():
            backup_app.rename(app_bundle)
        raise
    else:
        if previous_app:
            shutil.rmtree(backup_app)
        launcher_installed = True
    finally:
        if stage_parent.exists():
            shutil.rmtree(stage_parent)

fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
os.close(lock_descriptor)

print(json.dumps({
    "ok": True,
    "operation": "install",
    "version": version,
    "install_path": str(target),
    "current_path": str(current),
    "previous_version": old_current.name if old_current and old_current != target else None,
    "pre_update_backup_path": pre_update_backup,
    "shim": str(shim),
    "worker_shim": str(worker_shim),
    "launcher": str(app_bundle) if install_app else None,
    "launcher_installed": launcher_installed,
    "launcher_starts_live_workers": False,
    "user_data_preserved": True,
}, indent=2, sort_keys=True))
PY
