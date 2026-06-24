#!/usr/bin/env python3
"""Validate the Open Source Base Index v1.1 research packet without extra deps."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "docs" / "research" / "OPEN_SOURCE_BASE_REGISTRY_V1_1.yaml"
REQUIRED_DOCS = [
    ROOT / "docs" / "research" / "OPEN_SOURCE_BASE_INDEX_V1_1.md",
    ROOT / "docs" / "research" / "OSBI_V1_1_FINAL_PLAN.md",
    ROOT / "docs" / "research" / "OSBI_V1_1_HANDOFF.md",
    ROOT / "docs" / "research" / "evidence" / "OSBI_V1_1_EVIDENCE_COMPENDIUM.md",
]
REQUIRED_IDS = {
    "openai_agents_sdk",
    "jiuwenswarm",
    "git_worktree",
    "mcp",
    "sqlite_fts5",
    "sqlite_wal",
    "gitleaks",
    "opentelemetry",
    "promptfoo",
    "spdx",
}
SAFE_AUTHORITY_MARKERS = [
    "first-party control plane and evidence ledger",
    "first-party MIS authority boundary",
    "Agent Gateway remains authority",
    "NOT_INTEGRATED",
]
SECRET_MARKERS = ["Authorization:", "Bearer ", "sk-", "ntn_", "AGENTOPS_API_KEY="]


def fail(message: str) -> int:
    print(json.dumps({"ok": False, "error": message}, ensure_ascii=False, indent=2), file=sys.stderr)
    return 1


def main() -> int:
    if not REGISTRY.exists():
        return fail(f"missing registry: {REGISTRY.relative_to(ROOT)}")

    registry_text = REGISTRY.read_text(encoding="utf-8")
    ids = re.findall(r'\{\s*id:\s*"([^"]+)"', registry_text)
    decisions = re.findall(r'decision:\s*"([^"]+)"', registry_text)
    statuses = re.findall(r'status:\s*"([^"]+)"', registry_text)

    if len(ids) < 60:
        return fail(f"expected at least 60 registry bases, got {len(ids)}")
    if len(ids) != len(set(ids)):
        duplicates = sorted({item for item in ids if ids.count(item) > 1})
        return fail(f"duplicate registry ids: {duplicates}")
    missing_ids = sorted(REQUIRED_IDS - set(ids))
    if missing_ids:
        return fail(f"missing required registry ids: {missing_ids}")
    if len(decisions) != len(ids) or len(statuses) != len(ids):
        return fail("registry entries must include decision and status for every id")
    if "ADOPT_NOW" not in decisions or "IMPLEMENTED" not in statuses:
        return fail("registry must preserve adoption and implementation states")

    combined_docs = registry_text
    for path in REQUIRED_DOCS:
        if not path.exists():
            return fail(f"missing doc: {path.relative_to(ROOT)}")
        text = path.read_text(encoding="utf-8")
        if len(text.strip()) < 1000:
            return fail(f"doc too short: {path.relative_to(ROOT)}")
        combined_docs += "\n" + text

    missing_markers = [marker for marker in SAFE_AUTHORITY_MARKERS if marker not in combined_docs]
    if missing_markers:
        return fail(f"missing authority-boundary markers: {missing_markers}")
    leaked = [marker for marker in SECRET_MARKERS if marker in combined_docs]
    if leaked:
        return fail(f"token-like marker leaked in OSBI packet: {leaked}")

    print(json.dumps({
        "ok": True,
        "operation": "osbi_v1_1_registry_smoke",
        "registry_ids": len(ids),
        "unique_ids": len(set(ids)),
        "required_docs": len(REQUIRED_DOCS),
        "authority_boundary_checked": True,
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
