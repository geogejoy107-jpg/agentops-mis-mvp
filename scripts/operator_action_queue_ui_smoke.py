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
    "loop_action_package_source": "operatorLoopAudit?.action_package",
    "loop_action_package_items": "loopActionPackageItems",
    "loop_work_order_label_en": 'loopWorkOrderTitle: "Loop work order"',
    "loop_work_order_label_zh": 'loopWorkOrderTitle: "Loop 执行包"',
    "loop_work_order_summary_en": 'loopWorkOrderSummary: "Copy the next gate action',
    "loop_work_order_summary_zh": 'loopWorkOrderSummary: "从 loop action package',
    "loop_action_package_action_copy": "copyIntakeCommand(item.action_command)",
    "loop_action_package_verify_copy": "copyIntakeCommand(item.verify_command)",
    "loop_action_package_receipt_copy": "copyIntakeCommand(item.receipt_record_command)",
    "loop_action_package_verify_receipt_copy": "copyIntakeCommand(item.receipt_verify_record_command)",
    "operator_handoff_loader": "loadOperatorHandoff(12, scopedLoopId)",
    "operator_health_loader": "loadOperatorHealth(12, scopedLoopId)",
    "operator_health_data": "operatorHealth",
    "operator_health_label_en": 'operatorHealthTitle: "Operator health"',
    "operator_health_label_zh": 'operatorHealthTitle: "Operator 健康"',
    "operator_health_summary_en": 'operatorHealthSummary: "Aggregate read-only health',
    "operator_health_summary_zh": 'operatorHealthSummary: "聚合 Loop 交接',
    "operator_health_score_label_en": 'healthScore: "Health score"',
    "operator_health_score_label_zh": 'healthScore: "健康分"',
    "operator_health_risks_label_en": 'healthRisks: "Health risks"',
    "operator_health_risks_label_zh": 'healthRisks: "健康风险"',
    "operator_health_score_render": "operatorHealth?.score ?? 0",
    "operator_health_risk_queue_source": 'item.lane === "operator_health"',
    "operator_health_risk_source_label": "copy.operatorHealthTitle : copy.operatorTitle",
    "operator_health_risk_backend_receipt": "receiptRecordCommand: item.receipt_record_command",
    "operator_health_risk_backend_verify_receipt": "receiptVerifyRecordCommand: item.receipt_verify_record_command",
    "operator_health_risk_sort": "candidate.isOperatorHealthRisk ? 118",
    "receipt_evaluation_label_en": 'receiptEvaluation: "Receipt eval"',
    "receipt_evaluation_label_zh": 'receiptEvaluation: "收据评估"',
    "receipt_evaluation_queue_field": "receiptEvaluation: item.receipt_evaluation",
    "receipt_evaluation_queue_status": "queueReceiptEvaluationStatus",
    "receipt_evaluation_recovery_sort": "candidate.isReceiptEvaluationRecovery ? 116",
    "receipt_evaluation_coverage_render": "operatorReceiptCoverage.evaluation_coverage_percent",
    "receipt_failure_memory_label_en": 'receiptFailureMemoryTitle: "Receipt failure memory"',
    "receipt_failure_memory_label_zh": 'receiptFailureMemoryTitle: "失败收据记忆"',
    "receipt_failure_memory_source": "receiptFailureMemoryRaw",
    "receipt_failure_memory_handoff": "operatorHandoff?.receipt_state.failure_memory",
    "receipt_failure_memory_plan": "operatorActionPlan?.receipt_failure_memory",
    "receipt_failure_memory_candidate_count": "receiptFailureMemoryCandidateCount",
    "receipt_failure_memory_next_action": "receiptFailureMemoryNextAction",
    "receipt_failure_memory_copy": "copyIntakeCommand(receiptFailureMemoryNextAction)",
    "receipt_failure_memory_api_import": "proposeReceiptFailureMemory",
    "receipt_failure_memory_handler": "handleReceiptFailureMemory",
    "receipt_failure_memory_preview_call": "handleReceiptFailureMemory(false)",
    "receipt_failure_memory_confirm_call": "handleReceiptFailureMemory(true)",
    "receipt_failure_memory_confirm_label_en": 'createFailureMemory: "Create candidate"',
    "receipt_failure_memory_confirm_label_zh": 'createFailureMemory: "创建候选"',
    "receipt_failure_memory_preview_label_en": 'previewFailureMemory: "Preview memory"',
    "receipt_failure_memory_preview_label_zh": 'previewFailureMemory: "预览记忆"',
    "receipt_failure_memory_result": "receiptFailureMemoryResult",
    "receipt_failure_memory_action_flag": 'isReceiptFailureMemoryRecovery: item.source === "receipt_failure_memory"',
    "receipt_failure_memory_sort": "candidate.isReceiptFailureMemoryRecovery ? 114",
    "receipt_failure_memory_summary_render": "failure memory ${operatorPlanSummary.receipt_failure_memory_candidates}",
    "operator_handoff_data": "operatorHandoff",
    "operator_handoff_label_en": 'operatorHandoffTitle: "Operator handoff"',
    "operator_handoff_label_zh": 'operatorHandoffTitle: "Operator 交接包"',
    "operator_handoff_summary_en": 'operatorHandoffSummary: "Read-only handoff package',
    "operator_handoff_summary_zh": 'operatorHandoffSummary: "给 Hermes、OpenClaw、Codex',
    "operator_handoff_commands": "operatorHandoff?.work_order?.commands",
    "operator_handoff_loop_self_check_command": "loopSelfCheckCommand",
    "operator_handoff_loop_self_check_label_en": 'loopSelfCheckTitle: "Pre-advance check"',
    "operator_handoff_loop_self_check_label_zh": 'loopSelfCheckTitle: "推进前自检"',
    "operator_handoff_loop_self_check_copy": "copyIntakeCommand(loopSelfCheckCommand)",
    "operator_handoff_advance_loop_source": "operatorHandoff?.work_order?.advance_loop",
    "operator_handoff_advance_loop_label_en": 'advanceLoopTitle: "Bounded advance"',
    "operator_handoff_advance_loop_label_zh": 'advanceLoopTitle: "受限推进"',
    "operator_handoff_advance_loop_preview": "advanceLoopPreviewCommand",
    "operator_handoff_advance_loop_confirm": "advanceLoopConfirmCommand",
    "operator_handoff_advance_loop_copy_preview": "copyIntakeCommand(advanceLoopPreviewCommand)",
    "operator_handoff_advance_loop_copy_confirm": "copyIntakeCommand(advanceLoopConfirmCommand)",
    "operator_handoff_advance_loop_policy": "advanceLoopPolicy",
    "operator_handoff_advance_loop_policy_label_en": 'advanceLoopPolicyLabel: "Policy"',
    "operator_handoff_advance_loop_policy_label_zh": 'advanceLoopPolicyLabel: "策略"',
    "operator_handoff_advance_loop_policy_id": "advanceLoopPolicyId",
    "operator_handoff_advance_loop_policy_version": "advanceLoopPolicyVersion",
    "operator_handoff_sources": "operatorHandoffSources",
    "operator_handoff_receipt_state": "operatorHandoff.receipt_state.coverage",
    "operator_handoff_review_state": "operatorHandoff.review_state.loop_record",
    "operator_handoff_loop_health_json": "loop_health: operatorHandoff.loop_health",
    "operator_handoff_loop_health_label_en": 'loopHealth: "Loop health"',
    "operator_handoff_loop_health_label_zh": 'loopHealth: "Loop 健康"',
    "operator_handoff_loop_risks_label_en": 'loopRisks: "Risks"',
    "operator_handoff_loop_risks_label_zh": 'loopRisks: "风险"',
    "operator_handoff_loop_health_score": "operatorHandoff.loop_health?.score",
    "operator_handoff_loop_health_next_action": "operatorHandoff.loop_health?.next_action",
    "operator_handoff_auth_boundary_en": 'authBoundary: "Auth boundary"',
    "operator_handoff_auth_boundary_zh": 'authBoundary: "认证边界"',
    "operator_handoff_auth_json": "auth: operatorHandoff.auth",
    "operator_handoff_auth_render": "operatorHandoff.auth?.required_scope",
    "operator_handoff_loop_health_json": "loop_health: operatorHandoff.loop_health",
    "operator_handoff_loop_health_en": 'loopHealth: "Loop health"',
    "operator_handoff_loop_health_zh": 'loopHealth: "Loop 健康"',
    "operator_handoff_loop_risks": "operatorHandoff.loop_health?.risks?.length",
    "operator_handoff_json_copy": "copyIntakeCommand(operatorHandoffJson)",
    "operator_handoff_command_copy": "copyIntakeCommand(handoffCommand)",
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
    "copy_receipt_cli_label_en": 'copyReceiptCommand: "Copy receipt CLI"',
    "copy_receipt_cli_label_zh": 'copyReceiptCommand: "复制记账 CLI"',
    "copy_verify_receipt_cli_label_en": 'copyVerifyReceiptCommand: "Copy verify CLI"',
    "copy_verify_receipt_cli_label_zh": 'copyVerifyReceiptCommand: "复制验收 CLI"',
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
    "backend_receipt_required": "receiptRequired: item.receipt_required",
    "backend_verify_command": "verifyAction: item.verify_command",
    "backend_receipt_record_command": "receiptRecordCommand: item.receipt_record_command",
    "backend_receipt_record_confirm_command": "receiptRecordConfirmCommand: item.receipt_record_confirm_command",
    "backend_receipt_verify_record_command": "receiptVerifyRecordCommand: item.receipt_verify_record_command",
    "copy_receipt_record_command": "copyIntakeCommand(receiptRecordCommand)",
    "copy_receipt_verify_record_command": "copyIntakeCommand(receiptVerifyRecordCommand)",
    "render_copy_receipt_cli": "copy.copyReceiptCommand",
    "render_copy_verify_receipt_cli": "copy.copyVerifyReceiptCommand",
    "receipt_coverage_recovery_flag": 'isReceiptCoverageRecovery: item.source === "receipt_coverage"',
    "receipt_coverage_recovery_sort": "candidate.isReceiptCoverageRecovery ? 115",
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
