"""Pure operator evidence-report projection helpers."""
from __future__ import annotations

from typing import Any


MEMORY_REVIEW_STATUSES = ("candidate", "approved", "rejected", "stale", "superseded")
BLOCKING_RUN_EVIDENCE_CHECK_IDS = {
    "agent_plan_bound",
    "agent_plan_verifies",
    "plan_approval_resolved",
    "plan_evidence_manifest_verified",
}


def build_operator_run_memory_review(rows: list[Any]) -> dict[str, Any]:
    items = [dict(row) for row in rows]
    status_counts = {
        status: sum(1 for row in items if row.get("review_status") == status)
        for status in MEMORY_REVIEW_STATUSES
    }
    pending_review = int(status_counts.get("candidate") or 0) + int(status_counts.get("stale") or 0)
    status = "missing" if not items else "pending_review" if pending_review else "reviewed"
    return {
        "status": status,
        "total": len(items),
        "pending_review": pending_review,
        "approved": int(status_counts.get("approved") or 0),
        "status_counts": status_counts,
        "items": items,
        "raw_content_omitted": True,
        "token_omitted": True,
    }


def operator_run_evidence_status(checks: list[dict[str, Any]]) -> dict[str, Any]:
    failed = [check for check in checks if not check.get("ok")]
    blocked = any(str(check.get("id") or "") in BLOCKING_RUN_EVIDENCE_CHECK_IDS for check in failed)
    return {
        "status": "blocked" if blocked else "attention" if failed else "ready",
        "failed": failed,
        "failed_check_ids": [check.get("id") for check in failed],
        "blocking_check_ids": [
            check.get("id")
            for check in failed
            if str(check.get("id") or "") in BLOCKING_RUN_EVIDENCE_CHECK_IDS
        ],
        "token_omitted": True,
    }


def operator_evidence_report_summary(items: list[dict[str, Any]], receipt_summary: dict[str, Any]) -> dict[str, Any]:
    plan_quality_items = [
        (item.get("agent_plan") or {}).get("quality") or {}
        for item in items
        if ((item.get("agent_plan") or {}).get("quality") or {}).get("status")
    ]
    plan_quality_scores = [
        int(item.get("score") or 0)
        for item in plan_quality_items
        if item.get("score") is not None
    ]
    return {
        "runs": len(items),
        "ready": sum(1 for item in items if item.get("status") == "ready"),
        "attention": sum(1 for item in items if item.get("status") == "attention"),
        "blocked": sum(1 for item in items if item.get("status") == "blocked"),
        "agent_plan_quality_ready": sum(1 for item in plan_quality_items if item.get("status") == "ready"),
        "agent_plan_quality_attention": sum(1 for item in plan_quality_items if item.get("status") == "attention"),
        "agent_plan_quality_blocked": sum(1 for item in plan_quality_items if item.get("status") == "blocked"),
        "agent_plan_quality_min_score": min(plan_quality_scores) if plan_quality_scores else None,
        "agent_plan_quality_avg_score": round(sum(plan_quality_scores) / len(plan_quality_scores), 2) if plan_quality_scores else None,
        "verified_plan_evidence_manifests": sum(
            1 for item in items if (item.get("plan_evidence_manifest") or {}).get("verification_pass")
        ),
        "missing_plan_evidence_manifests": sum(
            1 for item in items if not (item.get("plan_evidence_manifest") or {}).get("manifest_id")
        ),
        "pending_approvals": sum(int((item.get("approvals") or {}).get("pending") or 0) for item in items),
        "memory_reviews": sum(int((item.get("memory_review") or {}).get("total") or 0) for item in items),
        "memory_review_ready": sum(
            1 for item in items if (item.get("memory_review") or {}).get("status") == "reviewed"
        ),
        "missing_memory_reviews": sum(
            1 for item in items if (item.get("memory_review") or {}).get("status") == "missing"
        ),
        "pending_memory_reviews": sum(
            int((item.get("memory_review") or {}).get("pending_review") or 0) for item in items
        ),
        "worker_runs": sum(
            1 for item in items if (item.get("worker_knowledge_retrieval") or {}).get("applicable")
        ),
        "worker_knowledge_retrieval_ready": sum(
            1 for item in items if (item.get("worker_knowledge_retrieval") or {}).get("status") == "ready"
        ),
        "worker_knowledge_retrieval_missing": sum(
            1 for item in items if (item.get("worker_knowledge_retrieval") or {}).get("status") == "missing"
        ),
        "worker_knowledge_retrieval_unavailable": sum(
            1 for item in items if (item.get("worker_knowledge_retrieval") or {}).get("status") == "unavailable"
        ),
        "worker_runtime_summary_ready": sum(
            1 for item in items if (item.get("worker_runtime_summary") or {}).get("status") == "ready"
        ),
        "worker_runtime_summary_missing": sum(
            1 for item in items if (item.get("worker_runtime_summary") or {}).get("status") == "missing"
        ),
        "approval_required_plans": sum(1 for item in items if (item.get("agent_plan") or {}).get("approval_required")),
        "approved_required_plans": sum(
            1
            for item in items
            if (item.get("agent_plan") or {}).get("approval_required")
            and (item.get("agent_plan") or {}).get("approval_decision") == "approved"
        ),
        "action_receipts": int(receipt_summary.get("receipts") or 0),
        "verified_action_receipts": int(receipt_summary.get("verified") or 0),
        "evaluated_action_receipts": int(receipt_summary.get("evaluated") or 0),
    }


def operator_evidence_report_status(summary: dict[str, Any]) -> str:
    if int(summary.get("blocked") or 0):
        return "blocked"
    if (
        int(summary.get("attention") or 0)
        or int(summary.get("pending_approvals") or 0)
        or int(summary.get("missing_memory_reviews") or 0)
        or int(summary.get("pending_memory_reviews") or 0)
        or int(summary.get("worker_knowledge_retrieval_missing") or 0)
        or int(summary.get("worker_knowledge_retrieval_unavailable") or 0)
        or int(summary.get("worker_runtime_summary_missing") or 0)
    ):
        return "attention"
    return "ready"
