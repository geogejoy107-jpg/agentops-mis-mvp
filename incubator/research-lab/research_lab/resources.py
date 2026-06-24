from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any


def _memory_bytes() -> int | None:
    meminfo = Path("/proc/meminfo")
    if not meminfo.exists():
        return None
    for line in meminfo.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("MemTotal:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1]) * 1024
    return None


def _gpu_inventory() -> list[dict[str, Any]]:
    executable = shutil.which("nvidia-smi")
    if not executable:
        return []
    command = [executable, "--query-gpu=index,name,uuid,memory.total,driver_version,compute_cap", "--format=csv,noheader,nounits"]
    try:
        completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    result: list[dict[str, Any]] = []
    for line in completed.stdout.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 6:
            continue
        result.append({"index": parts[0], "name": parts[1], "uuid": parts[2], "memory_total_mib": parts[3], "driver_version": parts[4], "compute_capability": parts[5]})
    return result


def git_commit(workdir: str | Path) -> str | None:
    if not shutil.which("git"):
        return None
    try:
        completed = subprocess.run(["git", "rev-parse", "HEAD"], cwd=Path(workdir), check=False, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value if completed.returncode == 0 and value else None


def runtime_fingerprint(workdir: str | Path | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "host_name": socket.gethostname(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "python_executable": sys.executable,
        "cpu_count": os.cpu_count(),
        "memory_total_bytes": _memory_bytes(),
        "gpus": _gpu_inventory(),
    }
    if workdir:
        payload["workdir"] = str(Path(workdir).resolve())
        payload["git_commit"] = git_commit(workdir)
    return payload


def pretty_inventory(workdir: str | Path | None = None) -> str:
    return json.dumps(runtime_fingerprint(workdir), ensure_ascii=False, indent=2, sort_keys=True)
