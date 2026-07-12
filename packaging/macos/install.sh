#!/bin/sh
set -eu

BUNDLE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
INSTALL_ROOT=${AGENTOPS_INSTALL_ROOT:-"$HOME/.local/share/agentops-mis"}
BIN_DIR=${AGENTOPS_BIN_DIR:-"$HOME/.local/bin"}

python3 - "$BUNDLE_DIR" "$INSTALL_ROOT" "$BIN_DIR" <<'PY'
import json
import hashlib
import shutil
import stat
import sys
from pathlib import Path

bundle = Path(sys.argv[1]).resolve()
install_root = Path(sys.argv[2]).expanduser().resolve()
bin_dir = Path(sys.argv[3]).expanduser().resolve()
manifest_path = bundle / "manifest.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
version = str(manifest["version"])
if not version or any(char not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for char in version):
    raise SystemExit("invalid bundle version")
target = install_root / "versions" / version

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

if target.exists():
    shutil.rmtree(target)
target.parent.mkdir(parents=True, exist_ok=True)
shutil.copytree(bundle / "payload", target, symlinks=False)

current = install_root / "current"
current.parent.mkdir(parents=True, exist_ok=True)
if current.is_symlink() or current.exists():
    if current.is_dir() and not current.is_symlink():
        shutil.rmtree(current)
    else:
        current.unlink()
current.symlink_to(target)

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
    "shim": str(shim),
    "user_data_preserved": True,
}, indent=2, sort_keys=True))
PY
