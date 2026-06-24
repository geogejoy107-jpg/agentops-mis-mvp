#!/usr/bin/env python3
"""Verify review decisions update only the necessary UI data/panels."""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIVE_API = ROOT / "ui" / "start-building-app" / "src" / "app" / "data" / "liveApi.ts"
APPROVALS_INBOX = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "ApprovalsInbox.tsx"
WORKSPACE_HOME = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "WorkspaceHome.tsx"
EVALUATION_ROOM = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "EvaluationRoom.tsx"
AI_EMPLOYEES = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "AIEmployees.tsx"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{20,}"),
]


def function_block(source: str, marker: str) -> str:
    start = source.find(marker)
    if start < 0:
        raise AssertionError(f"missing function marker: {marker}")
    brace = source.find("{", start)
    if brace < 0:
        raise AssertionError(f"missing function body for: {marker}")
    depth = 0
    for index in range(brace, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated function body: {marker}")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    live_api = LIVE_API.read_text(encoding="utf-8")
    approvals = APPROVALS_INBOX.read_text(encoding="utf-8")
    home = WORKSPACE_HOME.read_text(encoding="utf-8")
    eval_room = EVALUATION_ROOM.read_text(encoding="utf-8")
    ai_employees = AI_EMPLOYEES.read_text(encoding="utf-8")

    require("return { data, setData, loading, error, refresh }" in live_api, "useLiveData does not expose setData for local refresh", failures)
    require("typeof raw.approval === \"object\"" in live_api, "decideApproval does not unwrap approval envelopes", failures)
    require("Promise<EvaluationCaseCandidate>" in live_api and "normalizeEvaluationCaseCandidate(raw)" in live_api, "decideEvaluationCase does not return a normalized case", failures)

    checks = [
        ("approvals_inbox_decision", approvals, "const handleDecision = async", ["setData((current)", "decideApproval("], ["await refresh("]),
        ("workspace_home_approval", home, "const handleApproval = async", ["setData((current)", "decideApproval("], ["await refresh("]),
        ("evaluation_case_decision", eval_room, "const handleCaseDecision = async", ["setData((current)", "decideEvaluationCase("], ["await refresh("]),
        ("ai_employees_review_queue", ai_employees, "const handleReviewDecision = async", ['refreshPanel("review_queue")'], ["await refresh("]),
        ("ai_employees_loop_record", ai_employees, "const handleLoopRecordDecision = async", ['refreshPanel("operator_loop_audit")', 'refreshPanel("operator_handoff")'], ["await refresh("]),
        ("ai_employees_enrollment_approval", ai_employees, "const decideEnrollmentApproval = async", ['refreshPanel("approvals")'], ["await refresh("]),
    ]
    for label, source, marker, required_markers, forbidden_markers in checks:
        try:
            block = function_block(source, marker)
        except AssertionError as exc:
            failures.append(f"{label}: {exc}")
            continue
        for required in required_markers:
            require(required in block, f"{label} missing local refresh marker: {required}", failures)
        for forbidden in forbidden_markers:
            require(forbidden not in block, f"{label} still does whole-page refresh: {forbidden}", failures)

    source_bundle = "\n".join([live_api, approvals, home, eval_room, ai_employees])
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(source_bundle)]
    if secret_hits:
        failures.append(f"secret-like pattern found in reviewed source: {secret_hits}")

    output = {
        "ok": not failures,
        "operation": "review_decision_local_refresh_smoke",
        "files": [
            str(path.relative_to(ROOT))
            for path in [LIVE_API, APPROVALS_INBOX, WORKSPACE_HOME, EVALUATION_ROOM, AI_EMPLOYEES]
        ],
        "decisions_checked": len(checks),
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
