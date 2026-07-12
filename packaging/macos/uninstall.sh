#!/bin/sh
set -eu

INSTALL_ROOT=${AGENTOPS_INSTALL_ROOT:-"$HOME/.local/share/agentops-mis"}
BIN_DIR=${AGENTOPS_BIN_DIR:-"$HOME/.local/bin"}
DATA_ROOT=${AGENTOPS_HOST_HOME:-"$HOME/.agentops/host"}

python3 - "$INSTALL_ROOT" "$BIN_DIR" "$DATA_ROOT" "${AGENTOPS_PURGE_DATA:-false}" <<'PY'
import json
import fcntl
import os
import shlex
import shutil
import stat
import sys
from pathlib import Path

raw_install_root = Path(sys.argv[1]).expanduser()
raw_bin_dir = Path(sys.argv[2]).expanduser()
raw_data_root = Path(sys.argv[3]).expanduser()
if raw_install_root.is_symlink() or raw_bin_dir.is_symlink() or raw_data_root.is_symlink():
    raise SystemExit("unsafe symlinked uninstall path")
install_root = raw_install_root.resolve()
bin_dir = raw_bin_dir.resolve()
data_root = raw_data_root.resolve()
purge_data = sys.argv[4].lower() in {"1", "true", "yes"}
shim = bin_dir / "agentops"
home = Path.home().resolve()

def require_home_managed_path(path, label):
    try:
        relative = path.relative_to(home)
    except ValueError:
        raise SystemExit(f"{label} is outside HOME; automatic uninstall refused")
    if len(relative.parts) < 2:
        raise SystemExit(f"unsafe {label}")

require_home_managed_path(install_root, "install root")
require_home_managed_path(bin_dir, "binary directory")
require_home_managed_path(data_root, "Host data root")
if (
    install_root == data_root
    or install_root in data_root.parents
    or data_root in install_root.parents
    or install_root == bin_dir
    or install_root in bin_dir.parents
    or data_root == bin_dir
    or data_root in bin_dir.parents
    or bin_dir in data_root.parents
):
    raise SystemExit("overlapping uninstall roots are unsafe")

expected_install_marker = {
    "schema_version": 1,
    "product": "AgentOps MIS Private Host",
    "managed": True,
}
install_marker = install_root / ".agentops-mis-install.json"
try:
    install_marker_payload = json.loads(install_marker.read_text(encoding="utf-8"))
except (OSError, json.JSONDecodeError):
    raise SystemExit("installed product ownership marker is missing or invalid")
if install_marker.is_symlink() or install_marker_payload != expected_install_marker:
    raise SystemExit("installed product ownership marker is missing or invalid")

if shim.is_symlink():
    raise SystemExit("CLI shim ownership cannot be verified")
if shim.exists():
    try:
        shim_text = shim.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        raise SystemExit("CLI shim ownership cannot be verified")
    quoted_current = shlex.quote(str(install_root / "current"))
    expected_shim = (
        "#!/bin/sh\n"
        "set -eu\n"
        f"cd {quoted_current}\n"
        f"PYTHONPATH={quoted_current} exec python3 -m agentops_mis_cli \"$@\"\n"
    )
    if shim_text != expected_shim:
        raise SystemExit("CLI shim ownership cannot be verified")

if purge_data:
    expected_data_marker = {
        "schema_version": 1,
        "product": "AgentOps MIS Private Host Data",
        "managed": True,
    }
    data_marker = data_root / ".agentops-host-data.json"
    try:
        data_marker_payload = json.loads(data_marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise SystemExit("Host data ownership marker is missing or invalid; purge refused")
    if data_marker.is_symlink() or data_marker_payload != expected_data_marker:
        raise SystemExit("Host data ownership marker is missing or invalid; purge refused")

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
    raise SystemExit("Host lifecycle lock is not a regular file; uninstall refused")
os.fchmod(lock_descriptor, 0o600)
try:
    fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    os.close(lock_descriptor)
    raise SystemExit("Host lifecycle operation is active; uninstall refused")

pid_path = data_root / "run" / "host.pid.json"
if pid_path.exists():
    try:
        payload = json.loads(pid_path.read_text(encoding="utf-8"))
        pid = int(payload.get("pid") or 0) if isinstance(payload, dict) else 0
    except (OSError, ValueError, json.JSONDecodeError):
        raise SystemExit("cannot verify managed Host process state; uninstall refused")
    if pid <= 0:
        raise SystemExit("invalid managed Host PID record; uninstall refused")
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        pass
    except PermissionError:
        raise SystemExit("cannot verify managed Host process state; uninstall refused")
    else:
        raise SystemExit("AgentOps MIS Host is running; stop it before uninstalling")

if shim.exists():
    shim.unlink()
if install_root.exists():
    shutil.rmtree(install_root)
if purge_data and data_root.exists():
    shutil.rmtree(data_root)
fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
os.close(lock_descriptor)

print(json.dumps({
    "ok": True,
    "operation": "uninstall",
    "install_removed": not install_root.exists(),
    "shim_removed": not shim.exists(),
    "user_data_preserved": not purge_data,
    "data_path": str(data_root),
}, indent=2, sort_keys=True))
PY
