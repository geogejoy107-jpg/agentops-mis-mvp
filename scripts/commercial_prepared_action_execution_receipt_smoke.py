#!/usr/bin/env python3
"""Verify post-action receipts require and read back consumed prepared actions."""
from __future__ import annotations

import json
import os
import re
import shlex
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from commercial_receipt_prepared_action_binding_smoke import (
    CI_WORKFLOW,
    INDEX,
    RELEASE_PACKET,
    ROOT,
    SECRET_PATTERNS,
    db_counts,
    http_json,
    leaked_secret,
    require,
    run_cli,
    wait_ready,
)


ACCEPTANCE = ROOT / "docs" / "COMMERCIAL_PREPARED_ACTION_EXECUTION_RECEIPT_ACCEPTANCE.md"
COMMAND = "python3 scripts/commercial_prepared_action_execution_receipt_smoke.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def validate_wiring(failures: list[str]) -> None:
    docs = {
        "index": read(INDEX),
        "release": read(RELEASE_PACKET),
        "ci": read(CI_WORKFLOW),
        "acceptance": read(ACCEPTANCE),
    }
    require("Prepared Action Execution Receipt" in docs["index"], "index missing prepared-action execution receipt row", failures)
    require(COMMAND in docs["index"], "index missing prepared-action execution receipt command", failures)
    require(COMMAND in docs["release"], "release packet missing prepared-action execution receipt command", failures)
    require(COMMAND in docs["ci"], "CI workflow missing prepared-action execution receipt command", failures)
    require(COMMAND in docs["acceptance"], "acceptance missing prepared-action execution receipt command", failures)
    joined = "\n".join(docs.values())
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(joined)]
    require(not secret_hits, f"secret-like marker found in execution receipt docs: {secret_hits}", failures)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def execution_command(action_id: str, action_hash: str, side_effect_id: str) -> str:
    parts = [
        "agentops",
        "approval",
        "prepared-action",
        "resume",
        "--action-id",
        action_id,
        "--expected-action-hash",
        action_hash,
        "--provider-side-effect-id",
        side_effect_id,
    ]
    return " ".join(shlex.quote(part) for part in parts)


