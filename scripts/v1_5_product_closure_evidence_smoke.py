#!/usr/bin/env python3
"""Verify v1.5's eight product-closure items still have evidence coverage.

This is a static, CI-safe evidence matrix. It does not prove every runtime path
by itself; it prevents the product closure spec from drifting away from the
actual implementation, smokes, and runbooks that carry the stronger evidence.
"""
from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "V1_5_EIGHT_PRODUCT_CLOSURE_SPEC.md"
RELEASE_EVIDENCE = ROOT / "scripts" / "release_evidence_packet_smoke.py"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"

SECRET_PATTERNS = [
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def exists(path: str) -> bool:
    return (ROOT / path).exists()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def has_all(text: str, markers: list[str]) -> bool:
    return all(marker in text for marker in markers)


def item(
    item_id: str,
    title: str,
    *,
    docs: list[str],
    scripts: list[str],
    source_markers: dict[str, list[str]],
) -> dict:
    failures: list[str] = []
    for path in docs:
        require(exists(path), f"{item_id} missing doc {path}", failures)
    for path in scripts:
        require(exists(path), f"{item_id} missing script {path}", failures)
    for path, markers in source_markers.items():
        if not exists(path):
            failures.append(f"{item_id} missing source {path}")
            continue
        text = read(path)
        for marker in markers:
            require(marker in text, f"{item_id} source {path} missing marker {marker!r}", failures)
    return {
        "id": item_id,
        "title": title,
        "docs": docs,
        "scripts": scripts,
        "sources": sorted(source_markers),
        "ok": not failures,
        "failures": failures,
    }


def main() -> int:
    failures: list[str] = []
    spec_text = SPEC.read_text(encoding="utf-8")
    release_text = RELEASE_EVIDENCE.read_text(encoding="utf-8")
    ci_text = CI_WORKFLOW.read_text(encoding="utf-8")

    require(SPEC.exists(), "closure spec missing", failures)
    require(has_all(spec_text, [f"### {i}. " for i in range(1, 9)]), "closure spec must keep all eight numbered items", failures)

    items = [
        item(
            "1_worker_loop",
            "Real Long-Running Agent Worker",
            docs=["docs/V1_5_AGENT_WORKER_LOOP_SPEC.md", "docs/V1_5_AGENT_WORKER_ACCEPTANCE.md"],
            scripts=[
                "scripts/agent_worker.py",
                "scripts/agentops_worker_status_smoke.py",
                "scripts/agentops_worker_daemon_cli_smoke.py",
                "scripts/worker_daemon_resilience_smoke.py",
                "scripts/worker_fleet_hygiene_smoke.py",
            ],
            source_markers={
                "server.py": ["/api/workers/status", "/api/workers/local/start", "/api/workers/local/stop"],
                "agentops_mis_cli/agentops.py": ["worker_status", "cmd_worker_preflight", "cmd_worker_hygiene"],
            },
        ),
        item(
            "2_runtime_adapter_loop",
            "OpenClaw / Hermes Adapter Loop",
            docs=["docs/HERMES_OPENCLAW_LOOP_RUNBOOK.md", "docs/REMOTE_WORKER_OPERATIONS_RUNBOOK.md"],
            scripts=[
                "scripts/agent_worker.py",
                "scripts/hermes_openclaw_loop.py",
                "scripts/hermes_openclaw_loop_smoke.py",
                "scripts/runtime_connector_trust_smoke.py",
                "scripts/worker_adapter_readiness_smoke.py",
            ],
            source_markers={
                "agentops_mis_cli/worker.py": ["--adapter", "hermes", "openclaw"],
                "server.py": ["runtime_connector_trust_blocked", "runtime-capability-manifest-v1"],
            },
        ),
        item(
            "3_cli_package",
            "Installable CLI Package",
            docs=["docs/AGENT_GATEWAY_CLI_SPEC.md", "docs/REMOTE_WORKER_OPERATIONS_RUNBOOK.md"],
            scripts=[
                "scripts/agentops",
                "scripts/install_agentops_cli.py",
                "scripts/agentops_cli_install_smoke.py",
                "scripts/agentops_pip_install_smoke.py",
                "scripts/agentops_doctor_smoke.py",
            ],
            source_markers={
                "pyproject.toml": ["agentops", "agentops-mis-cli"],
                "agentops_mis_cli/agentops.py": ["def main", "worker", "enrollment"],
            },
        ),
        item(
            "4_remote_agent_entry",
            "Remote Agent Entry Shape",
            docs=["docs/AGENT_GATEWAY_CLI_SPEC.md", "docs/REMOTE_WORKER_OPERATIONS_RUNBOOK.md"],
            scripts=[
                "scripts/remote_worker_product_acceptance.py",
                "scripts/remote_agent_token_worker_smoke.py",
                "scripts/remote_launch_packet_worker_smoke.py",
                "scripts/enrollment_policy_preview_smoke.py",
                "scripts/workspace_isolation_smoke.py",
            ],
            source_markers={
                "server.py": ["/api/agent-gateway/enrollment/create", "/api/agent-gateway/session/create", "workspace_id"],
                "agentops_mis_cli/agentops.py": ["cmd_enrollment_create", "session/create"],
            },
        ),
        item(
            "5_security_boundary",
            "MVP Security Boundary",
            docs=["docs/PUBLIC_CLAIMS_AND_LIMITATIONS.md", "docs/V1_5_AGENT_GATEWAY_HARDENING_OBJECTIVE.md"],
            scripts=[
                "scripts/redaction_policy_smoke.py",
                "scripts/redaction_fuzz_smoke.py",
                "scripts/secret_scan_smoke.py",
                "scripts/shared_mode_local_write_guard_smoke.py",
                "scripts/external_connector_runtime_inventory_smoke.py",
            ],
            source_markers={
                "server.py": ["redact", "local_ui_write_admin_auth_required", "prepared_action"],
                ".gitignore": ["agentops_mis.db", ".agentops_runtime"],
            },
        ),
        item(
            "6_ui_operation_loop",
            "UI Operation Loop",
            docs=["docs/PIXEL_OPERATING_MAP_SPEC.md", "docs/DEMO_VIDEO_SCRIPT.md"],
            scripts=[
                "scripts/operator_action_queue_ui_smoke.py",
                "scripts/ai_employees_responsiveness_smoke.py",
                "scripts/production_security_warning_ui_smoke.py",
                "scripts/real_runtime_ui_confirm_smoke.py",
            ],
            source_markers={
                "ui/start-building-app/src/app/components/pages/AIEmployees.tsx": ["operator_loop_launch_packet", "receipt_state", "Worker Fleet"],
                "ui/start-building-app/src/app/data/liveApi.ts": ["loadOperatorLoopLaunchPacket", "loadWorkerStatus"],
            },
        ),
        item(
            "7_customer_task_usefulness",
            "Customer-Task Usefulness",
            docs=["docs/AI_KNOWLEDGE_BASE_BOT_DEMO.md", "docs/CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md"],
            scripts=[
                "scripts/kb_bot_demo_smoke.py",
                "scripts/kb_bot_workflow_api_smoke.py",
                "scripts/customer_task_template_smoke.py",
                "scripts/customer_project_report_smoke.py",
                "scripts/customer_delivery_boundary_smoke.py",
            ],
            source_markers={
                "server.py": ["/api/workflows/customer-task-templates", "/api/workflows/customer-projects", "report-artifact"],
                "ui/start-building-app/src/app/components/pages/PixelOffice.tsx": ["CustomerDispatchPanel"],
                "ui/start-building-app/src/app/components/pixel/CustomerDispatchPanel.tsx": [
                    "loadCustomerTaskTemplates",
                    "runCustomerTaskTemplateWorkflow",
                    "submitCustomerTaskTemplateJob",
                ],
                "ui/start-building-app/src/app/data/liveApi.ts": [
                    "/workflows/customer-task-templates",
                    "/workflows/customer-task-templates/run",
                    "/workflows/customer-task-templates/submit",
                ],
            },
        ),
        item(
            "8_productization_track",
            "Productization Track",
            docs=[
                "docs/PRODUCT_USAGE_AND_ACTOR_MODEL.md",
                "docs/CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md",
                "docs/RELEASE_EVIDENCE_PACKET.md",
                "docs/V1_5_MERGE_READINESS_CHECKLIST.md",
            ],
            scripts=[
                "scripts/agentops_local_backup.py",
                "scripts/agentops_local_backup_smoke.py",
                "scripts/release_evidence_packet_smoke.py",
                "scripts/merge_readiness_status_smoke.py",
                "scripts/github_required_checks_smoke.py",
                "scripts/open_source_adoption_boundary_smoke.py",
            ],
            source_markers={
                "docs/V1_5_MERGE_READINESS_CHECKLIST.md": ["READY_TO_MERGE", "Backend deterministic smokes", "UI build"],
                "docs/OPEN_SOURCE_ADOPTION_BOUNDARY_SPEC.md": ["first-party AgentOps MIS code", "MIS authority"],
            },
        ),
    ]

    for row in items:
        failures.extend(row["failures"])

    command = "python3 scripts/v1_5_product_closure_evidence_smoke.py"
    require(command in release_text, "release evidence packet missing product closure evidence smoke", failures)
    require(command in ci_text, "CI workflow missing product closure evidence smoke", failures)

    output = json.dumps({"operation": "v1_5_product_closure_evidence", "ok": not failures, "items": items, "failures": failures, "safety": {"read_only": True, "ledger_mutated": False, "live_execution_performed": False, "token_omitted": True}}, ensure_ascii=False, indent=2)
    require(not any(pattern.search(output) for pattern in SECRET_PATTERNS), "evidence output leaked token-like material", failures)
    if failures:
        output = json.dumps({"operation": "v1_5_product_closure_evidence", "ok": False, "items": items, "failures": failures, "safety": {"read_only": True, "ledger_mutated": False, "live_execution_performed": False, "token_omitted": True}}, ensure_ascii=False, indent=2)
    print(output)
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
