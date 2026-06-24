#!/usr/bin/env python3
"""Verify approval wording separates generic ledger decisions from exact prepared-action resume."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_DOC = ROOT / "docs" / "APPROVAL_SEMANTICS_BOUNDARY.md"
PROJECT_SPEC = ROOT / "PROJECT_SPEC.md"
README = ROOT / "README.md"
CHECKLIST = ROOT / "docs" / "V1_5_MERGE_READINESS_CHECKLIST.md"
APPROVALS_INBOX = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "ApprovalsInbox.tsx"
WORKSPACE_HOME = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "WorkspaceHome.tsx"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def compact(text: str) -> str:
    return " ".join(text.split())


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    paths = [BOUNDARY_DOC, PROJECT_SPEC, README, CHECKLIST, APPROVALS_INBOX, WORKSPACE_HOME]
    for path in paths:
        require(path.exists(), f"missing required file: {path.relative_to(ROOT)}", failures)

    boundary = read(BOUNDARY_DOC) if BOUNDARY_DOC.exists() else ""
    project_spec = read(PROJECT_SPEC)
    readme = read(README)
    checklist = read(CHECKLIST)
    approvals_ui = read(APPROVALS_INBOX)
    home_ui = read(WORKSPACE_HOME)

    required_boundary_phrases = [
        "Ledger / Delivery / Review Approval",
        "Prepared-Action Approval",
        "does not by itself prove that an exact provider side effect executed",
        "must not be described as exact tool-action resume",
        "Approving this gate authorizes a later exact resume",
        "still does not perform the side effect directly",
        "Every approval in the UI resumes the exact tool action",
    ]
    boundary_compact = compact(boundary)
    for phrase in required_boundary_phrases:
        require(phrase in boundary_compact, f"boundary doc missing phrase: {phrase}", failures)

    require("docs/APPROVAL_SEMANTICS_BOUNDARY.md" in project_spec, "PROJECT_SPEC does not link approval semantics boundary", failures)
    project_compact = compact(project_spec)
    require("generic approvals are ledger/delivery/review decisions" in project_compact, "PROJECT_SPEC missing generic approval wording", failures)
    require("exact tool-action resume is valid only" in project_compact, "PROJECT_SPEC missing prepared-action-only wording", failures)

    require("普通审批是账本/交付/审核决策" in readme, "README missing Chinese generic approval boundary", failures)
    require("prepared_action" in readme and "单独 resume" in readme, "README missing prepared-action separate-resume wording", failures)

    require("Existing approval is described as ledger/delivery approval" in checklist and "[x]" in checklist, "checklist did not close ledger/delivery approval item", failures)
    require("UI/docs do not claim exact tool-action resume" in checklist and "[x]" in checklist, "checklist did not close UI/docs exact-resume item", failures)

    ui_required = [
        "Generic approvals are ledger, delivery, enrollment, review, or plan decisions",
        "Exact tool-action resume only applies to prepared actions",
        "普通审批是账本、交付、接入、审核或计划决策",
        "prepared action",
        "Ledger/delivery decisions; exact tool-action resume is shown only for prepared actions.",
    ]
    ui_bundle = f"{approvals_ui}\n{home_ui}"
    for phrase in ui_required:
        require(phrase in ui_bundle, f"UI missing approval semantics phrase: {phrase}", failures)

    misleading_patterns = [
        re.compile(r"approve[^\n]{0,80}(executes?|resumes?|performs?)\b", re.IGNORECASE),
        re.compile(r"approval[^\n]{0,80}(executes?|resumes?|performs?)\b", re.IGNORECASE),
        re.compile(r"批准[^\n]{0,40}(执行|恢复)"),
        re.compile(r"审批[^\n]{0,40}(自动执行|直接执行|自动恢复)"),
    ]
    allowed_context_markers = ("prepared_action", "prepared action", "action hash", "action_hash", "prepared-action", "exact resume", "approval wall")
    for path in [README, PROJECT_SPEC, CHECKLIST, APPROVALS_INBOX, WORKSPACE_HOME]:
        lines = read(path).splitlines()
        for pattern in misleading_patterns:
            for line_no, line in enumerate(lines, start=1):
                hit = pattern.search(line)
                if hit and not any(marker in line.lower() for marker in allowed_context_markers):
                    failures.append(f"misleading generic approval wording in {path.relative_to(ROOT)}:{line_no}: {hit.group(0)}")

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search("\n".join(read(path) for path in paths if path.exists()))]
    require(not secret_hits, f"secret-like marker found in approval boundary files: {secret_hits}", failures)

    output = {
        "ok": not failures,
        "operation": "approval_semantics_boundary_smoke",
        "files": [str(path.relative_to(ROOT)) for path in paths],
        "contract": "Generic approvals are ledger/delivery/review decisions; exact resume claims are limited to prepared-action contexts.",
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
