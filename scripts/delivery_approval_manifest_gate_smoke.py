#!/usr/bin/env python3
"""Python+SQLite test-only regression for the customer delivery manifest gate.

This isolated fixture is not commercial Next.js/Postgres migration evidence.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import secrets
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
SERVER = ROOT / "server.py"
SEED_EXPORTS = [
    ROOT / "artifacts" / "sample_export_runs.json",
    ROOT / "artifacts" / "sample_export_memories.json",
]
SECRET_RE = re.compile(r"(Authorization:|Bearer |agtok_[A-Za-z0-9_-]{16,}|agtsess_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|ntn_[A-Za-z0-9_-]{16,})")
TOKEN_RE = re.compile(r"(?:agtok_|agtsess_|sk-|ntn_)[A-Za-z0-9_-]{16,}")
FIXTURE_ENV_TO_CLEAR = (
    "AGENTOPS_ADMIN_KEY",
    "AGENTOPS_API_KEY",
    "AGENTOPS_DEPLOYMENT_MODE",
    "AGENTOPS_EDITION",
    "AGENTOPS_ENABLE_POSTGRES_STORAGE",
    "AGENTOPS_ENTITLEMENTS_PATH",
    "AGENTOPS_POSTGRES_DSN",
    "AGENTOPS_POSTGRES_READ_ONLY_HTTP",
    "AGENTOPS_POSTGRES_WRITE_HTTP",
    "AGENTOPS_REQUIRE_PRODUCTION_SECURITY",
    "AGENTOPS_STORAGE_BACKEND",
    "AGENTOPS_WORKSPACE_ADMIN_KEYS_JSON",
    "DATABASE_URL",
)
TEST_CONTRACT = "python_sqlite_delivery_approval_manifest_gate_test_only_v1"


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def snapshot_seed_exports() -> dict[Path, str | None]:
    return {path: path.read_text(encoding="utf-8") if path.exists() else None for path in SEED_EXPORTS}


def restore_seed_exports(snapshot: dict[Path, str | None]) -> None:
    for path, content in snapshot.items():
        if content is None:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        else:
            path.write_text(content, encoding="utf-8")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {}


def clean_fixture_environment() -> dict[str, str]:
    env = os.environ.copy()
    for key in FIXTURE_ENV_TO_CLEAR:
        env.pop(key, None)
    return env


def sensitive_material_found(text: str, *values: str) -> bool:
    return bool(SECRET_RE.search(text) or any(value and value in text for value in values))


def redact_sensitive_text(text: str, *values: str) -> str:
    redacted = str(text)
    for value in values:
        if value:
            redacted = redacted.replace(value, "[REDACTED]")
    return TOKEN_RE.sub("[REDACTED]", redacted)


def run_cli(
    args: list[str],
    base_url: str,
    agent_id: str,
    workspace_id: str,
    outputs: list[str],
    *,
    token: str,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    env = clean_fixture_environment()
    env["AGENTOPS_API_KEY"] = token
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_AGENT_ID"] = agent_id
    env["AGENTOPS_WORKSPACE_ID"] = workspace_id
    proc = subprocess.run([str(CLI), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    outputs.extend([proc.stdout, proc.stderr])
    return proc


def http_json(
    method: str,
    base_url: str,
    path: str,
    payload: dict | None = None,
    *,
    token: str | None = None,
    admin_key: str | None = None,
) -> tuple[int, dict, str]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if method != "GET" else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if admin_key:
        headers["X-AgentOps-Admin-Key"] = admin_key
    req = urllib.request.Request(base_url + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw}
        return exc.code, body, raw


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout: float = 20.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return False
        try:
            with urllib.request.urlopen(base_url + "/api/dashboard/metrics", timeout=1) as resp:
                return resp.status == 200
        except (urllib.error.URLError, TimeoutError):
            time.sleep(0.2)
    return False


def start_server(db_path: Path, port: int, admin_key: str) -> subprocess.Popen[str]:
    env = clean_fixture_environment()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_RUNTIME_DIR"] = str(db_path.parent / "runtime")
    env["AGENTOPS_STORAGE_BACKEND"] = "sqlite"
    env["AGENTOPS_EDITION"] = "team_governance"
    env["AGENTOPS_ADMIN_KEY"] = admin_key
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    return subprocess.Popen([sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def install_trusted_customer_delivery_sqlite_fixture(
    db_path: Path,
    *,
    approval_id: str,
    task_id: str,
    run_id: str,
    workspace_id: str,
    agent_id: str,
) -> dict:
    """Bind a local test approval to customer_delivery without an Agent API input."""
    with sqlite3.connect(db_path, timeout=5.0) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("BEGIN IMMEDIATE")
        before = conn.execute(
            """SELECT approval.approval_id,approval.approval_kind,approval.task_id,
                      approval.run_id,approval.tool_call_id,approval.requested_by_agent_id,
                      approval.decision,task.workspace_id AS task_workspace_id,
                      run.workspace_id AS run_workspace_id,run.agent_id AS run_agent_id
               FROM approvals approval
               JOIN tasks task ON task.task_id=approval.task_id
               JOIN runs run ON run.run_id=approval.run_id AND run.task_id=task.task_id
               WHERE approval.approval_id=?""",
            (approval_id,),
        ).fetchone()
        if not before:
            raise AssertionError("trusted customer_delivery fixture approval was not found")
        binding_valid = (
            before["approval_kind"] == "run_execution"
            and before["task_id"] == task_id
            and before["run_id"] == run_id
            and before["tool_call_id"] is None
            and before["requested_by_agent_id"] == agent_id
            and before["decision"] == "pending"
            and before["task_workspace_id"] == workspace_id
            and before["run_workspace_id"] == workspace_id
            and before["run_agent_id"] == agent_id
        )
        if not binding_valid:
            raise AssertionError("trusted customer_delivery fixture binding validation failed")
        updated = conn.execute(
            """UPDATE approvals SET approval_kind='customer_delivery'
               WHERE approval_id=? AND approval_kind='run_execution'
                 AND task_id=? AND run_id=? AND tool_call_id IS NULL
                 AND requested_by_agent_id=? AND decision='pending'""",
            (approval_id, task_id, run_id, agent_id),
        )
        if updated.rowcount != 1:
            raise AssertionError("trusted customer_delivery fixture update lost its single row")
        after = conn.execute(
            """SELECT approval_kind,task_id,run_id,tool_call_id,
                      requested_by_agent_id,decision
               FROM approvals WHERE approval_id=?""",
            (approval_id,),
        ).fetchone()
        if not after or after["approval_kind"] != "customer_delivery":
            raise AssertionError("trusted customer_delivery fixture kind verification failed")
        conn.commit()
        return {
            "fixture_source": "direct_sqlite_test_helper_bound_to_agent_gateway_approval",
            "approval_kind": after["approval_kind"],
            "binding_verified": True,
            "agent_selected_approval_kind": False,
        }


def main() -> int:
    suffix = stamp()
    port = choose_port()
    base_url = f"http://127.0.0.1:{port}"
    workspace_id = f"ws_delivery_gate_{suffix}"
    agent_id = f"agt_delivery_gate_{suffix}"
    task_id = f"tsk_delivery_gate_{suffix}"
    approval_id = f"ap_customer_worker_delivery_{suffix}"
    failures: list[str] = []
    outputs: list[str] = []
    admin_key = "adm_test_" + secrets.token_urlsafe(32)
    gateway_token = ""
    trusted_fixture: dict = {}
    seed_snapshot = snapshot_seed_exports()
    server: subprocess.Popen[str] | None = None

    with tempfile.TemporaryDirectory(prefix="agentops-delivery-gate-") as tmp:
        db_path = Path(tmp) / "agentops_delivery_gate.db"
        try:
            server = start_server(db_path, port, admin_key)
            require(wait_ready(base_url, server), "isolated server did not become ready", failures)
            if failures:
                raise AssertionError(failures[-1])

            enrollment_status, enrollment, _enrollment_raw = http_json(
                "POST",
                base_url,
                "/api/agent-gateway/enrollment/request",
                {
                    "agent_id": agent_id,
                    "name": "Delivery Gate Smoke",
                    "role": "Builder",
                    "runtime_type": "mock",
                    "workspace_id": workspace_id,
                    "reason": "Run the customer delivery manifest gate smoke.",
                    "scopes": [
                        "agents:write",
                        "agents:heartbeat",
                        "agent_plans:read",
                        "agent_plans:write",
                        "plan_evidence:read",
                        "plan_evidence:write",
                        "tasks:create",
                        "tasks:read",
                        "tasks:claim",
                        "runs:write",
                        "toolcalls:write",
                        "artifacts:write",
                        "approvals:request",
                        "evaluations:submit",
                        "audit:write",
                    ],
                },
                admin_key=admin_key,
            )
            enrollment_approval = enrollment.get("approval") or {}
            enrollment_approval_id = enrollment_approval.get("approval_id")
            require(
                enrollment_status == 201
                and bool(enrollment_approval_id)
                and enrollment_approval.get("approval_kind") == "agent_enrollment",
                f"enrollment request failed: {enrollment_status} {enrollment}",
                failures,
            )
            approve_status, approved_enrollment, _approve_raw = http_json(
                "POST",
                base_url,
                f"/api/approvals/{enrollment_approval_id}/approve",
                {"workspace_id": workspace_id},
                admin_key=admin_key,
            )
            require(
                approve_status == 200 and approved_enrollment.get("decision") == "approved",
                f"enrollment approval failed: {approve_status} {approved_enrollment}",
                failures,
            )
            issue_status, issued, _issue_raw = http_json(
                "POST",
                base_url,
                "/api/agent-gateway/enrollment/issue-approved",
                {"approval_id": enrollment_approval_id, "workspace_id": workspace_id, "ttl_days": 1},
                admin_key=admin_key,
            )
            gateway_token = str(issued.get("token") or "")
            require(issue_status == 201 and bool(gateway_token), f"enrollment issue failed: {issue_status}", failures)

            register = run_cli(["agent", "register", "--id", agent_id, "--name", "Delivery Gate Smoke", "--role", "Builder", "--runtime", "mock"], base_url, agent_id, workspace_id, outputs, token=gateway_token)
            require(register.returncode == 0, f"agent register failed: {register.stderr or register.stdout}", failures)
            task = run_cli(["task", "create", "--task-id", task_id, "--title", "Delivery manifest gate smoke", "--description", "Customer delivery approval must consume a verified manifest.", "--owner-agent-id", agent_id, "--requester-id", "usr_founder", "--acceptance", "Approval blocks until plan_evidence_manifest verifies.", "--risk", "medium"], base_url, agent_id, workspace_id, outputs, token=gateway_token)
            require(task.returncode == 0, f"task create failed: {task.stderr or task.stdout}", failures)
            plan = run_cli(["agent-plan", "create", "--agent-id", agent_id, "--task-id", task_id, "--task-understanding", "Produce customer delivery only after ledger evidence is bound.", "--referenced-specs", "PROJECT_SPEC.md,AGENT_WORKFLOW.md", "--referenced-memories", "knowledge/shared/common_failures.md", "--referenced-bases", "base_local_tasks,base_local_memory", "--proposed-files-to-change", "server.py,scripts/delivery_approval_manifest_gate_smoke.py", "--risk", "medium", "--execution-steps", "READ,PLAN,EXECUTE,VERIFY,RECORD", "--verification-plan", "Run delivery_approval_manifest_gate_smoke.py.", "--rollback-plan", "Remove delivery gate checks if smoke fails."], base_url, agent_id, workspace_id, outputs, token=gateway_token)
            plan_id = (load_json(plan).get("agent_plan") or {}).get("plan_id")
            require(plan.returncode == 0 and bool(plan_id), f"plan create failed: {plan.stderr or plan.stdout}", failures)
            run = run_cli(["run", "start", "--task-id", task_id, "--agent-id", agent_id, "--runtime", "mock", "--input-summary", "Delivery gate smoke run."], base_url, agent_id, workspace_id, outputs, token=gateway_token)
            run_id = (load_json(run).get("run") or {}).get("run_id")
            require(run.returncode == 0 and bool(run_id), f"run start failed: {run.stderr or run.stdout}", failures)

            status, approval, raw = http_json("POST", base_url, "/api/agent-gateway/approvals/request", {
                "workspace_id": workspace_id,
                "approval_id": approval_id,
                "run_id": run_id,
                "agent_id": agent_id,
                "reason": "Customer delivery acceptance is required before treating this worker result as approved.",
            }, token=gateway_token)
            outputs.append(raw)
            require(status == 201, f"delivery approval request failed: {status} {approval}", failures)
            if status != 201:
                raise AssertionError("Agent Gateway did not create the fixture-bound approval")
            trusted_fixture = install_trusted_customer_delivery_sqlite_fixture(
                db_path,
                approval_id=approval_id,
                task_id=task_id,
                run_id=str(run_id),
                workspace_id=workspace_id,
                agent_id=agent_id,
            )
            require(
                trusted_fixture.get("approval_kind") == "customer_delivery"
                and trusted_fixture.get("binding_verified") is True
                and trusted_fixture.get("agent_selected_approval_kind") is False,
                f"trusted customer_delivery fixture verification failed: {trusted_fixture}",
                failures,
            )

            status, blocked, raw = http_json(
                "POST",
                base_url,
                f"/api/approvals/{approval_id}/approve",
                {"workspace_id": workspace_id},
                admin_key=admin_key,
            )
            outputs.append(raw)
            require(status == 409, f"approval should block without manifest: {status} {blocked}", failures)
            require(blocked.get("error") == "verified_plan_evidence_manifest_required", f"wrong block payload: {blocked}", failures)

            tool = run_cli(["toolcall", "record", "--run-id", str(run_id), "--agent-id", agent_id, "--tool", "delivery_gate.fixture", "--category", "custom", "--risk", "low", "--status", "completed", "--summary", "Fixture tool call completed."], base_url, agent_id, workspace_id, outputs, token=gateway_token)
            tool_id = (load_json(tool).get("tool_call") or {}).get("tool_call_id")
            evaluation = run_cli(["eval", "submit", "--run-id", str(run_id), "--task-id", task_id, "--agent-id", agent_id, "--gate", "delivery_manifest_gate", "--score", "1", "--pass", "--notes", "Delivery gate fixture passed."], base_url, agent_id, workspace_id, outputs, token=gateway_token)
            evaluation_id = (load_json(evaluation).get("evaluation") or {}).get("evaluation_id")
            artifact = run_cli(["artifact", "record", "--run-id", str(run_id), "--task-id", task_id, "--agent-id", agent_id, "--type", "customer_worker_result", "--title", "Delivery gate fixture artifact", "--summary", "Safe customer delivery fixture summary.", "--uri", f"run://{run_id}"], base_url, agent_id, workspace_id, outputs, token=gateway_token)
            artifact_id = (load_json(artifact).get("artifact") or {}).get("artifact_id")
            require(tool_id and evaluation_id and artifact_id, "missing tool/eval/artifact ids", failures)

            manifest = run_cli(["plan-evidence", "create", "--plan-id", str(plan_id), "--run-id", str(run_id), "--mismatch-policy", "block", "--tool-call-ids", str(tool_id), "--evaluation-ids", str(evaluation_id), "--artifact-ids", str(artifact_id)], base_url, agent_id, workspace_id, outputs, token=gateway_token)
            manifest_payload = load_json(manifest)
            manifest_id = (manifest_payload.get("manifest") or {}).get("manifest_id")
            require(manifest.returncode == 0 and (manifest_payload.get("verification") or {}).get("pass") is True, f"manifest did not verify: {manifest_payload}", failures)

            status, approved, raw = http_json(
                "POST",
                base_url,
                f"/api/approvals/{approval_id}/approve",
                {"workspace_id": workspace_id},
                admin_key=admin_key,
            )
            outputs.append(raw)
            require(status == 200 and approved.get("decision") == "approved", f"approval should pass with verified manifest: {status} {approved}", failures)

            status, board, raw = http_json(
                "GET",
                base_url,
                f"/api/workflows/customer-delivery-board?workspace_id={workspace_id}&limit=10",
            )
            outputs.append(raw)
            deliveries = board.get("deliveries") or []
            delivery = next((row for row in deliveries if row.get("run_id") == run_id), {})
            gate = delivery.get("delivery_approval_gate") or {}
            require(status == 200, f"delivery board failed: {status} {board}", failures)
            require(gate.get("pass") is True and gate.get("manifest_id") == manifest_id, f"board did not surface verified manifest: {delivery}", failures)
        except Exception as exc:
            failures.append(f"unexpected exception: {type(exc).__name__}: {exc}")
        finally:
            if server:
                server.terminate()
                try:
                    out, err = server.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    server.kill()
                    out, err = server.communicate(timeout=5)
                outputs.extend([out or "", err or ""])
            restore_seed_exports(seed_snapshot)

    captured_text = "\n".join([*outputs, *failures])
    secret_leaked = sensitive_material_found(captured_text, admin_key, gateway_token)
    if secret_leaked:
        failures.append("captured output contained sensitive material; values omitted")
    redacted_failures = [redact_sensitive_text(item, admin_key, gateway_token) for item in failures]
    print(json.dumps({
        "ok": not failures,
        "failures": redacted_failures,
        "base_url": base_url,
        "contract": TEST_CONTRACT,
        "evidence_scope": "python_sqlite_test_only_regression",
        "commercial_next_postgres_evidence": False,
        "real_agent_runtime_executed": False,
        "admin_auth": "explicit_temporary_local_admin_key",
        "approval_fixture_source": trusted_fixture.get("fixture_source"),
        "approval_kind_verified": trusted_fixture.get("approval_kind") == "customer_delivery",
        "agent_selected_approval_kind": trusted_fixture.get("agent_selected_approval_kind"),
        "secret_leaked": secret_leaked,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
