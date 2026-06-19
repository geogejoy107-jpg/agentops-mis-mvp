"""Console-script entry point for the dependency-free AgentOps CLI."""
from __future__ import annotations

from typing import Sequence

from .agentops import main as agentops_main


def main(argv: Sequence[str] | None = None) -> int:
    return int(agentops_main(list(argv) if argv is not None else None))
