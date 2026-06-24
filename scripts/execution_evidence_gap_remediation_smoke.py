#!/usr/bin/env python3
"""Verify execution-evidence gaps can become Commander remediation packages."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
DEFAULT_DB = Path(os.environ.get("AGENTOPS_DB_PATH") or (ROOT / "agentops_mis.db"))
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


def http_json(base_url: str, method: str, path: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urlopen(req, timeout=60) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def run_cli(base_url: str, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "--base-url", base_url, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def run_agentops_command(base_url: str, command: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    parts = shlex.split(command)
    if parts and parts[0] == "agentops":
        parts = parts[1:]
    return run_cli(base_url, parts, env)


def command_center_workflow_item(base_url: str, run_id: str, step_id: str, outputs: list[str], failures: list[str]) -> tuple[dict, dict]:
    status, payload = http_json(base_url, "GET", "/api/operator/command-center?limit=20&refresh_cache=true")
    outputs.append(json.dumps(payload, ensure_ascii=False))
    require(status == 200, f"command-center readback failed: {status} {payload}", failures)
    workflow = payload.get("evidence_remediation_workflow") or {}
    item = next((
        row for row in workflow.get("items") or []
        if row.get("run_id") == run_id and row.get("step_id") == step_id
    ), {})
    return item, payload


def handoff_remediation_item(base_url: str, run_id: str, env: dict[str, str], outputs: list[str]) -> tuple[dict, dict]:
    handoff = run_cli(base_url, ["operator", "handoff", "--limit", "12"], env)
    outputs.extend([handoff.stdout, handoff.stderr])
    payload = load_json(handoff)
    items = ((((payload.get("work_order") or {}).get("evidence_report") or {}).get("remediation_chain") or {}).get("items") or [])
    item = next((row for row in items if row.get("run_id") == run_id), {})
    return item, payload


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def db_fingerprint(db_path: Path) -> dict | None:
    if not db_path.exists():
        return None
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        result = {}
        for table, timestamp_col in [
            ("tasks", "updated_at"),
            ("runs", "created_at"),
            ("runtime_events", "created_at"),
            ("audit_logs", "created_at"),
            ("agent_plans", "updated_at"),
            ("plan_evidence_manifests", "updated_at"),
        ]:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if not exists:
                continue
            row = conn.execute(f"SELECT COUNT(*) AS count, COALESCE(MAX({timestamp_col}), '') AS max_ts FROM {table}").fetchone()
            result[table] = {"count": int(row["count"] or 0), "max_ts": row["max_ts"] or ""}
        return result
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify execution-evidence gap remediation packages.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--db-path", default=str(DEFAULT_DB))
    args = parser.parse_args()

    failures: list[str] = []
    outputs: list[str] = []
    db_path = Path(args.db_path)
    before = db_fingerprint(db_path)

    status, action_plan = http_json(args.base_url, "GET", "/api/operator/action-plan?limit=20")
    outputs.append(json.dumps(action_plan, ensure_ascii=False))
    require(status == 200, f"action-plan failed: {status} {action_plan}", failures)
    gaps = [item for item in (action_plan.get("execution_evidence") or {}).get("gaps") or [] if item.get("run_id")]
    gap = (
        next((item for item in gaps if not item.get("remediation_task_id")), None)
        or next((item for item in gaps if item.get("remediation_synthesis_status") in {None, "empty"}), None)
        or next((item for item in gaps if item.get("gap_decision_status") != "closed"), None)
        or (gaps[0] if gaps else None)
    )
    require(bool(gap), f"no execution evidence gap available: {action_plan}", failures)
    run_id = str((gap or {}).get("run_id") or "")

    preview_status, preview = http_json(args.base_url, "POST", "/api/operator/execution-evidence/remediation-task", {
        "run_id": run_id,
    })
    outputs.append(json.dumps(preview, ensure_ascii=False))
    require(preview_status == 200, f"preview failed: {preview_status} {preview}", failures)
    require(preview.get("status") == "preview", f"preview status wrong: {preview}", failures)
    require(preview.get("created") is False, f"preview created task: {preview}", failures)
    require(preview.get("safety", {}).get("ledger_mutated") is False, f"preview mutated ledger: {preview}", failures)
    require((preview.get("task") or {}).get("description", "").startswith("Commander project:"), f"preview task is not Commander package: {preview}", failures)
    task_id = (preview.get("task") or {}).get("task_id")
    project_id = (preview.get("task") or {}).get("project_id")
    require(bool(task_id), f"preview task_id missing: {preview}", failures)
    require(bool(project_id), f"preview project_id missing: {preview}", failures)

    after_preview = db_fingerprint(db_path)
    if before is not None and after_preview is not None:
        require(before == after_preview, "preview changed database fingerprint", failures)

    with tempfile.TemporaryDirectory(prefix="agentops-evidence-gap-") as tmp:
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env.pop("AGENTOPS_API_KEY", None)

        cli_preview = run_cli(args.base_url, ["operator", "remediate-evidence-gap", "--run-id", run_id], env)
        outputs.extend([cli_preview.stdout, cli_preview.stderr])
        cli_preview_payload = load_json(cli_preview)
        require(cli_preview.returncode == 0, f"CLI preview failed: {cli_preview.stderr or cli_preview.stdout}", failures)
        require(cli_preview_payload.get("status") == "preview", f"CLI preview status wrong: {cli_preview_payload}", failures)

        handoff_item, handoff_payload = handoff_remediation_item(args.base_url, run_id, env, outputs)
        preview_step = handoff_item.get("next_workflow_step") or {}
        require(handoff_item.get("run_id") == run_id, f"handoff remediation item missing for run: {handoff_payload}", failures)
        require(preview_step.get("id") == "preview" or preview_step.get("step_id") == "preview", f"handoff should start at preview step: {handoff_item}", failures)
        preview_receipt_command = str(preview_step.get("receipt_verify_record_command") or "")
        require("record-action-receipt" in preview_receipt_command and "--confirm-record" in preview_receipt_command, f"preview receipt command missing: {preview_step}", failures)
        if preview_receipt_command:
            preview_receipt = run_agentops_command(args.base_url, preview_receipt_command, env)
            outputs.extend([preview_receipt.stdout, preview_receipt.stderr])
            preview_receipt_payload = load_json(preview_receipt)
            require(preview_receipt.returncode == 0, f"preview receipt record failed: {preview_receipt.stderr or preview_receipt.stdout}", failures)
            require(((preview_receipt_payload.get("receipt") or {}).get("source") == "handoff.evidence_remediation"), f"preview receipt source mismatch: {preview_receipt_payload}", failures)

        create_workflow_item, create_command_center = command_center_workflow_item(args.base_url, run_id, "create_task", outputs, failures)
        create_receipt_command = str(create_workflow_item.get("receipt_verify_record_command") or "")
        require(create_workflow_item.get("run_id") == run_id, f"command-center did not surface create_task after preview receipt: {create_command_center}", failures)
        require(create_workflow_item.get("preview_receipt_verified") is True, f"create_task should prove preview receipt first: {create_workflow_item}", failures)
        require(str(create_workflow_item.get("command") or "").endswith("--confirm-create"), f"create_task command must be explicit confirmation: {create_workflow_item}", failures)
        require(create_workflow_item.get("mutating") is True and create_workflow_item.get("confirm_required") is True, f"create_task mutation boundary missing: {create_workflow_item}", failures)

        cli_create = run_cli(args.base_url, ["operator", "remediate-evidence-gap", "--run-id", run_id, "--confirm-create"], env)
        outputs.extend([cli_create.stdout, cli_create.stderr])
        create_payload = load_json(cli_create)
        require(cli_create.returncode == 0, f"CLI create failed: {cli_create.stderr or cli_create.stdout}", failures)
        require(create_payload.get("status") in {"created", "already_exists"}, f"create status wrong: {create_payload}", failures)
        require(create_payload.get("created") is (create_payload.get("status") == "created"), f"create flag wrong: {create_payload}", failures)
        require(create_payload.get("commander_work_package") is True, f"created task not Commander package: {create_payload}", failures)
        require(create_payload.get("task_id") == task_id, f"created task id not stable: {create_payload} vs {task_id}", failures)
        if create_payload.get("status") == "created":
            require(create_payload.get("safety", {}).get("ledger_mutated") is True, f"create did not report ledger mutation: {create_payload}", failures)
        if create_receipt_command:
            create_receipt = run_agentops_command(args.base_url, create_receipt_command, env)
            outputs.extend([create_receipt.stdout, create_receipt.stderr])
            create_receipt_payload = load_json(create_receipt)
            require(create_receipt.returncode == 0, f"create_task receipt record failed: {create_receipt.stderr or create_receipt.stdout}", failures)
            require(((create_receipt_payload.get("receipt") or {}).get("source") == "handoff.evidence_remediation.create_task"), f"create_task receipt source mismatch: {create_receipt_payload}", failures)

        dispatch_workflow_item, dispatch_command_center = command_center_workflow_item(args.base_url, run_id, "dispatch_package", outputs, failures)
        require(dispatch_workflow_item.get("run_id") == run_id, f"command-center did not surface dispatch_package after create_task: {dispatch_command_center}", failures)
        require(dispatch_workflow_item.get("step_id") == "dispatch_package", f"dispatch workflow step mismatch: {dispatch_workflow_item}", failures)
        require("commander dispatch-package" in str(dispatch_workflow_item.get("command") or ""), f"dispatch workflow command missing: {dispatch_workflow_item}", failures)
        require(dispatch_workflow_item.get("mutating") is True, f"dispatch workflow should be marked mutating: {dispatch_workflow_item}", failures)

        cli_repeat = run_cli(args.base_url, ["operator", "remediate-evidence-gap", "--run-id", run_id, "--confirm-create"], env)
        outputs.extend([cli_repeat.stdout, cli_repeat.stderr])
        repeat_payload = load_json(cli_repeat)
        require(cli_repeat.returncode == 0, f"CLI repeat failed: {cli_repeat.stderr or cli_repeat.stdout}", failures)
        require(repeat_payload.get("status") == "already_exists", f"repeat create not idempotent: {repeat_payload}", failures)

        dispatch = run_cli(args.base_url, ["commander", "dispatch-package", "--task-id", str(task_id), "--adapter", "mock"], env)
        outputs.extend([dispatch.stdout, dispatch.stderr])
        dispatch_payload = load_json(dispatch)
        require(dispatch.returncode == 0, f"CLI dispatch failed: {dispatch.stderr or dispatch.stdout}", failures)
        require(dispatch_payload.get("ok") is True, f"dispatch not ok: {dispatch_payload}", failures)
        require(dispatch_payload.get("run_id"), f"dispatch missing run id: {dispatch_payload}", failures)
        dispatch_evidence = dispatch_payload.get("evidence") or {}
        for key in ["tool_calls", "evaluations", "artifacts", "audit_logs", "plan_evidence_manifests"]:
            require(int(dispatch_evidence.get(key) or 0) >= 1, f"dispatch evidence missing {key}: {dispatch_payload}", failures)

        post_dispatch_status, post_dispatch_center = http_json(args.base_url, "GET", "/api/operator/command-center?limit=20&refresh_cache=true")
        outputs.append(json.dumps(post_dispatch_center, ensure_ascii=False))
        post_dispatch_items = (post_dispatch_center.get("evidence_remediation_workflow") or {}).get("items") or []
        post_dispatch_item = next((row for row in post_dispatch_items if row.get("run_id") == run_id), {})
        post_dispatch_step = str(post_dispatch_item.get("step_id") or "")
        post_dispatch_command = str(post_dispatch_item.get("command") or "")
        require(post_dispatch_status == 200, f"post-dispatch command-center failed: {post_dispatch_status} {post_dispatch_center}", failures)
        require(post_dispatch_item.get("run_id") == run_id, f"command-center did not surface next workflow step after dispatch: {post_dispatch_center}", failures)
        require(post_dispatch_step in {"plan_evidence", "synthesize"}, f"unexpected post-dispatch workflow step: {post_dispatch_item}", failures)
        if post_dispatch_step == "plan_evidence":
            require("plan-evidence" in post_dispatch_command, f"plan evidence workflow command missing: {post_dispatch_item}", failures)
        else:
            require("commander synthesize" in post_dispatch_command, f"synthesize workflow command missing: {post_dispatch_item}", failures)

    package_status, packages = http_json(args.base_url, "GET", f"/api/commander/work-packages?project_id={project_id}&limit=5")
    outputs.append(json.dumps(packages, ensure_ascii=False))
    require(package_status == 200, f"package readback failed: {package_status} {packages}", failures)
    package_items = packages.get("work_packages") or []
    require(any(item.get("task_id") == task_id for item in package_items), f"created package missing from readback: {packages}", failures)
    matched = next((item for item in package_items if item.get("task_id") == task_id), {})
    require(matched.get("package_status") == "ready_for_review", f"package not ready after dispatch: {matched}", failures)
    require("task get" in (matched.get("recommended_action") or ""), f"package review next action missing: {matched}", failures)

    post_status, post_plan = http_json(args.base_url, "GET", "/api/operator/action-plan?limit=20")
    outputs.append(json.dumps(post_plan, ensure_ascii=False))
    require(post_status == 200, f"post-create action-plan failed: {post_status} {post_plan}", failures)
    post_gap = next((item for item in (post_plan.get("execution_evidence") or {}).get("gaps") or [] if item.get("run_id") == run_id), {})
    require(post_gap.get("remediation_task_id") == task_id, f"post-create gap did not link remediation task: {post_gap}", failures)
    require(post_gap.get("remediation_status") == "verified", f"post-dispatch gap did not verify remediation package: {post_gap}", failures)
    require(post_gap.get("severity") == "ready", f"post-dispatch gap did not become ready: {post_gap}", failures)
    synthesize_command = str(post_gap.get("command") or "")
    require(synthesize_command.startswith("agentops commander synthesize --project-id "), f"post-dispatch gap did not recommend synthesis: {post_gap}", failures)
    remediation_counts = post_gap.get("remediation_evidence_counts") or {}
    for key in ["tool_calls", "evaluations", "artifacts", "audit_logs", "plan_evidence_manifests"]:
        require(int(remediation_counts.get(key) or 0) >= 1, f"post-dispatch remediation evidence missing {key}: {post_gap}", failures)

    with tempfile.TemporaryDirectory(prefix="agentops-evidence-synthesis-") as tmp:
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env.pop("AGENTOPS_API_KEY", None)

        synth_args = shlex.split(synthesize_command)
        if synth_args and synth_args[0] == "agentops":
            synth_args = synth_args[1:]
        synthesis = run_cli(args.base_url, synth_args, env)
        outputs.extend([synthesis.stdout, synthesis.stderr])
        synthesis_payload = load_json(synthesis)
        require(synthesis.returncode == 0, f"synthesis command failed: {synthesis.stderr or synthesis.stdout}", failures)
        require(synthesis_payload.get("status") == "created", f"synthesis not created: {synthesis_payload}", failures)
        artifact_id = synthesis_payload.get("artifact_id")
        approval_id = synthesis_payload.get("approval_id")
        require(str(artifact_id or "").startswith("art_cmd_synthesis_"), f"synthesis artifact missing: {synthesis_payload}", failures)
        require(str(approval_id or "").startswith("ap_cmd_synthesis_"), f"synthesis approval missing: {synthesis_payload}", failures)

        pending_status, pending_plan = http_json(args.base_url, "GET", "/api/operator/action-plan?limit=20")
        outputs.append(json.dumps(pending_plan, ensure_ascii=False))
        require(pending_status == 200, f"pending action-plan failed: {pending_status} {pending_plan}", failures)
        pending_gap = next((item for item in (pending_plan.get("execution_evidence") or {}).get("gaps") or [] if item.get("run_id") == run_id), {})
        require(pending_gap.get("remediation_synthesis_status") == "review_pending", f"gap not waiting on synthesis review: {pending_gap}", failures)
        require(str(pending_gap.get("command") or "").startswith("agentops approval inspect --approval-id "), f"gap did not recommend approval inspect: {pending_gap}", failures)

        approve_status, approved = http_json(args.base_url, "POST", f"/api/approvals/{approval_id}/approve", {})
        outputs.append(json.dumps(approved, ensure_ascii=False))
        require(approve_status == 200, f"approval failed: {approve_status} {approved}", failures)
        require(approved.get("decision") == "approved", f"approval did not approve synthesis: {approved}", failures)

        approved_status, approved_plan = http_json(args.base_url, "GET", "/api/operator/action-plan?limit=20")
        outputs.append(json.dumps(approved_plan, ensure_ascii=False))
        require(approved_status == 200, f"approved action-plan failed: {approved_status} {approved_plan}", failures)
        approved_gap = next((item for item in (approved_plan.get("execution_evidence") or {}).get("gaps") or [] if item.get("run_id") == run_id), {})
        require(approved_gap.get("remediation_synthesis_status") == "approved_not_promoted", f"gap not ready to promote: {approved_gap}", failures)
        promote_command = str(approved_gap.get("command") or "")
        require(promote_command.startswith("agentops commander promote-synthesis --artifact-id "), f"gap did not recommend promotion: {approved_gap}", failures)

        promote_args = shlex.split(promote_command)
        if promote_args and promote_args[0] == "agentops":
            promote_args = promote_args[1:]
        promoted = run_cli(args.base_url, promote_args, env)
        outputs.extend([promoted.stdout, promoted.stderr])
        promoted_payload = load_json(promoted)
        require(promoted.returncode == 0, f"promotion command failed: {promoted.stderr or promoted.stdout}", failures)
        require(promoted_payload.get("status") == "promoted", f"synthesis not promoted: {promoted_payload}", failures)
        promoted_rows = promoted_payload.get("created") or {}
        require(promoted_rows.get("memory_id"), f"promotion missing memory candidate: {promoted_payload}", failures)
        require(promoted_rows.get("delivery_artifact_id"), f"promotion missing delivery artifact: {promoted_payload}", failures)

    promoted_status, promoted_plan = http_json(args.base_url, "GET", "/api/operator/action-plan?limit=20")
    outputs.append(json.dumps(promoted_plan, ensure_ascii=False))
    require(promoted_status == 200, f"promoted action-plan failed: {promoted_status} {promoted_plan}", failures)
    promoted_gap = next((item for item in (promoted_plan.get("execution_evidence") or {}).get("gaps") or [] if item.get("run_id") == run_id), {})
    require(promoted_gap.get("remediation_synthesis_status") in {"promoted", "memory_pending_review"}, f"gap did not record promoted synthesis: {promoted_gap}", failures)
    close_command = str(promoted_gap.get("command") or "")
    require(close_command.startswith("agentops operator close-evidence-gap --run-id "), f"promoted gap did not recommend close decision: {promoted_gap}", failures)
    promoted_summary = promoted_plan.get("summary") or {}
    require(int(promoted_summary.get("evidence_synthesis_promoted_runs") or 0) >= 1, f"promoted summary missing: {promoted_summary}", failures)
    require(int(promoted_summary.get("evidence_gap_closure_ready_runs") or 0) >= 1, f"closure-ready summary missing: {promoted_summary}", failures)

    with tempfile.TemporaryDirectory(prefix="agentops-evidence-close-") as tmp:
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env.pop("AGENTOPS_API_KEY", None)

        close_preview = run_cli(args.base_url, ["operator", "close-evidence-gap", "--run-id", run_id, "--decision", "accepted_remediation"], env)
        outputs.extend([close_preview.stdout, close_preview.stderr])
        close_preview_payload = load_json(close_preview)
        require(close_preview.returncode == 0, f"close preview failed: {close_preview.stderr or close_preview.stdout}", failures)
        require(close_preview_payload.get("status") == "preview", f"close preview status wrong: {close_preview_payload}", failures)
        require(close_preview_payload.get("safety", {}).get("ledger_mutated") is False, f"close preview mutated ledger: {close_preview_payload}", failures)

        close_args = shlex.split(close_command)
        if close_args and close_args[0] == "agentops":
            close_args = close_args[1:]
        closed = run_cli(args.base_url, close_args, env)
        outputs.extend([closed.stdout, closed.stderr])
        closed_payload = load_json(closed)
        require(closed.returncode == 0, f"close command failed: {closed.stderr or closed.stdout}", failures)
        require(closed_payload.get("status") == "closed", f"gap decision not closed: {closed_payload}", failures)
        require(closed_payload.get("closed") is True, f"gap decision closed flag wrong: {closed_payload}", failures)
        require(closed_payload.get("safety", {}).get("ledger_mutated") is True, f"close did not report ledger mutation: {closed_payload}", failures)

    closed_status, closed_plan = http_json(args.base_url, "GET", "/api/operator/action-plan?limit=20")
    outputs.append(json.dumps(closed_plan, ensure_ascii=False))
    require(closed_status == 200, f"closed action-plan failed: {closed_status} {closed_plan}", failures)
    closed_gap = next((item for item in (closed_plan.get("execution_evidence") or {}).get("gaps") or [] if item.get("run_id") == run_id), {})
    require(closed_gap.get("gap_decision_status") == "closed", f"gap did not retain closed decision: {closed_gap}", failures)
    require(closed_gap.get("gap_decision_type") == "accepted_remediation", f"gap closed decision type wrong: {closed_gap}", failures)
    closed_summary = closed_plan.get("summary") or {}
    require(int(closed_summary.get("closed_evidence_gap_runs") or 0) >= 1, f"closed summary missing: {closed_summary}", failures)

    after_create = db_fingerprint(db_path)
    if before is not None and after_create is not None:
        if create_payload.get("status") == "created":
            require(after_create.get("tasks", {}).get("count", 0) == before.get("tasks", {}).get("count", 0) + 1, f"task count did not increase once: before={before} after={after_create}", failures)
            require(after_create.get("runtime_events", {}).get("count", 0) >= before.get("runtime_events", {}).get("count", 0) + 1, f"runtime event missing: before={before} after={after_create}", failures)
            require(after_create.get("audit_logs", {}).get("count", 0) >= before.get("audit_logs", {}).get("count", 0) + 2, f"audit logs missing: before={before} after={after_create}", failures)

    require(not leaked_secret("\n".join(outputs)), "execution evidence remediation leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "run_id": run_id,
        "task_id": task_id,
        "project_id": project_id,
        "preview_read_only": before == after_preview if before is not None and after_preview is not None else None,
        "created_status": create_payload.get("status") if not failures else None,
        "package_readback_total": (packages.get("summary") or {}).get("total") if isinstance(packages, dict) else None,
        "secret_leaked": leaked_secret("\n".join(outputs)),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
