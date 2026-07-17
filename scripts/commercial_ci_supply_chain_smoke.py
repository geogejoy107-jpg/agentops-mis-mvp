#!/usr/bin/env python3
"""Fail closed when commercial CI execution inputs are movable."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "commercial-migration-ci.yml"
CONTRACT = "commercial_ci_supply_chain_pins_v1"
EXPECTED_ACTION_PINS = {
    "actions/checkout": "11bd71901bbe5b1630ceea73d27597364c9af683",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/setup-node": "49933ea5288caeca8642d1e84afbd3f7d6820020",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
    "actions/download-artifact": "d3f86a106a0bac45b974a628896c90dbdf5c8093",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    text = WORKFLOW.read_text(encoding="utf-8")
    action_refs = re.findall(r"uses:\s+(actions/[a-z-]+)@([^\s#]+)", text)
    require(action_refs, "commercial workflow has no first-party action references")
    for action, ref in action_refs:
        require(action in EXPECTED_ACTION_PINS, f"unexpected first-party action: {action}")
        require(ref == EXPECTED_ACTION_PINS[action], f"movable or unexpected action ref: {action}@{ref}")
        require(bool(re.fullmatch(r"[0-9a-f]{40}", ref)), f"action is not commit pinned: {action}")

    require("ubuntu-latest" not in text, "commercial workflow runner is movable")
    require(text.count("runs-on: ubuntu-24.04") == 5, "commercial workflow runner coverage changed")
    require('python-version: "3.11.9"' in text, "Python patch version is not pinned")
    require('node-version: "20.19.4"' in text, "Node patch version is not pinned")
    require("@playwright/cli@0.1.17" in text, "Playwright CLI version is not pinned")
    require("--package @playwright/cli playwright-cli" not in text, "movable Playwright CLI package remains")
    require(
        bool(re.search(r'AGENTOPS_POSTGRES_IMAGE:\s+"postgres:16\.14-alpine3\.23@sha256:[0-9a-f]{64}"', text)),
        "Postgres image is not tag-and-digest pinned",
    )

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT,
        "workflow": str(WORKFLOW.relative_to(ROOT)),
        "action_pin_count": len(action_refs),
        "unique_action_count": len(set(action for action, _ref in action_refs)),
        "runner": "ubuntu-24.04",
        "python": "3.11.9",
        "node": "20.19.4",
        "playwright_cli": "0.1.17",
        "postgres_tag_and_digest_required": True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
