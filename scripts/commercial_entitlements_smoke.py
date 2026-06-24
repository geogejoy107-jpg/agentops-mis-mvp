#!/usr/bin/env python3
"""Smoke-test read-only commercial entitlement status API and CLI."""
from __future__ import annotations

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_MARKERS = ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_", "AGENTOPS_API_KEY="]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in SECRET_MARKERS)


def http_json(base_url: str) -> tuple[int, dict]:
    req = urllib.request.Request(base_url.rstrip("/") + "/api/commercial/entitlements", headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"error": exc.reason}
        return exc.code, body


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def run(cmd: list[str], *, env: dict[str, str], timeout: int = 45) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def start_server(port: int, env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def wait_for_api(base_url: str, timeout_sec: int = 30) -> None:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        try:
            status, _payload = http_json(base_url)
            if status < 500:
                return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.3)
    raise RuntimeError(f"Timed out waiting for entitlement API at {base_url}: {last_error}")


def post_json(base_url: str, path: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"error": exc.reason}
        return exc.code, body


def run_cli(base_url: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "--base-url", base_url, "commercial", "entitlements"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def validate(payload: dict, label: str, expected_edition: str = "free_local") -> None:
    require(payload.get("provider") == "agentops-commercial", f"{label} wrong provider: {payload}")
    require(payload.get("operation") == "entitlement_status", f"{label} wrong operation: {payload}")
    require(payload.get("status") == "ready", f"{label} bad status: {payload.get('status')}")
    require(payload.get("edition") == expected_edition, f"{label} should be {expected_edition}: {payload}")
    require(payload.get("token_omitted") is True, f"{label} token omission proof missing")
    require(payload.get("live_execution_performed") is False, f"{label} must not execute live work")
    capabilities = payload.get("capabilities") or {}
    require(capabilities.get("sqlite_ledger") is True, f"{label} sqlite ledger should be enabled")
    require(capabilities.get("postgres_adapter") is False, f"{label} postgres adapter should be gated below enterprise")
    require(capabilities.get("sso_hooks") is False, f"{label} SSO should be gated below enterprise")
    gates = payload.get("gates") or []
    gate_caps = {gate.get("capability"): gate for gate in gates if isinstance(gate, dict)}
    for capability in ["multi_project", "rbac", "postgres_adapter", "custom_connector_sdk"]:
        require(capability in gate_caps, f"{label} missing gate for {capability}")
        require(gate_caps[capability].get("enforcement") == "read_only_preview", f"{label} unexpected enforcement for {capability}")
    for capability in ["approval_policies", "notion_confirmed_export", "report_templates"]:
        require(capability in gate_caps, f"{label} missing fail-closed gate for {capability}")
        require(gate_caps[capability].get("enforcement") == "fail_closed", f"{label} {capability} should be fail_closed: {gate_caps[capability]}")
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety.read_only missing")
    require(safety.get("billing_call_performed") is False, f"{label} should not call billing")
    require("billing integration" in (payload.get("contract") or ""), f"{label} contract should mention billing boundary")


def validate_free_local_export_gate(base_url: str) -> dict:
    status, payload = post_json(
        base_url,
        "/api/integrations/notion/export-confirmed",
        {"confirm_export": True, "title": "Commercial entitlement smoke"},
    )
    require(status == 403, f"confirmed Notion export should be entitlement-blocked in Free Local: {status} {payload}")
    require(payload.get("error") == "entitlement_required", f"wrong block error: {payload}")
    require(payload.get("capability") == "notion_confirmed_export", f"wrong blocked capability: {payload}")
    require(payload.get("required_edition") == "pro_workspace", f"wrong required edition: {payload}")
    require(payload.get("current_edition") == "free_local", f"wrong current edition: {payload}")
    require(payload.get("enforcement") == "fail_closed", f"wrong enforcement: {payload}")
    require(payload.get("billing_call_performed") is False, f"billing should not be called: {payload}")
    require(payload.get("live_execution_performed") is False, f"live work should not be performed: {payload}")
    require(payload.get("token_omitted") is True, f"token omission proof missing: {payload}")
    return {
        "status": status,
        "capability": payload.get("capability"),
        "required_edition": payload.get("required_edition"),
        "current_edition": payload.get("current_edition"),
    }


def validate_free_local_template_gates(base_url: str) -> dict:
    results = {}
    for action, path in {
        "run": "/api/workflows/customer-task-templates/run",
        "submit": "/api/workflows/customer-task-templates/submit",
    }.items():
        status, payload = post_json(base_url, path, {"template_id": "tpl_customer_kb_qa_bot"})
        require(status == 403, f"template {action} should be entitlement-blocked in Free Local: {status} {payload}")
        require(payload.get("error") == "entitlement_required", f"template {action} wrong block error: {payload}")
        require(payload.get("capability") == "report_templates", f"template {action} wrong capability: {payload}")
        require(payload.get("required_edition") == "pro_workspace", f"template {action} wrong required edition: {payload}")
        require(payload.get("current_edition") == "free_local", f"template {action} wrong current edition: {payload}")
        require(payload.get("enforcement") == "fail_closed", f"template {action} wrong enforcement: {payload}")
        require(payload.get("billing_call_performed") is False, f"template {action} should not call billing: {payload}")
        require(payload.get("live_execution_performed") is False, f"template {action} should not perform live work: {payload}")
        results[action] = {
            "status": status,
            "capability": payload.get("capability"),
            "required_edition": payload.get("required_edition"),
            "current_edition": payload.get("current_edition"),
        }
    return results


def validate_entitlement_audit(db_path: Path | None) -> dict:
    if not db_path:
        return {"checked": False, "reason": "db_path_not_available"}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT action, entity_id, metadata_json
            FROM audit_logs
            WHERE action='commercial.entitlement_blocked'
            ORDER BY created_at
            """
        ).fetchall()
    counts: dict[str, int] = {}
    metadata_ok = True
    for row in rows:
        entity_id = row["entity_id"]
        counts[entity_id] = counts.get(entity_id, 0) + 1
        try:
            metadata = json.loads(row["metadata_json"] or "{}")
        except Exception:
            metadata = {}
            metadata_ok = False
        if metadata.get("billing_call_performed") is not False:
            metadata_ok = False
    require(counts.get("notion_confirmed_export", 0) >= 1, f"Notion entitlement block audit missing: {counts}")
    require(counts.get("report_templates", 0) >= 2, f"template entitlement block audits missing: {counts}")
    require(metadata_ok, "entitlement block audit metadata should prove billing_call_performed=false")
    return {"checked": True, "blocked_audit_counts": counts, "metadata_billing_call_false": metadata_ok}


def write_entitlement_fixture(path: Path, edition: str) -> None:
    path.write_text(
        json.dumps({"edition": edition, "overrides": {}, "notes": "Temporary entitlement smoke fixture. No secrets."}, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def validate_pro_template_run(base_url: str, entitlement_path: Path | None) -> dict:
    if not entitlement_path:
        return {"checked": False, "reason": "entitlement_fixture_not_available"}
    write_entitlement_fixture(entitlement_path, "pro_workspace")
    status, entitlement_payload = http_json(base_url)
    require(status == 200, f"pro entitlement API failed: {status} {entitlement_payload}")
    validate(entitlement_payload, "api-pro", expected_edition="pro_workspace")
    capabilities = entitlement_payload.get("capabilities") or {}
    require(capabilities.get("report_templates") is True, f"Pro should enable report_templates: {entitlement_payload}")
    status, payload = post_json(base_url, "/api/workflows/customer-task-templates/run", {"template_id": "tpl_customer_kb_qa_bot"})
    require(status == 201, f"Pro template run should be allowed: {status} {payload}")
    require(payload.get("error") != "entitlement_required", f"Pro template run was still blocked: {payload}")
    template = payload.get("template") or {}
    require(template.get("template_id") == "tpl_customer_kb_qa_bot", f"template result missing template id: {payload}")
    require(payload.get("project_id") or payload.get("task_id"), f"Pro template run should write ledger evidence: {payload}")
    return {
        "checked": True,
        "edition": entitlement_payload.get("edition"),
        "report_templates_enabled": capabilities.get("report_templates"),
        "status": status,
        "project_id": payload.get("project_id"),
        "task_id": payload.get("task_id"),
        "run_id": payload.get("run_id"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify commercial entitlement status API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL"))
    parser.add_argument("--db-path", default=os.environ.get("AGENTOPS_DB_PATH"))
    args = parser.parse_args()
    outputs: list[str] = []
    processes: list[subprocess.Popen[str]] = []
    try:
        with tempfile.TemporaryDirectory(prefix="agentops-commercial-entitlements-") as tmp:
            tmp_path = Path(tmp)
            base_url = args.base_url
            db_path = Path(args.db_path).expanduser() if args.db_path else None
            entitlements_path: Path | None = None
            server_env = os.environ.copy()
            if not base_url:
                port = free_port()
                base_url = f"http://127.0.0.1:{port}"
                entitlements_path = tmp_path / "entitlements.local.json"
                write_entitlement_fixture(entitlements_path, "free_local")
                db_path = tmp_path / "agentops.db"
                server_env["AGENTOPS_DB_PATH"] = str(db_path)
                server_env["AGENTOPS_ENTITLEMENTS_PATH"] = str(entitlements_path)
                server_env.pop("AGENTOPS_EDITION", None)
                reset = run([sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset"], env=server_env, timeout=30)
                require(reset.returncode == 0, f"seed reset failed: {reset.stderr or reset.stdout}")
                proc = start_server(port, server_env)
                processes.append(proc)
                wait_for_api(base_url)

            status, payload = http_json(base_url)
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            outputs.append(raw)
            require(status == 200, f"entitlement API failed: {status} {payload}")
            validate(payload, "api")
            export_gate = validate_free_local_export_gate(base_url)
            template_gates = validate_free_local_template_gates(base_url)
            audit_evidence = validate_entitlement_audit(db_path)
            outputs.append(json.dumps(export_gate, ensure_ascii=False, sort_keys=True))
            outputs.append(json.dumps(template_gates, ensure_ascii=False, sort_keys=True))
            outputs.append(json.dumps(audit_evidence, ensure_ascii=False, sort_keys=True))

            env = os.environ.copy()
            env["AGENTOPS_CONFIG"] = str(tmp_path / "config.json")
            env.pop("AGENTOPS_API_KEY", None)
            env.pop("AGENTOPS_EDITION", None)
            cli = run_cli(base_url, env)
            outputs.extend([cli.stdout, cli.stderr])
            require(cli.returncode == 0, f"entitlement CLI failed: {cli.stderr or cli.stdout}")
            cli_payload = json.loads(cli.stdout)
            validate(cli_payload, "cli")

            pro_template_run = validate_pro_template_run(base_url, entitlements_path)
            outputs.append(json.dumps(pro_template_run, ensure_ascii=False, sort_keys=True))

        require(not leaked_secret("\n".join(outputs)), "entitlements leaked token-like material")
        print(json.dumps({
            "ok": True,
            "edition": payload.get("edition"),
            "gate_count": len(payload.get("gates") or []),
            "notion_confirmed_export_blocked": export_gate,
            "report_template_execution_blocked": template_gates,
            "entitlement_block_audit": audit_evidence,
            "pro_template_run_allowed": pro_template_run,
            "postgres_enabled": payload.get("capabilities", {}).get("postgres_adapter"),
            "billing_call_performed": payload.get("safety", {}).get("billing_call_performed"),
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
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


if __name__ == "__main__":
    raise SystemExit(main())
