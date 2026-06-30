#!/usr/bin/env python3
"""Verify Admin Connectors exposes safe commercial config operator next actions."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_CONNECTORS = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "RuntimeConnectors.tsx"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_(API|ADMIN)_KEY=", re.IGNORECASE),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def extract_block(text: str, start_marker: str, end_marker: str) -> str:
    start = text.find(start_marker)
    if start < 0:
        return ""
    end = text.find(end_marker, start)
    if end < 0:
        return text[start:]
    return text[start:end]


def main() -> int:
    failures: list[str] = []
    ui = RUNTIME_CONNECTORS.read_text(encoding="utf-8")
    block = extract_block(ui, 'data-testid="commercial-config-operator-action"', "</div>\n        </div>\n      )}")

    required_markers = {
        "operator_action_test_id": 'data-testid="commercial-config-operator-action"',
        "english_title": 'operatorNextAction: "Operator next action"',
        "chinese_title": 'operatorNextAction: "操作员下一步"',
        "cli_command": "agentops commercial config-status",
        "evidence_doc": "docs/COMMERCIAL_CONFIG_STATUS_UI_ACCEPTANCE.md",
        "read_only_badge": "read_only_cli",
        "no_billing_cleanup_en": "No billing, cleanup, hosted-readiness or live-runtime action is performed from this panel.",
        "no_billing_cleanup_zh": "此面板不会执行 billing、cleanup、hosted-readiness 或真实运行时动作。",
    }
    for label, marker in required_markers.items():
        require(marker in ui, f"missing operator action marker {label}: {marker}", failures)

    require(bool(block), "commercial config operator action block missing", failures)
    require("StatusBadge status=\"pass\"" in block, "operator action block must render a passing read-only badge", failures)
    require("agentops commercial config-status" in block, "operator action block must expose the CLI verification command", failures)
    require("docs/COMMERCIAL_CONFIG_STATUS_UI_ACCEPTANCE.md" in block, "operator action block must link the acceptance evidence path", failures)

    forbidden_runtime_markers = [
        "confirm_run",
        "confirm_export",
        "confirm_upload",
        "cleanup_execution_enabled: true",
        "billing_calls_enabled: true",
        "live_execution_performed: true",
        "apiJson<",
        "updateRuntimeConnectorTrust(",
    ]
    for marker in forbidden_runtime_markers:
        if marker == "updateRuntimeConnectorTrust(":
            # The page has runtime trust mutation elsewhere; this operator block must not add one.
            require(marker not in block, f"operator action block must not mutate trust state: {marker}", failures)
        else:
            require(marker not in block, f"operator action block must remain read-only: {marker}", failures)

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(block)]
    require(not secret_hits, f"secret-like marker found in operator action block: {secret_hits}", failures)

    print(json.dumps({
        "operation": "commercial_config_operator_action_ui_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "files": [str(RUNTIME_CONNECTORS.relative_to(ROOT))],
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "billing_call_performed": False,
            "cleanup_execution_performed": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
