#!/usr/bin/env python3
"""
Install the repo-local AgentOps CLI as a local user command.

This is intentionally a lightweight local install, not a package manager. It
writes a small shim to <prefix>/bin/agentops that executes this repository's
scripts/agentops wrapper.
"""
from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "agentops"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install AgentOps MIS CLI into a local bin directory.")
    parser.add_argument("--prefix", default=os.environ.get("AGENTOPS_CLI_PREFIX", "~/.local"), help="Install prefix. Default: ~/.local")
    parser.add_argument("--force", action="store_true", help="Overwrite an existing non-AgentOps shim.")
    args = parser.parse_args()

    prefix = Path(args.prefix).expanduser().resolve()
    bin_dir = prefix / "bin"
    target = bin_dir / "agentops"
    bin_dir.mkdir(parents=True, exist_ok=True)

    marker = f"# agentops-mis-mvp source={SOURCE}\n"
    if target.exists():
        existing = target.read_text(encoding="utf-8", errors="replace") if target.is_file() else ""
        if "agentops-mis-mvp source=" not in existing and not args.force:
            print(json.dumps({
                "ok": False,
                "installed": False,
                "target": str(target),
                "error": "target exists and is not an AgentOps MIS shim; rerun with --force to overwrite",
            }, ensure_ascii=False, indent=2))
            return 1

    shim = f"""#!/usr/bin/env sh
{marker}exec "{SOURCE}" "$@"
"""
    target.write_text(shim, encoding="utf-8")
    target.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
    print(json.dumps({
        "ok": True,
        "installed": True,
        "target": str(target),
        "source": str(SOURCE),
        "path_hint": f"export PATH=\"{bin_dir}:$PATH\"",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