def main() -> int:
    failures: list[str] = []
    validate_wiring(failures)
    outputs: list[str] = []
    recorded_receipt: dict = {}

    with tempfile.TemporaryDirectory(prefix="agentops-commercial-execution-receipt-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_BASE_URL"] = base_url
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env.pop("AGENTOPS_API_KEY", None)
        proc = subprocess.Popen(
            [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_ready(base_url, proc)
            stamp = time.strftime("%Y%m%d%H%M%S")
            task_id = f"tsk_commercial_execution_receipt_{stamp}"
            agent_id = "agt_research"
            side_effect_id = f"mock-commercial-side-effect-{stamp}"
            status, task_payload = http_json(base_url, "/api/tasks", {
                "task_id": task_id,
                "workspace_id": "local-demo",
                "title": f"Commercial prepared-action execution receipt smoke {stamp}",
                "description": "Require a consumed prepared action before recording an execution receipt.",
                "owner_agent_id": agent_id,
                "risk_level": "high",
                "acceptance_criteria": "Pre-consumption receipt fails closed, resume consumes exactly once, and receipt records side-effect readback.",
            })
            outputs.append(json.dumps(task_payload, ensure_ascii=False))
            require(status in {200, 201}, f"task create failed: {status} {task_payload}", failures)

            status, run_payload = http_json(base_url, "/api/mock-runs/start", {"task_id": task_id, "agent_id": agent_id})
            outputs.append(json.dumps(run_payload, ensure_ascii=False))
            require(status == 201, f"mock run start failed: {status} {run_payload}", failures)
            run_id = (run_payload.get("run") or {}).get("run_id") or run_payload.get("run_id")
            require(bool(run_id), f"run_id missing: {run_payload}", failures)

            prepare_status, prepare_payload = http_json(base_url, "/api/agent-gateway/prepared-actions", {
                "workspace_id": "local-demo",
                "run_id": run_id,
                "agent_id": agent_id,
                "requested_by_agent_id": agent_id,
                "action_type": "commercial.execute_reviewed_action",
                "args": {
                    "risk_category": "live_external_side_effect",
                    "target_resource": "commercial_config.external_side_effect",
                    "action_execution_allowed": False,
                },
                "target_resource": "commercial://external_side_effect",
                "risk_level": "high",
                "checkpoint": {"checkpoint": "before_commercial_external_side_effect", "raw_payload_stored": False},
                "idempotency_key": f"commercial-execution-receipt-{stamp}",
                "reason": "Execution receipt must prove this exact prepared action was consumed before post-action evidence is recorded.",
            })
            outputs.append(json.dumps(prepare_payload, ensure_ascii=False))
            require(prepare_status in {200, 201}, f"prepared action create failed: {prepare_status} {prepare_payload}", failures)
            prepared_action = prepare_payload.get("prepared_action") or {}
            approval = prepare_payload.get("approval") or {}
            prepared_action_id = str(prepared_action.get("action_id") or "")
            prepared_action_hash = str(prepared_action.get("action_hash") or "")
            approval_id = str(approval.get("approval_id") or "")
            require(bool(prepared_action_id and prepared_action_hash and approval_id), f"prepared action fields missing: {prepare_payload}", failures)

            before = db_counts(db_path)
            pre_status, pre_payload = http_json(base_url, "/api/operator/action-receipts", {
                "workspace_id": "local-demo",
                "actor_id": "usr_founder",
                "action_command": execution_command(prepared_action_id, prepared_action_hash, side_effect_id),
                "verify_command": "agentops approval prepared-action get --action-id " + shlex.quote(prepared_action_id),
                "prepared_action_id": prepared_action_id,
                "prepared_action_hash": prepared_action_hash,
                "required_prepared_action_status": "consumed",
                "source": "commercial.prepared_action_execution_receipt.pre_consumed_probe",
                "status": "verified",
                "result_summary": "This pre-consumption receipt must fail closed.",
            })
            outputs.append(json.dumps(pre_payload, ensure_ascii=False))
            after_pre = db_counts(db_path)
            require(pre_status == 409, f"pre-consumed receipt should fail with 409: {pre_status} {pre_payload}", failures)
            require(pre_payload.get("error") == "prepared_action_status_required", f"wrong pre-consumed error: {pre_payload}", failures)
            require(after_pre == before, f"pre-consumed receipt changed ledger counts: {before} -> {after_pre}", failures)

            code, approve_payload, raw = run_cli(env, "approval", "approve", "--approval-id", approval_id)
            outputs.append(raw)
            require(code == 0, f"approval approve failed: {raw}", failures)
            require((approve_payload.get("prepared_action") or {}).get("status") == "approved", f"prepared action not approved: {approve_payload}", failures)

            code, resume_payload, raw = run_cli(
                env,
                "approval",
                "prepared-action",
                "resume",
                "--action-id",
                prepared_action_id,
                "--agent-id",
                agent_id,
                "--provider-side-effect-id",
                side_effect_id,
                "--result-summary",
                "Mock commercial side effect recorded after exact approval; no live external call performed.",
            )
            outputs.append(raw)
            require(code == 0, f"prepared action resume failed: {raw}", failures)
            resumed = resume_payload.get("prepared_action") or {}
            require(resume_payload.get("execute_once") is True, f"execute_once missing: {resume_payload}", failures)
            require(resumed.get("status") == "consumed", f"prepared action not consumed: {resume_payload}", failures)
            require(resumed.get("provider_side_effect_id") == side_effect_id, f"side effect id mismatch: {resume_payload}", failures)
            require((resume_payload.get("hash_verification") or {}).get("match") is True, f"resume hash verification missing: {resume_payload}", failures)

            code, confirmed, raw = run_cli(
                env,
                "operator",
                "record-action-receipt",
                "--action-command",
                execution_command(prepared_action_id, prepared_action_hash, side_effect_id),
                "--verify-command",
                "agentops approval prepared-action get --action-id " + shlex.quote(prepared_action_id),
                "--action-id",
                "commercial_external_side_effect_execution",
                "--action-signature",
                "prepared_action_execution_receipt_v1:live_external_side_effect",
                "--prepared-action-id",
                prepared_action_id,
                "--prepared-action-hash",
                prepared_action_hash,
                "--required-prepared-action-status",
                "consumed",
                "--source",
                "commercial.prepared_action_execution_receipt",
                "--status",
                "verified",
                "--result-summary",
                "Post-action receipt recorded against consumed prepared action hash; no live external call performed by receipt CLI.",
                "--confirm-record",
            )
            outputs.append(raw)
            after_confirm = db_counts(db_path)
            require(code == 0, f"confirmed execution receipt CLI failed: {code} {raw}", failures)
            receipt = confirmed.get("receipt") or {}
            evaluation = confirmed.get("evaluation") or {}
            require(receipt.get("prepared_action_id") == prepared_action_id, f"receipt missing prepared action id: {receipt}", failures)
            require(receipt.get("prepared_action_hash") == prepared_action_hash, f"receipt prepared action hash mismatch: {receipt}", failures)
            require(receipt.get("required_prepared_action_status") == "consumed", f"receipt missing required status: {receipt}", failures)
            require(receipt.get("prepared_action_status") == "consumed", f"receipt did not read consumed status: {receipt}", failures)
            require(receipt.get("prepared_action_consumed") is True, f"receipt consumed flag missing: {receipt}", failures)
            require(receipt.get("prepared_action_approved") is True, f"receipt approved flag missing: {receipt}", failures)
            require(receipt.get("prepared_action_provider_side_effect_id") == side_effect_id, f"receipt side-effect id mismatch: {receipt}", failures)
            require(evaluation.get("pass_fail") == "pass", f"verified receipt evaluation should pass: {evaluation}", failures)
            for key in after_confirm:
                require(after_confirm[key] == after_pre[key] + 1, f"{key} count mismatch: {after_pre} -> {after_confirm}", failures)
            recorded_receipt = {
                "receipt_id": receipt.get("receipt_id"),
                "prepared_action_id": receipt.get("prepared_action_id"),
                "prepared_action_hash_match": receipt.get("prepared_action_hash_match"),
                "prepared_action_status": receipt.get("prepared_action_status"),
                "prepared_action_provider_side_effect_id": receipt.get("prepared_action_provider_side_effect_id"),
                "evaluation_id": evaluation.get("evaluation_id"),
            }
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

    output = {
        "operation": "commercial_prepared_action_execution_receipt_smoke",
        "ok": not failures,
        "recorded_receipt": recorded_receipt,
        "safety": {
            "isolated_temp_db": True,
            "default_db_touched": False,
            "server_started": True,
            "ledger_mutated": True,
            "ledger_mutation_scope": "isolated_temp_sqlite_only",
            "billing_call_performed": False,
            "cleanup_execution_performed": False,
            "hosted_migration_performed": False,
            "postgres_cutover_performed": False,
            "live_execution_performed": False,
            "action_command_executed_by_receipt_cli": False,
            "prepared_action_resumed_once": bool(recorded_receipt),
            "prepared_action_consumed_required": True,
            "raw_logs_omitted": True,
            "raw_prompts_omitted": True,
            "raw_responses_omitted": True,
            "token_omitted": True,
        },
        "failure_count": len(failures),
        "failures": failures,
    }
    rendered = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    if leaked_secret(rendered) or leaked_secret("\n".join(outputs)):
        output["ok"] = False
        output["failure_count"] += 1
        output["failures"].append("secret-like marker leaked in prepared-action execution receipt smoke output")
        rendered = json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    return 1 if output["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
