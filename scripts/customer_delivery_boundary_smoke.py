#!/usr/bin/env python3
"""Verify customer delivery report UI separates customer content from internal evidence."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "CustomerProjectReport.tsx"
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"
SERVER = ROOT / "server.py"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
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
    report_ui = REPORT.read_text(encoding="utf-8")
    live_api = LIVE_API.read_text(encoding="utf-8")
    server = SERVER.read_text(encoding="utf-8")
    customer_metrics = extract_block(report_ui, "const metrics = [", "return (")
    customer_article = extract_block(report_ui, "<article", "data-testid=\"internal-evidence-index\"")
    internal_section = extract_block(report_ui, 'data-testid="internal-evidence-index"', "</section>")
    report_function = extract_block(server, "def customer_project_report", "def customer_projects_index")

    expected = {
        "internal_evidence_type": "internal_evidence?:",
        "report_boundary_type": "report_boundary?:",
        "internal_evidence_payload": '"internal_evidence": internal_evidence',
        "report_boundary_payload": '"report_boundary": report_boundary',
        "customer_exclusion_flag": '"customer_markdown_excludes_internal_evidence": True',
        "internal_separated_flag": '"internal_evidence_separated": True',
        "raw_prompt_omitted": '"raw_prompts_omitted": True',
        "private_transcripts_omitted": '"private_transcripts_omitted": True',
        "safe_raw_prompts_false": '"raw_prompts_stored": False',
        "safe_private_transcripts_false": '"private_transcripts_stored": False',
        "ui_internal_section": 'data-testid="internal-evidence-index"',
        "ui_not_customer_report": "not part of the customer report body",
        "ui_internal_evidence": "internalEvidence",
        "ui_report_boundary": "report.report_boundary",
        "ui_lock_icon": "LockKeyhole",
    }
    bundle = "\n".join([report_ui, live_api, server])
    for label, marker in expected.items():
        require(marker in bundle, f"missing {label}: {marker}", failures)

    require("Tool calls" not in customer_metrics and "工具调用" not in customer_metrics, "customer-facing metric strip should not show tool calls", failures)
    require("Tool calls" in internal_section and "Audit logs" in internal_section, "internal evidence section should retain operator evidence counts", failures)
    require("internalEvidence.delivery_artifact_id" in internal_section, "internal evidence section should show delivery artifact id", failures)
    require("markdownLines.map(renderMarkdownLine)" in customer_article, "customer markdown article should render before internal evidence section", failures)
    require('"## Delivery Progress"' in report_function, "server customer markdown should expose Delivery Progress", failures)
    require('"## Task Ledger"' not in report_function, "server customer markdown must not expose Task Ledger section", failures)
    require('f"- Tool calls:' not in report_function, "server customer markdown must not expose tool-call counts", failures)
    require('f"- Memory candidates:' not in report_function, "server customer markdown must not expose memory candidate counts", failures)
    require("raw model responses and private transcripts included in this customer report: false" in report_function, "server markdown must state raw prompt/transcript exclusion", failures)

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(bundle)]
    require(not secret_hits, f"secret-like marker found in customer delivery boundary source: {secret_hits}", failures)

    output = {
        "ok": not failures,
        "operation": "customer_delivery_boundary_smoke",
        "files": [str(REPORT.relative_to(ROOT)), str(LIVE_API.relative_to(ROOT)), str(SERVER.relative_to(ROOT))],
        "contract": "Customer report markdown is customer-facing; internal run/tool/approval/audit evidence is separated into an operator-only evidence index.",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
