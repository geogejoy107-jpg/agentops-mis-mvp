#!/usr/bin/env python3
"""Browser snapshot and interaction smoke for the Next.js parity track.

The script starts an isolated MIS API provider and Next.js dev server, then uses
the Codex Playwright CLI wrapper to capture accessibility snapshots for the
current parity routes. It also exercises the approval and memory review flows
through the Next.js UI and verifies the resulting state through the API proxy.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NEXT_APP = ROOT / "ui" / "next-app"
PWCLI = Path.home() / ".codex" / "skills" / "playwright" / "scripts" / "playwright_cli.sh"
NEXT_ENV = NEXT_APP / "next-env.d.ts"

ROUTES = [
    ("/workspace", ["Workspace control plane", "Active tasks", "Pending approval queue"]),
    ("/workspace/agents", ["Agents", "Production security", "Adapter readiness"]),
    ("/workspace/agents/agt_cos", ["Agent Detail", "Per-agent performance", "Recent Runs"]),
    ("/workspace/commercial", ["Commercial", "Capability matrix", "Fail-closed gates"]),
    ("/workspace/governance", ["Governance", "Production readiness", "Session governance"]),
    ("/workspace/deployment", ["Deployment", "Storage backend migration gate", "Storage and retention"]),
    ("/workspace/tasks", ["Tasks", "running", "planned"]),
    ("/workspace/runs", ["Run Ledger", "Run", "Status"]),
    ("/workspace/tool-calls", ["Tool Call Ledger", "high-risk", "Run"]),
    ("/workspace/evaluations", ["Evaluation Room", "failed gates", "average score"]),
    ("/workspace/connectors", ["Runtime Connectors", "Runtime Trust Registry", "blocked"]),
    ("/workspace/external-bases/notion", ["Notion External Base", "dry-run default", "notion_confirmed_export"]),
    ("/workspace/approvals", ["Approvals", "Pending approval", "Decision history"]),
    ("/workspace/memory", ["Memory", "candidate", "approved"]),
    ("/workspace/audit", ["Audit", "audit events", "Actor"]),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(cmd: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def start_process(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def wait_http(url: str, timeout_sec: int = 45) -> None:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status < 500:
                    return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def http_json(url: str) -> object:
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def http_json_status(method: str, url: str, payload: dict | None = None) -> tuple[int, object]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read().decode("utf-8")
            return int(response.status), json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}


def http_form(url: str, payload: dict[str, str]) -> int:
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    data = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(url, data=data, method="POST")
    request.add_header("Content-Type", "application/x-www-form-urlencoded")
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=10) as response:
            return int(response.status)
    except urllib.error.HTTPError as exc:
        if exc.code in {302, 303, 307, 308}:
            return int(exc.code)
        raise


def seed_customer_project_fixture(db_path: str) -> str:
    project_id = f"pwfixture_{uuid.uuid4().hex[:8]}"
    now = dt.datetime.now(dt.timezone.utc)
    now_iso = now.isoformat()
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA foreign_keys=ON")
        for index, title in [(1, "Scope customer knowledge base"), (2, "Deliver customer Q&A bot report")]:
            task_id = f"tsk_kb_bot_{project_id}_{index:02d}"
            run_id = f"run_kb_bot_{project_id}_{index:02d}"
            agent_id = "agt_cos" if index == 2 else "agt_research"
            conn.execute(
                """INSERT INTO tasks(task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    task_id,
                    "local-demo",
                    title,
                    "Safe browser smoke fixture for customer project report parity.",
                    "usr_founder",
                    agent_id,
                    "[]",
                    "completed",
                    "medium",
                    None,
                    "Summary/hash report evidence only.",
                    "medium",
                    0.0,
                    now_iso,
                    now_iso,
                ),
            )
            conn.execute(
                """INSERT INTO runs(run_id,workspace_id,task_id,agent_id,runtime_type,status,started_at,ended_at,duration_ms,input_summary,output_summary,model_provider,model_name,input_tokens,output_tokens,reasoning_tokens,cost_usd,error_type,error_message,trace_id,parent_run_id,delegation_id,approval_required,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    run_id,
                    "local-demo",
                    task_id,
                    agent_id,
                    "mock",
                    "completed",
                    now_iso,
                    now_iso,
                    120000,
                    "Fixture input summary.",
                    "Fixture output summary for customer delivery report.",
                    "mock-provider",
                    "mock-model",
                    0,
                    0,
                    0,
                    0.0,
                    None,
                    None,
                    f"trace_{project_id}_{index:02d}",
                    None,
                    f"kb-bot-fixture:{project_id}:{index:02d}",
                    1 if index == 2 else 0,
                    now_iso,
                ),
            )
            conn.execute(
                """INSERT INTO evaluations(evaluation_id,task_id,run_id,agent_id,evaluator_type,score,pass_fail,rubric_json,notes,created_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    f"eval_kb_bot_{project_id}_{index:02d}",
                    task_id,
                    run_id,
                    agent_id,
                    "rule",
                    92.0,
                    "pass",
                    "{}",
                    "Fixture evaluation for Next.js customer report smoke.",
                    now_iso,
                ),
            )
        final_task_id = f"tsk_kb_bot_{project_id}_02"
        final_run_id = f"run_kb_bot_{project_id}_02"
        conn.execute(
            """INSERT INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"tc_kb_bot_{project_id}_delivery",
                final_run_id,
                "agt_cos",
                "customer.delivery_report",
                "v1",
                "custom",
                "{}",
                f"agentops://customer-projects/{project_id}/report",
                "medium",
                "completed",
                "Fixture delivery report tool call completed.",
                None,
                now_iso,
                now_iso,
                now_iso,
            ),
        )
        conn.execute(
            """INSERT INTO approvals(approval_id,task_id,run_id,tool_call_id,requested_by_agent_id,approver_user_id,decision,reason,expires_at,created_at,decided_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"ap_kb_bot_{project_id}_delivery",
                final_task_id,
                final_run_id,
                f"tc_kb_bot_{project_id}_delivery",
                "agt_cos",
                "usr_founder",
                "approved",
                "Fixture approval for customer delivery report smoke.",
                (now + dt.timedelta(days=2)).isoformat(),
                now_iso,
                now_iso,
            ),
        )
        conn.execute(
            """INSERT INTO artifacts(artifact_id,task_id,run_id,artifact_type,title,uri,summary,created_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (
                f"art_kb_bot_delivery_{project_id}",
                final_task_id,
                final_run_id,
                "customer_delivery_report",
                f"Customer delivery summary {project_id}",
                f"agentops://kb-bot-demo/{project_id}/delivery-summary",
                "Safe fixture customer delivery summary; raw documents and credentials omitted.",
                now_iso,
            ),
        )
        conn.execute(
            """INSERT INTO audit_logs(audit_id,actor_type,actor_id,action,entity_type,entity_id,before_hash,after_hash,metadata_json,tamper_chain_hash,created_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                f"audit_kb_bot_{project_id}",
                "system",
                "nextjs-playwright-smoke",
                "workflow.kb_bot_project.fixture",
                "projects",
                project_id,
                None,
                f"hash_{project_id}",
                json.dumps({"raw_documents_stored": False, "credentials_stored": False, "fixture": True}, sort_keys=True),
                f"chain_{project_id}",
                now_iso,
            ),
        )
        conn.commit()
    return project_id


