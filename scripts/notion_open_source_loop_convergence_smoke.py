#!/usr/bin/env python3
"""Static smoke for Notion/open-source/loop convergence planning."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


REQUIRED = {
    "docs/NOTION_OPEN_SOURCE_LOOP_CONVERGENCE_PLAN.md": [
        "Notion Project Memory",
        "Local Open Source Experiment Base",
        "Local Hermes/OpenClaw loop convergence",
        "PR #25",
        "PR #26",
        "codex/loop-bootstrap-fast-path",
        "Notion entries auto-promote",
        "Local Loop Convergence Acceptance",
        "Live Hermes/OpenClaw execution",
    ],
    "docs/project/CHATGPT_PROJECT_INSTRUCTIONS.md": [
        "Notion MIS Project Ledger",
        "AgentOps MIS SQLite/API",
    ],
    "docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md": [
        "AgentOps MIS may borrow open-source tools",
        "source of truth",
    ],
}


FORBIDDEN = [
    "store credentials",
    "full raw prompt",
    "full raw response",
    "Notion owns runtime execution",
    "Notion is the runtime authority",
]


def text(path: str) -> str:
    p = ROOT / path
    return p.read_text(encoding="utf-8") if p.exists() else ""


def main() -> int:
    failures: list[dict[str, object]] = []
    fragments: dict[str, dict[str, object]] = {}
    for path, required_fragments in REQUIRED.items():
        body = text(path)
        missing = [fragment for fragment in required_fragments if fragment not in body]
        fragments[path] = {"ok": bool(body) and not missing, "missing_file": not bool(body), "missing_fragments": missing}
        if not body:
            failures.append({"file": path, "reason": "missing_file"})
        if missing:
            failures.append({"file": path, "reason": "missing_fragments", "missing": missing})

    plan = text("docs/NOTION_OPEN_SOURCE_LOOP_CONVERGENCE_PLAN.md")
    forbidden_hits = [fragment for fragment in FORBIDDEN if fragment in plan]
    if forbidden_hits:
        failures.append({"file": "docs/NOTION_OPEN_SOURCE_LOOP_CONVERGENCE_PLAN.md", "reason": "forbidden_fragments", "hits": forbidden_hits})

    payload = {
        "operation": "notion_open_source_loop_convergence_smoke",
        "ok": not failures,
        "contract": "Notion collaboration, open-source experiments, and local Hermes/OpenClaw loops converge through explicit authority boundaries.",
        "evidence": {
            "fragment_results": fragments,
            "forbidden_fragment_hits": forbidden_hits,
        },
        "safety": {
            "read_only": True,
            "notion_api_called": False,
            "ledger_mutated": False,
            "live_runtime_executed": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
        },
        "recommended_next": [
            "Record a short Proposed Project Ledger entry in Notion.",
            "Resolve PR #25 and PR #26 before rebasing the fast loop branch.",
            "Open a focused PR for codex/loop-bootstrap-fast-path after base layers land.",
        ],
        "failures": failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
