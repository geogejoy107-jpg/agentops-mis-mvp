#!/usr/bin/env python3
"""Verify the Workspace Agents operator action queue UI contract."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AI_EMPLOYEES = ROOT / "ui" / "start-building-app" / "src" / "app" / "components" / "pages" / "AIEmployees.tsx"


SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


EXPECTED_MARKERS = {
    "loop_first_issue_recovery": "loop-first-issue:",
    "loop_first_issue_verify": "verifyAction: loopAuditNextAction",
    "close_gap_verify": 'isCloseEvidenceGapCommand(item.command) ? "agentops operator action-plan --limit 20"',
    "fleet_verify": 'verifyAction: "agentops worker status"',
    "integration_inbox_verify": 'verifyAction: "agentops commander inbox --limit 5"',
    "synthesis_verify": 'verifyAction: "agentops commander board --limit 20"',
    "local_readiness_verify": 'verifyAction: "agentops local readiness"',
    "verify_label_en": 'verifyAfterAction: "Verify"',
    "verify_label_zh": 'verifyAfterAction: "验收"',
    "verify_render": "{copy.verifyAfterAction}: {item.verifyAction}",
    "verify_copy_button": "copyIntakeCommand(item.verifyAction)",
    "receipt_loader": "loadOperatorActionReceipts(8)",
    "receipt_writer": "recordOperatorActionReceipt({",
    "record_action_label_en": 'recordActionReceipt: "Record"',
    "record_action_label_zh": 'recordActionReceipt: "记账"',
    "verify_receipt_label_en": 'recordVerifyReceipt: "Verify receipt"',
    "verify_receipt_label_zh": 'recordVerifyReceipt: "验收记账"',
    "receipt_summary": "operatorActionReceipts.summary.receipts",
    "receipt_proof_label_en": 'receiptProof: "Receipt"',
    "receipt_proof_label_zh": 'receiptProof: "收据证明"',
    "receipt_needed_label_en": 'receiptNeeded: "Needs receipt"',
    "receipt_needed_label_zh": 'receiptNeeded: "需验收收据"',
    "receipt_matcher": "latestReceiptForAction",
    "receipt_no_verify_only_match": "wantedAction === String(receipt.action_command",
    "receipt_signature_match": "wantedSignature === String(receipt.action_signature",
    "receipt_short_hash": "receiptShortHash",
    "backend_receipt_status": "receiptStatus: item.receipt_status",
    "backend_action_signature": "actionSignature: item.action_signature",
    "receipt_signature_writer": "action_signature:",
    "backend_receipt_verified": "receiptVerified: item.receipt_verified",
    "backend_verify_command": "verifyAction: item.verify_command",
    "receipt_coverage_source": "operatorReceiptCoverage",
    "receipt_coverage_display": "receipt coverage",
    "receipt_coverage_verified_required": "operatorReceiptCoverage.verified}/${operatorReceiptCoverage.required",
    "receipt_coverage_stale_missing": "operatorReceiptCoverage.stale} · missing ${operatorReceiptCoverage.missing",
    "verified_receipt_sort": "!candidateReceiptVerified(candidate) ? 80",
    "receipt_sensitive_queue_key": "actionReceiptKey",
    "queue_receipt_display": "{copy.receiptProof}: {queueReceiptStatus}",
    "queue_receipt_needed_display": "{copy.receiptNeeded}: {verifyAction || item.action}",
    "loop_receipt_display": "{copy.receiptProof}: {stepReceipt.status}",
    "recorded_receipt_status": 'recordActionQueueReceipt(item, "recorded")',
    "verified_receipt_status": 'recordActionQueueReceipt(item, "verified")',
}


def main() -> int:
    source = AI_EMPLOYEES.read_text(encoding="utf-8")
    failures: list[str] = []

    for label, marker in EXPECTED_MARKERS.items():
        if marker not in source:
            failures.append(f"missing {label}: {marker}")

    queue_index = source.find("const actionQueueCandidates")
    verify_render_index = source.find("{copy.verifyAfterAction}: {item.verifyAction}")
    if queue_index < 0:
        failures.append("operator action queue candidate block missing")
    if verify_render_index < 0:
        failures.append("operator action queue verify render block missing")
    if queue_index >= 0 and verify_render_index >= 0 and verify_render_index < queue_index:
        failures.append("verify render appears before queue candidate construction")

    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(source)]
    if secret_hits:
        failures.append(f"secret-like pattern found in UI source: {secret_hits}")

    result = {
        "ok": not failures,
        "operation": "operator_action_queue_ui_contract",
        "file": str(AI_EMPLOYEES.relative_to(ROOT)),
        "markers_checked": len(EXPECTED_MARKERS),
        "failures": failures,
        "safety": {
            "read_only": True,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
