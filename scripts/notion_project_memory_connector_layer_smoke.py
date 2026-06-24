#!/usr/bin/env python3
"""Static smoke for the Notion Project Memory connector boundary.

This script is intentionally read-only. It does not call Notion, does not read
environment tokens, and does not mutate the MIS ledger. Its job is to prevent
the project-memory collaboration layer from being confused with the execution
authority ledger.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


REQUIRED_FRAGMENTS = {
    "docs/NOTION_PROJECT_MEMORY_CONNECTOR_LAYER.md": [
        "Web GPT",
        "Notion Project Ledger",
        "AgentOps MIS SQLite/API",
        "Authority Model",
        "prepared-action approval",
        "Project Ledger preview",
        "project-memory canonical",
    ],
    "docs/project/CHATGPT_PROJECT_INSTRUCTIONS.md": [
        "Notion MIS Project Ledger",
        "Canonical=false",
        "Inbox",
        "Proposed",
    ],
    "docs/project/PROJECT_OPERATING_RULES.md": [
        "Notion MIS Project Ledger",
        "AgentOps MIS SQLite/API",
    ],
    "docs/API_SPEC.md": [
        "POST /api/integrations/notion/sync-memory-candidates",
        "NOTION_TOKEN=",
    ],
    "server.py": [
        "notion_sync_memory_candidates",
        "notion_import_preview",
        "notion_export_live_or_gate",
        "prepared_action_required",
        "token_omitted",
    ],
    "README.md": [
        "Notion External Base",
        "dry-run",
    ],
}


FORBIDDEN_DOC_FRAGMENTS = [
    "Notion is the runtime authority",
    "Notion owns runtime execution",
    "store full prompt",
    "store full raw response",
    "commit NOTION_TOKEN",
]


def read_text(relative_path: str) -> str:
    path = ROOT / relative_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def main() -> int:
    failures: list[dict[str, object]] = []
    fragment_results: dict[str, dict[str, object]] = {}

    for relative_path, fragments in REQUIRED_FRAGMENTS.items():
        text = read_text(relative_path)
        missing = [fragment for fragment in fragments if fragment not in text]
        fragment_results[relative_path] = {
            "missing_file": not bool(text),
            "missing_fragments": missing,
            "ok": bool(text) and not missing,
        }
        if not text:
            failures.append({"file": relative_path, "reason": "missing_file"})
        if missing:
            failures.append({"file": relative_path, "reason": "missing_fragments", "missing": missing})

    scanned_doc = read_text("docs/NOTION_PROJECT_MEMORY_CONNECTOR_LAYER.md")
    forbidden_hits = [fragment for fragment in FORBIDDEN_DOC_FRAGMENTS if fragment in scanned_doc]
    if forbidden_hits:
        failures.append({"file": "docs/NOTION_PROJECT_MEMORY_CONNECTOR_LAYER.md", "reason": "forbidden_fragments", "hits": forbidden_hits})

    payload = {
        "operation": "notion_project_memory_connector_layer_smoke",
        "ok": not failures,
        "contract": "Notion Project Memory is a Web GPT/human collaboration layer; MIS remains execution-ledger authority.",
        "evidence": {
            "fragment_results": fragment_results,
            "forbidden_doc_fragment_hits": forbidden_hits,
        },
        "safety": {
            "read_only": True,
            "notion_api_called": False,
            "ledger_mutated": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
        },
        "recommended_next": [
            "Add a read-only Project Ledger preview endpoint before any live sync.",
            "Map Notion Inbox/Proposed entries to MIS candidates, not canonical runtime facts.",
            "Use prepared-action approval before any real Notion writeback.",
        ],
        "failures": failures,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
