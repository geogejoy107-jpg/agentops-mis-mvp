#!/usr/bin/env python3
"""Verify customer delivery approvals fail closed until a manifest verifies."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import socket
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


def run_cli(args: list[str], base_url: str, agent_id: str, workspace_id: str, outputs: list[str], timeout: int = 60) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_AGENT_ID"] = agent_id
    env["AGENTOPS_WORKSPACE_ID"] = workspace_id
    proc = subprocess.run([str(CLI), *args], cwd=ROOT, env=env, capture_output=True, text=True, timeout=timeout, check=False)
    outputs.extend([proc.stdout, proc.stderr])
    return proc


def http_json(method: str, base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict, str]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if method != "GET" else None
    req = urllib.request.Request(base_url + path, data=data, headers={"Content-Type": "application/json"}, method=method)
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


def start_server(db_path: Path, port: int) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    return subprocess.Popen([sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


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
    seed_snapshot = snapshot_seed_exports()
    server: subprocess.Popen[str] | None = None

    with tempfile.TemporaryDirectory(prefix="agentops-delivery-gate-") as tmp:
        db_path = Path(tmp) / "agentops_delivery_gate.db"
        try:
            server = start_server(db_path, port)
            require(wait_ready(base_url, server), "isolated server did not become ready", failures)
            if failures:
                raise AssertionError(failures[-1])

            register = run_cli(["agent", "register", "--id", agent_id, "--name", "Delivery Gate Smoke", "--role", "Builder", "--runtime", "mock"], base_url, agent_id, workspace_id, outputs)
            require(register.returncode == 0, f"agent register failed: {register.stderr or register.stdout}", failures)
            task = run_cli(["task", "create", "--task-id", task_id, "--title", "Delivery manifest gate smoke", "--description", "Customer delivery approval must consume a verified manifest.", "--owner-agent-id", agent_id, "--requester-id", "usr_founder", "--acceptance", "Approval blocks until plan_evidence_manifest verifies.", "--risk", "medium"], base_url, agent_id, workspace_id, outputs)
            require(task.returncode == 0, f"task create failed: {task.stderr or task.stdout}", failures)
            plan = run_cli(["agent-plan", "create", "--agent-id", agent_id, "--task-id", task_id, "--task-understanding", "Produce customer delivery only after ledger evidence is bound.", "--referenced-specs", "PROJECT_SPEC.md,AGENT_WORKFLOW.md", "--referenced-memories", "knowledge/shared/common_failures.md", "--referenced-bases", "base_local_tasks,base_local_memory", "--proposed-files-to-change", "server.py,scripts/delivery_approval_manifest_gate_smoke.py", "--risk", "medium", "--execution-steps", "READ,PLAN,EXECUTE,VERIFY,RECORD", "--verification-plan", "Run delivery_approval_manifest_gate_smoke.py.", "--rollback-plan", "Remove delivery gate checks if smoke fails."], base_url, agent_id, workspace_id, outputs)
            plan_id = (load_json(plan).get("agent_plan") or {}).get("plan_id")
            require(plan.returncode == 0 and bool(plan_id), f"plan create failed: {plan.stderr or plan.stdout}", failures)
            run = run_cli(["run", "start", "--task-id", task_id, "--agent-id", agent_id, "--runtime", "mock", "--input-summary", "Delivery gate smoke run."], base_url, agent_id, workspace_id, outputs)
            run_id = (load_json(run).get("run") or {}).get("run_id")
            require(run.returncode == 0 and bool(run_id), f"run start failed: {run.stderr or run.stdout}", failures)

            status, approval, raw = http_json("POST", base_url, "/api/agent-gateway/approvals/request", {
                "workspace_id": workspace_id,
                "approval_id": approval_id,
                "run_id": run_id,
                "agent_id": agent_id,
                "reason": "Customer delivery acceptance is required before treating this worker result as approved.",
            })
            outputs.append(raw)
            require(status == 201, f"delivery approval request failed: {status} {approval}", failures)

            status, blocked, raw = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
            outputs.append(raw)
            require(status == 409, f"approval should block without manifest: {status} {blocked}", failures)
            require(blocked.get("error") == "verified_plan_evidence_manifest_required", f"wrong block payload: {blocked}", failures)

            tool = run_cli(["toolcall", "record", "--run-id", str(run_id), "--agent-id", agent_id, "--tool", "delivery_gate.fixture", "--category", "custom", "--risk", "low", "--status", "completed", "--summary", "Fixture tool call completed."], base_url, agent_id, workspace_id, outputs)
            tool_id = (load_json(tool).get("tool_call") or {}).get("tool_call_id")
            evaluation = run_cli(["eval", "submit", "--run-id", str(run_id), "--task-id", task_id, "--agent-id", agent_id, "--gate", "delivery_manifest_gate", "--score", "1", "--pass", "--notes", "Delivery gate fixture passed."], base_url, agent_id, workspace_id, outputs)
            evaluation_id = (load_json(evaluation).get("evaluation") or {}).get("evaluation_id")
            artifact = run_cli(["artifact", "record", "--run-id", str(run_id), "--task-id", task_id, "--agent-id", agent_id, "--type", "customer_worker_result", "--title", "Delivery gate fixture artifact", "--summary", "Safe customer delivery fixture summary.", "--uri", f"run://{run_id}"], base_url, agent_id, workspace_id, outputs)
            artifact_id = (load_json(artifact).get("artifact") or {}).get("artifact_id")
            require(tool_id and evaluation_id and artifact_id, "missing tool/eval/artifact ids", failures)

            manifest = run_cli(["plan-evidence", "create", "--plan-id", str(plan_id), "--run-id", str(run_id), "--mismatch-policy", "block", "--tool-call-ids", str(tool_id), "--evaluation-ids", str(evaluation_id), "--artifact-ids", str(artifact_id)], base_url, agent_id, workspace_id, outputs)
            manifest_payload = load_json(manifest)
            manifest_id = (manifest_payload.get("manifest") or {}).get("manifest_id")
            require(manifest.returncode == 0 and (manifest_payload.get("verification") or {}).get("pass") is True, f"manifest did not verify: {manifest_payload}", failures)

            status, approved, raw = http_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
            outputs.append(raw)
            require(status == 200 and approved.get("decision") == "approved", f"approval should pass with verified manifest: {status} {approved}", failures)

            status, board, raw = http_json("GET", base_url, "/api/workflows/customer-delivery-board?limit=10")
            outputs.append(raw)
            deliveries = board.get("deliveries") or []
            delivery = next((row for row in deliveries if row.get("run_id") == run_id), {})
            gate = delivery.get("delivery_approval_gate") or {}
            require(status == 200, f"delivery board failed: {status} {board}", failures)
            require(gate.get("pass") is True and gate.get("manifest_id") == manifest_id, f"board did not surface verified manifest: {delivery}", failures)
            require(not SECRET_RE.search("\n".join(outputs)), "delivery approval smoke leaked token-like material", failures)
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

    print(json.dumps({
        "ok": not failures,
        "failures": failures,
        "base_url": base_url,
        "secret_leaked": False if not SECRET_RE.search("\n".join(outputs)) else True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
