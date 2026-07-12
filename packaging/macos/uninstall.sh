#!/bin/sh
set -eu

INSTALL_ROOT=${AGENTOPS_INSTALL_ROOT:-"$HOME/.local/share/agentops-mis"}
BIN_DIR=${AGENTOPS_BIN_DIR:-"$HOME/.local/bin"}
DATA_ROOT=${AGENTOPS_HOST_HOME:-"$HOME/.agentops/host"}

python3 - "$INSTALL_ROOT" "$BIN_DIR" "$DATA_ROOT" "${AGENTOPS_PURGE_DATA:-false}" <<'PY'
import json
import shutil
import sys
from pathlib import Path

install_root = Path(sys.argv[1]).expanduser().resolve()
bin_dir = Path(sys.argv[2]).expanduser().resolve()
data_root = Path(sys.argv[3]).expanduser().resolve()
purge_data = sys.argv[4].lower() in {"1", "true", "yes"}
shim = bin_dir / "agentops"

if shim.exists() or shim.is_symlink():
    shim.unlink()
if install_root.exists():
    shutil.rmtree(install_root)
if purge_data and data_root.exists():
    shutil.rmtree(data_root)

print(json.dumps({
    "ok": True,
    "operation": "uninstall",
    "install_removed": not install_root.exists(),
    "shim_removed": not shim.exists(),
    "user_data_preserved": not purge_data,
    "data_path": str(data_root),
}, indent=2, sort_keys=True))
PY