def write_entitlement_fixture(path: Path, edition: str) -> None:
    payload = {
        "edition": edition,
        "notes": "Temporary Next.js Playwright smoke fixture. No secrets.",
        "overrides": {},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def wait_for_json(url: str, predicate, description: str, timeout_sec: int = 10) -> object:
    deadline = time.time() + timeout_sec
    last_value: object | None = None
    while time.time() < deadline:
        last_value = http_json(url)
        if predicate(last_value):
            return last_value
        time.sleep(0.4)
    raise AssertionError(f"Timed out waiting for {description}: last value {last_value!r}")


def restore_next_env() -> None:
    if not NEXT_ENV.exists():
        return
    text = NEXT_ENV.read_text(encoding="utf-8")
    text = text.replace('import "./.next/dev/types/routes.d.ts";', 'import "./.next/types/routes.d.ts";')
    NEXT_ENV.write_text(text, encoding="utf-8")


def leaked_secret(text: str) -> bool:
    markers = ["Authorization: " + "Bearer", "agtok" + "_", "agtsess" + "_", "sk" + "-", "ntn" + "_"]
    return any(marker in text for marker in markers)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def playwright(env: dict[str, str], *args: str, timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return run(["bash", str(PWCLI), *args], env=env, timeout=timeout)


def snapshot_route(base_url: str, path: str, expected: list[str], env: dict[str, str]) -> dict:
    target = base_url.rstrip("/") + path
    goto = playwright(env, "goto", target)
    require(goto.returncode == 0, f"Playwright goto failed for {path}: {goto.stderr or goto.stdout}")
    time.sleep(1.0)

    snapshot = playwright(env, "snapshot")
    require(snapshot.returncode == 0, f"Playwright snapshot failed for {path}: {snapshot.stderr or snapshot.stdout}")
    text = snapshot.stdout + snapshot.stderr
    missing = [item for item in expected if item not in text]
    require(not missing, f"Snapshot for {path} missed expected text: {missing}")
    require(not leaked_secret(text), f"Snapshot for {path} leaked token-like material")
    return {"path": path, "expected": expected, "snapshot_chars": len(text)}


def first_button_ref(snapshot_text: str, label: str) -> str:
    for line in snapshot_text.splitlines():
        if "button" not in line or label not in line:
            continue
        match = re.search(r"\[ref=(e\d+)\]", line)
        if match:
            return match.group(1)
    raise AssertionError(f"Could not find Playwright ref for {label!r} button")


def snapshot_text(env: dict[str, str], path: str) -> str:
    snapshot = playwright(env, "snapshot")
    require(snapshot.returncode == 0, f"Playwright snapshot failed for {path}: {snapshot.stderr or snapshot.stdout}")
    text = snapshot.stdout + snapshot.stderr
    require(not leaked_secret(text), f"Snapshot for {path} leaked token-like material")
    return text


def wait_for_snapshot_text(env: dict[str, str], path: str, predicate, description: str, timeout_sec: int = 12) -> str:
    deadline = time.time() + timeout_sec
    last_text = ""
    while time.time() < deadline:
        last_text = snapshot_text(env, path)
        if predicate(last_text):
            return last_text
        time.sleep(0.5)
    raise AssertionError(f"Timed out waiting for {description}; last snapshot had {len(last_text)} chars")


def find_by_id(rows: object, key: str, value: str) -> dict:
    require(isinstance(rows, list), f"Expected list payload while looking for {key}={value}")
    for row in rows:
        if isinstance(row, dict) and row.get(key) == value:
            return row
    raise AssertionError(f"Could not find {key}={value}")


def approve_first_pending_approval(next_base: str, env: dict[str, str]) -> dict:
    approvals_url = f"{next_base}/api/mis/approvals"
    approvals = http_json(approvals_url)
    require(isinstance(approvals, list), "Approvals API did not return a list")
    pending = [row for row in approvals if isinstance(row, dict) and row.get("decision") == "pending"]
    require(bool(pending), "No pending approval available for browser review smoke")
    pending_ids = {str(row["approval_id"]) for row in pending}

    target = next_base.rstrip("/") + "/workspace/approvals"
    goto = playwright(env, "goto", target)
    require(goto.returncode == 0, f"Playwright goto failed for approvals interaction: {goto.stderr or goto.stdout}")
    before = wait_for_snapshot_text(
        env,
        "/workspace/approvals",
        lambda text: "Approve" in text,
        "approvals page to render an Approve button",
    )
    button_ref = first_button_ref(before, "Approve")
    clicked = playwright(env, "click", button_ref)
    require(clicked.returncode == 0, f"Playwright approval click failed: {clicked.stderr or clicked.stdout}")

    def approved(payload: object) -> bool:
        require(isinstance(payload, list), "Approvals API did not return a list after click")
        return any(
            isinstance(row, dict)
            and str(row.get("approval_id")) in pending_ids
            and row.get("decision") == "approved"
            for row in payload
        )

    after_payload = wait_for_json(approvals_url, approved, "a visible approval to become approved")
    changed = [
        row
        for row in after_payload
        if isinstance(row, dict)
        and str(row.get("approval_id")) in pending_ids
        and row.get("decision") == "approved"
    ]
    approval_id = str(changed[0]["approval_id"])
    time.sleep(0.8)
    after = snapshot_text(env, "/workspace/approvals")
    require("approved" in after, "Approvals page did not show approved decision after click")
    return {
        "approval_id": approval_id,
        "button_ref": button_ref,
        "decision": find_by_id(after_payload, "approval_id", approval_id).get("decision"),
    }


def approve_first_candidate_memory(next_base: str, env: dict[str, str]) -> dict:
    memories_url = f"{next_base}/api/mis/memories"
    memories = http_json(memories_url)
    require(isinstance(memories, list), "Memories API did not return a list")
    candidates = [row for row in memories if isinstance(row, dict) and row.get("review_status") == "candidate"]
    require(bool(candidates), "No candidate memory available for browser review smoke")
    candidate_ids = {str(row["memory_id"]) for row in candidates}

    target = next_base.rstrip("/") + "/workspace/memory"
    goto = playwright(env, "goto", target)
    require(goto.returncode == 0, f"Playwright goto failed for memory interaction: {goto.stderr or goto.stdout}")
    before = wait_for_snapshot_text(
        env,
        "/workspace/memory",
        lambda text: "Approve" in text,
        "memory page to render an Approve button",
    )
    button_ref = first_button_ref(before, "Approve")
    clicked = playwright(env, "click", button_ref)
    require(clicked.returncode == 0, f"Playwright memory click failed: {clicked.stderr or clicked.stdout}")

    def approved(payload: object) -> bool:
        require(isinstance(payload, list), "Memories API did not return a list after click")
        return any(
            isinstance(row, dict)
            and str(row.get("memory_id")) in candidate_ids
            and row.get("review_status") == "approved"
            for row in payload
        )

    after_payload = wait_for_json(memories_url, approved, "a visible memory to become approved")
    changed = [
        row
        for row in after_payload
        if isinstance(row, dict)
        and str(row.get("memory_id")) in candidate_ids
        and row.get("review_status") == "approved"
    ]
    memory_id = str(changed[0]["memory_id"])
    time.sleep(0.8)
    after = snapshot_text(env, "/workspace/memory")
    require("approved" in after, "Memory page did not show approved review status after click")
    return {
        "memory_id": memory_id,
        "button_ref": button_ref,
        "review_status": find_by_id(after_payload, "memory_id", memory_id).get("review_status"),
    }


def archive_customer_project_report(next_base: str, project_id: str, env: dict[str, str]) -> dict:
    report_url = f"{next_base}/api/mis/workflows/customer-projects/{project_id}/report"
    before_report = http_json(report_url)
    require(isinstance(before_report, dict), "Customer project report API did not return an object")
    require(before_report.get("project_id") == project_id, f"Customer report project mismatch before archive: {before_report}")

    target = next_base.rstrip("/") + f"/workspace/customer-projects/{project_id}/report"
    goto = playwright(env, "goto", target)
    require(goto.returncode == 0, f"Playwright goto failed for customer report interaction: {goto.stderr or goto.stdout}")
    before = wait_for_snapshot_text(
        env,
        f"/workspace/customer-projects/{project_id}/report",
        lambda text: "Archive report" in text or "Refresh archive" in text,
        "customer report page to render an archive button",
    )
    button_ref = first_button_ref(before, "Archive report") if "Archive report" in before else first_button_ref(before, "Refresh archive")
    clicked = playwright(env, "click", button_ref)
    require(clicked.returncode == 0, f"Playwright report archive click failed: {clicked.stderr or clicked.stdout}")

    def archived(payload: object) -> bool:
        require(isinstance(payload, dict), "Customer report API did not return an object after archive")
        return payload.get("project_id") == project_id and bool(payload.get("report_artifact_id"))

    after_payload = wait_for_json(report_url, archived, f"report artifact for {project_id}", timeout_sec=20)
    time.sleep(0.8)
    after = snapshot_text(env, f"/workspace/customer-projects/{project_id}/report")
    require("report artifact" in after.lower(), "Customer report page did not show report artifact evidence after archive")
    return {
        "project_id": project_id,
        "button_ref": button_ref,
        "report_artifact_id": after_payload.get("report_artifact_id"),
    }


def review_first_runtime_connector(next_base: str, env: dict[str, str]) -> dict:
    connectors_url = f"{next_base}/api/mis/runtime-connectors"
    connectors = http_json(connectors_url)
    require(isinstance(connectors, list), "Runtime connectors API did not return a list")
    candidates = [
        row for row in connectors
        if isinstance(row, dict)
        and str(row.get("runtime_connector_id") or row.get("connector_id") or "")
        and row.get("trust_status") != "review_required"
    ]
    require(bool(candidates), "No runtime connector available for trust review smoke")
    candidate_ids = {str(row.get("runtime_connector_id") or row.get("connector_id")) for row in candidates}

    target = next_base.rstrip("/") + "/workspace/connectors"
    goto = playwright(env, "goto", target)
    require(goto.returncode == 0, f"Playwright goto failed for connectors interaction: {goto.stderr or goto.stdout}")
    wait_for_snapshot_text(
        env,
        "/workspace/connectors",
        lambda text: "Runtime Trust Registry" in text and "blocked" in text,
        "connectors page to render trust registry controls",
    )
    preferred_ids = [item for item in sorted(candidate_ids) if "agnesfallback" in item]
    selected_id = preferred_ids[0] if preferred_ids else sorted(candidate_ids)[-1]
    status = http_form(
        next_base.rstrip("/") + "/workspace/connectors/trust",
        {"connector_id": selected_id, "trust_status": "review_required"},
    )
    require(status < 500, f"Next connector trust fallback returned {status}")

    def reviewed(payload: object) -> bool:
        require(isinstance(payload, list), "Runtime connectors API did not return a list after trust update")
        return any(
            isinstance(row, dict)
            and str(row.get("runtime_connector_id") or row.get("connector_id")) in candidate_ids
            and row.get("trust_status") == "review_required"
            for row in payload
        )

    after_payload = wait_for_json(connectors_url, reviewed, "a runtime connector to become review_required")
    time.sleep(0.8)
    after = snapshot_text(env, "/workspace/connectors")
    require("review_required" in after, "Connectors page did not show review_required trust status after click")
    reviewed_row = next(
        row for row in after_payload
        if isinstance(row, dict)
        and str(row.get("runtime_connector_id") or row.get("connector_id")) in candidate_ids
        and row.get("trust_status") == "review_required"
    )
    connector_id = str(reviewed_row.get("runtime_connector_id") or reviewed_row.get("connector_id"))
    return {
        "connector_id": connector_id,
        "form_fallback_status": status,
        "trust_status": reviewed_row.get("trust_status"),
    }


def verify_notion_external_base_gate(next_base: str, env: dict[str, str]) -> dict:
    target = next_base.rstrip("/") + "/workspace/external-bases/notion"
    goto = playwright(env, "goto", target)
    require(goto.returncode == 0, f"Playwright goto failed for Notion external base: {goto.stderr or goto.stdout}")
    wait_for_snapshot_text(
        env,
        "/workspace/external-bases/notion",
        lambda text: "Run dry-run export" in text and "Confirm export" in text,
        "Notion external base page to render export controls",
    )

    dry_status, dry_payload = http_json_status("POST", f"{next_base}/api/mis/integrations/notion/dry-run-export", {})
    require(dry_status == 201, f"Notion dry-run export should be accepted through Next proxy: {dry_status} {dry_payload}")
    require(isinstance(dry_payload, dict) and dry_payload.get("dry_run") is True and dry_payload.get("created") is False, f"Notion dry-run should not create external page: {dry_payload}")
    require(bool(dry_payload.get("sync_event_id")), f"Notion dry-run did not create sync event evidence: {dry_payload}")
    require(not leaked_secret(json.dumps(dry_payload, ensure_ascii=False)), "Notion dry-run response leaked token-like material")

    fallback_status = http_form(
        next_base.rstrip("/") + "/workspace/external-bases/notion/export",
        {"mode": "confirmed"},
    )
    require(fallback_status == 303, f"Notion confirmed export form fallback should redirect after handling: {fallback_status}")
    blocked_status, blocked_payload = http_json_status(
        "POST",
        f"{next_base}/api/mis/integrations/notion/export-confirmed",
        {"confirm_export": True, "title": "Next Notion entitlement smoke"},
    )
    require(blocked_status == 403, f"Notion confirmed export should be entitlement-blocked in Free Local: {blocked_status} {blocked_payload}")
    require(isinstance(blocked_payload, dict), f"Notion entitlement block did not return an object: {blocked_payload}")
    require(blocked_payload.get("error") == "entitlement_required", f"Notion entitlement block missing error: {blocked_payload}")
    require(blocked_payload.get("capability") == "notion_confirmed_export", f"Notion entitlement block wrong capability: {blocked_payload}")
    require(blocked_payload.get("billing_call_performed") is False, f"Notion entitlement block should not call billing: {blocked_payload}")
    require(blocked_payload.get("live_execution_performed") is False, f"Notion entitlement block should not perform live work: {blocked_payload}")
    require(blocked_payload.get("token_omitted") is True, f"Notion entitlement block should omit token: {blocked_payload}")
    require(not leaked_secret(json.dumps(blocked_payload, ensure_ascii=False)), "Notion entitlement block leaked token-like material")
    return {
        "dry_run_status": dry_status,
        "dry_run_sync_event_id": dry_payload.get("sync_event_id"),
        "confirmed_form_fallback_status": fallback_status,
        "blocked_capability": blocked_payload.get("capability"),
        "required_edition": blocked_payload.get("required_edition"),
    }


def verify_dispatch_entitlement_block(next_base: str, env: dict[str, str]) -> dict:
    projects_url = f"{next_base}/api/mis/workflows/customer-projects?limit=25"
    before_projects = http_json(projects_url)
    require(isinstance(before_projects, dict), "Customer projects API did not return an object before dispatch")
    before_count = len(before_projects.get("projects", []))

    target = next_base.rstrip("/") + "/workspace/dispatch"
    goto = playwright(env, "goto", target)
    require(goto.returncode == 0, f"Playwright goto failed for dispatch interaction: {goto.stderr or goto.stdout}")
    before = wait_for_snapshot_text(
        env,
        "/workspace/dispatch",
        lambda text: "Start template" in text and "report_templates" in text,
        "dispatch page to render template start controls and entitlement gate",
    )
    button_ref = first_button_ref(before, "Start template")
    clicked = playwright(env, "click", button_ref)
    require(clicked.returncode == 0, f"Playwright dispatch template click failed: {clicked.stderr or clicked.stdout}")
    after = wait_for_snapshot_text(
        env,
        "/workspace/dispatch",
        lambda text: "Entitlement required" in text and "report_templates" in text,
        "dispatch page to show Free Local entitlement block",
    )
    require("pro_workspace" in after, "Dispatch entitlement block did not show required edition")
    after_projects = http_json(projects_url)
    require(isinstance(after_projects, dict), "Customer projects API did not return an object after dispatch")
    after_count = len(after_projects.get("projects", []))
    require(after_count == before_count, f"Blocked dispatch changed customer project count: {before_count} -> {after_count}")
    return {
        "button_ref": button_ref,
        "blocked_capability": "report_templates",
        "required_edition": "pro_workspace",
        "project_count": after_count,
    }


def verify_dispatch_template_run_success(next_base: str, entitlement_path: Path, env: dict[str, str]) -> dict:
    write_entitlement_fixture(entitlement_path, "pro_workspace")
    projects_url = f"{next_base}/api/mis/workflows/customer-projects?limit=25"
    before_projects = http_json(projects_url)
    require(isinstance(before_projects, dict), "Customer projects API did not return an object before Pro dispatch")
    before_rows = before_projects.get("projects") or []
    require(isinstance(before_rows, list), "Customer projects payload did not include a project list before Pro dispatch")
    before_ids = {str(row.get("project_id")) for row in before_rows if isinstance(row, dict) and row.get("project_id")}

    target = next_base.rstrip("/") + "/workspace/dispatch"
    goto = playwright(env, "goto", target)
    require(goto.returncode == 0, f"Playwright goto failed for Pro dispatch interaction: {goto.stderr or goto.stdout}")
    before = wait_for_snapshot_text(
        env,
        "/workspace/dispatch",
        lambda text: "Start template" in text and "report_templates true" in text and "billing call false" in text,
        "dispatch page to render Pro entitlement-enabled template controls",
    )
    button_ref = first_button_ref(before, "Start template")
    clicked = playwright(env, "click", button_ref, timeout=75)
    require(clicked.returncode == 0, f"Playwright Pro dispatch template click failed: {clicked.stderr or clicked.stdout}")
    after = wait_for_snapshot_text(
        env,
        "/workspace/dispatch",
        lambda text: "Customer project started" in text,
        "dispatch page to show started customer project",
        timeout_sec=25,
    )
    require("Entitlement required" not in after, "Pro dispatch still showed entitlement blocking")

    after_projects = http_json(projects_url)
    require(isinstance(after_projects, dict), "Customer projects API did not return an object after Pro dispatch")
    after_rows = after_projects.get("projects") or []
    require(isinstance(after_rows, list), "Customer projects payload did not include a project list after Pro dispatch")
    after_ids = {str(row.get("project_id")) for row in after_rows if isinstance(row, dict) and row.get("project_id")}
    created_ids = sorted(after_ids - before_ids)
    require(created_ids, f"Pro dispatch did not create a customer project: before={len(before_ids)} after={len(after_ids)}")
    project_id = created_ids[-1]

    report = http_json(f"{next_base}/api/mis/workflows/customer-projects/{project_id}/report")
    require(isinstance(report, dict), f"Created project report did not return an object: {report!r}")
    require(report.get("project_id") == project_id, f"Created project report project mismatch: {report}")
    counts = report.get("counts") or {}
    require((counts.get("tasks") or 0) >= 1, f"Created project report has no task evidence: {counts}")
    require(bool(report.get("artifact_id")), f"Created project report has no delivery artifact: {report}")
    execution_evidence = report.get("execution_evidence") or {}
    require((execution_evidence.get("agent_plans") or 0) >= 1, f"Created project report has no Agent Plan evidence: {execution_evidence}")
    require((execution_evidence.get("verified_plan_evidence_manifests") or 0) >= 1, f"Created project report has no verified plan evidence: {execution_evidence}")
    manifest_ids = execution_evidence.get("verified_manifest_ids") or execution_evidence.get("manifest_ids") or []
    require(bool(manifest_ids), f"Created project report did not expose manifest ids: {execution_evidence}")
    recent_manifests = execution_evidence.get("recent_manifests") or []
    report_target = next_base.rstrip("/") + f"/workspace/customer-projects/{project_id}/report"
    report_goto = playwright(env, "goto", report_target)
    require(report_goto.returncode == 0, f"Playwright goto failed for created project report: {report_goto.stderr or report_goto.stdout}")
    report_snapshot = wait_for_snapshot_text(
        env,
        f"/workspace/customer-projects/{project_id}/report",
        lambda text: "Agent Plan evidence" in text and "Verified Evidence" in text and "Open evidence" in text,
        "created project report page to render Agent Plan evidence",
        timeout_sec=12,
    )
    require("verified" in report_snapshot, "Created project report page did not show verified plan evidence")
    manifest_id = str(manifest_ids[0])
    evidence_goto = playwright(env, "goto", next_base.rstrip("/") + f"/workspace/evidence/{manifest_id}")
    require(evidence_goto.returncode == 0, f"Playwright goto failed for evidence drilldown: {evidence_goto.stderr or evidence_goto.stdout}")
    evidence_snapshot = wait_for_snapshot_text(
        env,
        f"/workspace/evidence/{manifest_id}",
        lambda text: "Evidence Drilldown" in text and "Manifest verification" in text and "Run graph" in text,
        "evidence drilldown page to render verification and run graph",
        timeout_sec=12,
    )
    require("pass" in evidence_snapshot and "Token omitted" in evidence_snapshot, "Evidence drilldown did not show verification pass and token omission")
    manifest_row = next((row for row in recent_manifests if isinstance(row, dict) and str(row.get("manifest_id")) == manifest_id), {})
    run_id = str(manifest_row.get("run_id") or "")
    task_id = str(manifest_row.get("task_id") or "")
    require(bool(run_id and task_id), f"Created report evidence did not expose task/run ids for {manifest_id}: {recent_manifests}")
    run_goto = playwright(env, "goto", next_base.rstrip("/") + f"/workspace/runs/{run_id}")
    require(run_goto.returncode == 0, f"Playwright goto failed for run detail: {run_goto.stderr or run_goto.stdout}")
    run_snapshot = wait_for_snapshot_text(
        env,
        f"/workspace/runs/{run_id}",
        lambda text: "Run Detail" in text and "Tool and evaluation evidence" in text and "Audit and artifact evidence" in text,
        "run detail page to render evidence sections",
        timeout_sec=12,
    )
    require(run_id in run_snapshot and "Token omitted" in run_snapshot, "Run detail did not show run id and token omission")
    task_goto = playwright(env, "goto", next_base.rstrip("/") + f"/workspace/tasks/{task_id}")
    require(task_goto.returncode == 0, f"Playwright goto failed for task detail: {task_goto.stderr or task_goto.stdout}")
    task_snapshot = wait_for_snapshot_text(
        env,
        f"/workspace/tasks/{task_id}",
        lambda text: "Task Detail" in text and "Approvals" in text and "Artifacts" in text,
        "task detail page to render approvals and artifacts",
        timeout_sec=12,
    )
    require(task_id in task_snapshot and "Token omitted" in task_snapshot, "Task detail did not show task id and token omission")
    serialized = json.dumps(report, ensure_ascii=False)
    require(not leaked_secret(serialized), "Created project report leaked token-like material")
    return {
        "button_ref": button_ref,
        "created_project_id": project_id,
        "evidence_manifest_id": manifest_id,
        "evidence_run_id": run_id,
        "evidence_task_id": task_id,
        "project_count_before": len(before_ids),
        "project_count_after": len(after_ids),
        "artifact_id": report.get("artifact_id"),
        "tasks": counts.get("tasks"),
        "runs": counts.get("runs"),
        "agent_plans": execution_evidence.get("agent_plans"),
        "verified_plan_evidence_manifests": execution_evidence.get("verified_plan_evidence_manifests"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Next.js Playwright snapshot smoke.")
    parser.add_argument("--api-port", type=int, default=0)
    parser.add_argument("--next-port", type=int, default=0)
    args = parser.parse_args()

    if not PWCLI.exists():
        print(json.dumps({"ok": False, "error": f"missing Playwright wrapper: {PWCLI}"}, indent=2), file=sys.stderr)
        return 1
    if run(["bash", "-lc", "command -v npx >/dev/null 2>&1"]).returncode != 0:
        print(json.dumps({"ok": False, "error": "npx is required for Playwright CLI wrapper"}, indent=2), file=sys.stderr)
        return 1

    api_port = args.api_port or free_port()
    next_port = args.next_port or free_port()
    api_base = f"http://127.0.0.1:{api_port}"
    next_base = f"http://127.0.0.1:{next_port}"
    session = f"agentops-next-parity-{uuid.uuid4().hex[:8]}"
    processes: list[subprocess.Popen[str]] = []

    try:
        with tempfile.TemporaryDirectory(prefix="agentops-next-pw-") as tmp:
            db_path = str(Path(tmp) / "agentops.db")
            entitlement_path = Path(tmp) / "entitlements.local.json"
            write_entitlement_fixture(entitlement_path, "free_local")
            reset_env = os.environ.copy()
            reset_env["AGENTOPS_DB_PATH"] = db_path
            reset_env["AGENTOPS_ENTITLEMENTS_PATH"] = str(entitlement_path)
            reset = run(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port), "--reset"], env=reset_env, timeout=30)
            require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")
            project_id = seed_customer_project_fixture(db_path)

            api_env = os.environ.copy()
            api_env["AGENTOPS_DB_PATH"] = db_path
            api_env["AGENTOPS_ENTITLEMENTS_PATH"] = str(entitlement_path)
            api_proc = start_process(["python3", "server.py", "--host", "127.0.0.1", "--port", str(api_port)], cwd=ROOT, env=api_env)
            processes.append(api_proc)
            wait_http(f"{api_base}/api/dashboard/metrics")

            next_env = os.environ.copy()
            next_env["AGENTOPS_API_BASE"] = f"{api_base}/api"
            next_proc = start_process(["npx", "next", "dev", "-p", str(next_port)], cwd=NEXT_APP, env=next_env)
            processes.append(next_proc)
            wait_http(f"{next_base}/workspace")

            pw_env = os.environ.copy()
            pw_env["PLAYWRIGHT_CLI_SESSION"] = session
            opened = playwright(pw_env, "open", f"{next_base}/workspace")
            require(opened.returncode == 0, f"Playwright open failed: {opened.stderr or opened.stdout}")
            resized = playwright(pw_env, "resize", "1365", "900")
            require(resized.returncode == 0, f"Playwright resize failed: {resized.stderr or resized.stdout}")

            routes = [
                *ROUTES,
                ("/workspace/reports", ["Reports", "Customer delivery board", "Customer project reports"]),
                ("/workspace/dispatch", ["Dispatch", "Customer task templates", "report_templates"]),
                (f"/workspace/customer-projects/{project_id}/report", ["Delivery Report", project_id, "Safety boundary"]),
            ]
            snapshots = [snapshot_route(next_base, path, expected, pw_env) for path, expected in routes]
            interactions = {
                "approval_review": approve_first_pending_approval(next_base, pw_env),
                "memory_review": approve_first_candidate_memory(next_base, pw_env),
                "runtime_connector_trust_review": review_first_runtime_connector(next_base, pw_env),
                "notion_external_base_gate": verify_notion_external_base_gate(next_base, pw_env),
                "customer_report_archive": archive_customer_project_report(next_base, project_id, pw_env),
                "dispatch_entitlement_block": verify_dispatch_entitlement_block(next_base, pw_env),
                "dispatch_template_run_success": verify_dispatch_template_run_success(next_base, entitlement_path, pw_env),
            }
            proxy_checks = {
                "agents": len(http_json(f"{next_base}/api/mis/agents")),
                "tasks": len(http_json(f"{next_base}/api/mis/tasks")),
                "memories": len(http_json(f"{next_base}/api/mis/memories")),
                "commercial_edition": http_json(f"{next_base}/api/mis/commercial/entitlements").get("edition"),
                "commercial_report_templates": http_json(f"{next_base}/api/mis/commercial/entitlements").get("capabilities", {}).get("report_templates"),
                "governance_sessions_token_omitted": http_json(f"{next_base}/api/mis/agent-gateway/sessions").get("token_omitted"),
                "deployment_local_token_omitted": http_json(f"{next_base}/api/mis/local/readiness").get("token_omitted"),
                "customer_projects": len(http_json(f"{next_base}/api/mis/workflows/customer-projects?limit=25").get("projects", [])),
                "runtime_connectors": len(http_json(f"{next_base}/api/mis/runtime-connectors")),
                "notion_writeback_allowed": http_json(f"{next_base}/api/mis/integrations/notion/status").get("writeback_allowed"),
                "notion_dry_run_default": http_json(f"{next_base}/api/mis/integrations/notion/status").get("dry_run_default"),
                "security_status": http_json(f"{next_base}/api/mis/security/production-readiness").get("status"),
                "worker_status": http_json(f"{next_base}/api/mis/workers/status").get("status"),
            }

            try:
                playwright(pw_env, "close", timeout=10)
            except subprocess.TimeoutExpired:
                playwright(pw_env, "kill-all", timeout=20)
            payload = {
                "ok": True,
                "api_base": api_base,
                "customer_project_fixture": project_id,
                "next_base": next_base,
                "routes": snapshots,
                "interactions": interactions,
                "proxy_checks": proxy_checks,
                "secret_leaked": False,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        for proc in reversed(processes):
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        run(["bash", "-lc", f"lsof -tiTCP:{next_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["bash", "-lc", f"lsof -tiTCP:{api_port} -sTCP:LISTEN | xargs -r kill"], timeout=10)
        run(["rm", "-rf", str(NEXT_APP / ".next")], timeout=10)
        restore_next_env()


if __name__ == "__main__":
    raise SystemExit(main())
