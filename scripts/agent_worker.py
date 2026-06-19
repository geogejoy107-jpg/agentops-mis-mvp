#!/usr/bin/env python3
"""Repo-local compatibility wrapper for the installable AgentOps worker."""
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentops_mis_cli.worker import *  # noqa: F401,F403 - compatibility imports
from agentops_mis_cli.worker import main


if __name__ == "__main__":
    raise SystemExit(main())
