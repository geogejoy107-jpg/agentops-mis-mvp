#!/usr/bin/env python3
"""Smoke-test local installation of the repo AgentOps CLI shim."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="agentops-cli-install-") as tmp:
        prefix = Path(tmp)
        install = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "install_agentops_cli.py"), "--prefix", str(prefix)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if install.returncode != 0:
            print(install.stderr or install.stdout, file=sys.stderr)
            return 1
        payload = json.loads(install.stdout)
        target = Path(payload["target"])
        help_run = subprocess.run(
            [str(target), "--help"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        ok = payload.get("ok") is True and target.exists() and help_run.returncode == 0 and "AgentOps MIS local Agent Gateway CLI" in help_run.stdout
        print(json.dumps({
            "ok": ok,
            "target": str(target),
            "install_ok": payload.get("ok"),
            "help_returncode": help_run.returncode,
            "token_written": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
