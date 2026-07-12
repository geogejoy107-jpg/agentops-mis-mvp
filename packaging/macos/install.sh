#!/bin/sh
set -eu

BUNDLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_ROOT=${AGENTOPS_INSTALL_ROOT:-"$HOME/.local/share/agentops-mis"}
BIN_DIR=${AGENTOPS_BIN_DIR:-"$HOME/.local/bin"}
DATA_ROOT=${AGENTOPS_HOST_HOME:-"$HOME/.agentops/host"}

if [ "$(uname -s)" != "Darwin" ] && [ "${AGENTOPS_BUNDLE_INSTALLER_TEST_MODE:-}" != "1" ]; then
  echo "this unsigned Private Host bundle supports macOS only" >&2
  exit 2
fi
python3 - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ is required")
PY

python3 - "$BUNDLE_DIR" "$INSTALL_ROOT" "$BIN_DIR" "$DATA_ROOT" <<'PY'
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
manifest_path = bundle / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
version = str(manifest["version"])
if not version or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in version):
    raise SystemExit("invalid bundle version")
target = install_root / "versions" / version

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
if shim.exists() or shim.is_symlink():
    if shim.is_symlink() or not old_current:
        raise SystemExit("existing CLI shim ownership cannot be verified")
    try:
        existing_shim = shim.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise SystemExit("existing CLI shim ownership cannot be verified")
    quoted_old_current = shlex.quote(str(current))
    expected_shim = (
        "#!/bin/sh\n"
        "set -eu\n"
        f"cd {quoted_old_current}\n"
        f"PYTHONPATH={quoted_old_current} exec python3 -m agentops_mis_cli \"$@\"\n"
    )
    if existing_shim != expected_shim:
        raise SystemExit("existing CLI shim ownership cannot be verified")
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
quoted_current = shlex.quote(str(current))
shim.write_text(
    "#!/bin/sh\n"
    "set -eu\n"
    f"cd {quoted_current}\n"
    f"PYTHONPATH={quoted_current} exec python3 -m agentops_mis_cli \"$@\"\n",
    encoding="utf-8",
)
shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
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
    "user_data_preserved": True,
}, indent=2, sort_keys=True))
PY
