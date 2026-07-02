#!/usr/bin/env python3
"""Verify Run Ledger exposes evidence review affordances without extra runtime action."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUN_LEDGER = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "RunLedger.tsx"
RUN_DETAIL = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "RunDetail.tsx"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{20,}"),
]


def main() -> int:
    failures: list[str] = []
    run_ledger = RUN_LEDGER.read_text(encoding="utf-8")
    run_detail = RUN_DETAIL.read_text(encoding="utf-8")
    source_bundle = f"{run_ledger}\n{run_detail}"

    expected_markers = {
        "run_ledger_live_runs": "loadRuns",
        "run_ledger_evidence_header_en": '"Evidence"',
        "run_ledger_evidence_header_zh": '"证据"',
        "run_ledger_evidence_testid": 'data-testid="run-ledger-evidence-entry"',
        "run_ledger_graph_anchor_link": 'to={`/admin/runs/${run.run_id}#work-delivery-graph`}',
        "run_ledger_open_graph_en": "Open graph",
        "run_ledger_open_graph_zh": "查看图谱",
        "run_ledger_live_runtime_marker": "liveRuntime",
        "run_ledger_approval_wall_marker": "run.approval_required",
        "run_ledger_no_graph_loader": "loadRunEvidenceGraph",
        "run_detail_graph_anchor": 'id="work-delivery-graph"',
        "run_detail_graph_testid": 'data-testid="run-detail-work-delivery-graph"',
    }
    for label, marker in expected_markers.items():
        if label == "run_ledger_no_graph_loader":
            if marker in run_ledger:
                failures.append("Run Ledger must not call evidence-graph for every row")
            continue
        if marker not in source_bundle:
            failures.append(f"missing {label}: {marker}")

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(source_bundle)]
    if secret_hits:
        failures.append(f"secret-like pattern found in run ledger UI source: {secret_hits}")

    output = {
        "operation": "run_ledger_evidence_ui_smoke",
        "ok": not failures,
        "files": [str(RUN_LEDGER.relative_to(ROOT)), str(RUN_DETAIL.relative_to(ROOT))],
        "markers_checked": len(expected_markers),
        "failures": failures,
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
            "avoids_row_by_row_graph_fetch": True,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
