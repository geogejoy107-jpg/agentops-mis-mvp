#!/bin/sh
set -eu

BUNDLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_ROOT=${AGENTOPS_INSTALL_ROOT:-"$HOME/.local/share/agentops-mis"}
BIN_DIR=${AGENTOPS_BIN_DIR:-"$HOME/.local/bin"}
DATA_ROOT=${AGENTOPS_HOST_HOME:-"$HOME/.agentops/host"}

python3 - "$BUNDLE_DIR" "$INSTALL_ROOT" "$BIN_DIR" "$DATA_ROOT" <<'PY'
import json
import hashlib
import os
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

pid_path = data_root / "run" / "host.pid.json"
if pid_path.is_file():
    try:
        pid = int(json.loads(pid_path.read_text(encoding="utf-8")).get("pid") or 0)
        if pid > 0:
            os.kill(pid, 0)
            raise SystemExit("AgentOps MIS Host is running; stop it before installing an update")
    except ProcessLookupError:
        pass
    except PermissionError:
        raise SystemExit("cannot verify Host process state; update refused")
    except (OSError, ValueError, json.JSONDecodeError):
        pass

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

if old_current and old_current != target:
    atomic_symlink(previous, old_current)
atomic_symlink(current, target)

bin_dir.mkdir(parents=True, exist_ok=True)
shim = bin_dir / "agentops"
shim.write_text(
    "#!/bin/sh\n"
    "set -eu\n"
    f'PYTHONPATH="{current}${{PYTHONPATH:+:$PYTHONPATH}}" '
    'exec python3 -m agentops_mis_cli "$@"\n',
    encoding="utf-8",
)
shim.chmod(shim.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

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
