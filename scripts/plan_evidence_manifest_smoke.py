#!/usr/bin/env python3
"""Verify plan_evidence_manifest binds plan/run/tool/eval/artifact/audit evidence."""
from __future__ import annotations

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
    configured = os.environ.get("AGENTOPS_PLAN_EVIDENCE_SMOKE_PORT")
    if configured:
        return int(configured)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


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
    proc = subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    outputs.extend([proc.stdout, proc.stderr])
    return proc


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
    return subprocess.Popen(
        [sys.executable, str(SERVER), "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


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


def db_scalar(db_path: Path, sql: str, params: tuple = ()):
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(sql, params).fetchone()
    return row[0] if row else None


def main() -> int:
    suffix = stamp()
    port = choose_port()
    base_url = f"http://127.0.0.1:{port}"
    workspace_id = f"ws_plan_evidence_{suffix}"
    agent_id = f"agt_plan_evidence_{suffix}"
    task_id = f"tsk_plan_evidence_{suffix}"
    failures: list[str] = []
    outputs: list[str] = []
    server: subprocess.Popen[str] | None = None
    seed_snapshot = snapshot_seed_exports()

    with tempfile.TemporaryDirectory(prefix="agentops-plan-evidence-") as tmp:
        db_path = Path(tmp) / "agentops_plan_evidence.db"
        try:
            server = start_server(db_path, port)
            require(wait_ready(base_url, server), "isolated server did not become ready", failures)
            if failures:
                raise AssertionError(failures[-1])

            register = run_cli(["agent", "register", "--id", agent_id, "--name", "Plan Evidence Smoke", "--role", "Builder", "--runtime", "mock"], base_url, agent_id, workspace_id, outputs)
            require(register.returncode == 0, f"agent register failed: {register.stderr or register.stdout}", failures)

            task = run_cli([
                "task",
                "create",
                "--task-id",
                task_id,
                "--title",
                "Plan evidence manifest smoke task",
                "--description",
                "Bind a verified agent plan to ledger evidence.",
                "--owner-agent-id",
                agent_id,
                "--requester-id",
                "usr_founder",
                "--acceptance",
                "Manifest must verify plan/run/tool/eval/artifact/audit evidence.",
                "--risk",
                "medium",
            ], base_url, agent_id, workspace_id, outputs)
            require(task.returncode == 0, f"task create failed: {task.stderr or task.stdout}", failures)

            plan = run_cli([
                "agent-plan",
                "create",
                "--agent-id",
                agent_id,
                "--task-id",
                task_id,
                "--task-understanding",
                "Create a plan_evidence_manifest only after searching specs and writing ledger evidence.",
                "--referenced-specs",
                "PROJECT_SPEC.md,AGENT_WORKFLOW.md,docs/AGENT_WORK_METHOD_BLOCK.md",
                "--referenced-memories",
                "knowledge/shared/common_failures.md",
                "--referenced-bases",
                "base_local_tasks,base_local_memory",
                "--proposed-files-to-change",
                "server.py,agentops_mis_cli/agentops.py,scripts/plan_evidence_manifest_smoke.py",
                "--risk",
                "medium",
                "--execution-steps",
                "READ,PLAN,RETRIEVE,COMPARE,EXECUTE,VERIFY,RECORD",
                "--verification-plan",
                "Run plan_evidence_manifest_smoke.py against an isolated DB.",
                "--rollback-plan",
                "Remove manifest table, routes and CLI commands if verification fails.",
            ], base_url, agent_id, workspace_id, outputs)
            plan_payload = load_json(plan)
            plan_id = (plan_payload.get("agent_plan") or {}).get("plan_id")
            require(plan.returncode == 0 and bool(plan_id), f"agent plan create failed: {plan.stderr or plan.stdout}", failures)

            verified_plan = run_cli(["agent-plan", "verify", "--plan-id", str(plan_id)], base_url, agent_id, workspace_id, outputs)
            verified_plan_payload = load_json(verified_plan)
            require((verified_plan_payload.get("verification") or {}).get("pass") is True, f"agent plan did not verify: {verified_plan_payload}", failures)

            run = run_cli(["run", "start", "--task-id", task_id, "--agent-id", agent_id, "--runtime", "mock", "--input-summary", "Plan evidence smoke run."], base_url, agent_id, workspace_id, outputs)
            run_payload = load_json(run)
            run_id = (run_payload.get("run") or {}).get("run_id")
            require(run.returncode == 0 and bool(run_id), f"run start failed: {run.stderr or run.stdout}", failures)

            blocked_manifest = run_cli(["plan-evidence", "create", "--plan-id", str(plan_id), "--run-id", str(run_id), "--mismatch-policy", "block"], base_url, agent_id, workspace_id, outputs)
            blocked_payload = load_json(blocked_manifest)
            require(blocked_manifest.returncode == 0, f"blocked manifest create failed unexpectedly: {blocked_manifest.stderr or blocked_manifest.stdout}", failures)
            require((blocked_payload.get("verification") or {}).get("pass") is False, f"manifest without evidence should not pass: {blocked_payload}", failures)
            require((blocked_payload.get("manifest") or {}).get("status") == "blocked", f"manifest without evidence should block: {blocked_payload}", failures)

            tool = run_cli(["toolcall", "record", "--run-id", str(run_id), "--agent-id", agent_id, "--tool", "plan_evidence.fixture", "--category", "custom", "--risk", "low", "--status", "completed", "--summary", "Fixture tool call completed."], base_url, agent_id, workspace_id, outputs)
            tool_id = (load_json(tool).get("tool_call") or {}).get("tool_call_id")
            require(tool.returncode == 0 and bool(tool_id), f"toolcall record failed: {tool.stderr or tool.stdout}", failures)

            evaluation = run_cli(["eval", "submit", "--run-id", str(run_id), "--task-id", task_id, "--agent-id", agent_id, "--gate", "plan_evidence_manifest_smoke", "--score", "1", "--pass", "--notes", "Fixture evaluation passed."], base_url, agent_id, workspace_id, outputs)
            evaluation_id = (load_json(evaluation).get("evaluation") or {}).get("evaluation_id")
            require(evaluation.returncode == 0 and bool(evaluation_id), f"evaluation submit failed: {evaluation.stderr or evaluation.stdout}", failures)

            artifact = run_cli(["artifact", "record", "--run-id", str(run_id), "--task-id", task_id, "--agent-id", agent_id, "--type", "plan_evidence_fixture", "--title", "Plan evidence fixture artifact", "--summary", "Safe fixture artifact summary.", "--uri", f"run://{run_id}"], base_url, agent_id, workspace_id, outputs)
            artifact_id = (load_json(artifact).get("artifact") or {}).get("artifact_id")
            require(artifact.returncode == 0 and bool(artifact_id), f"artifact record failed: {artifact.stderr or artifact.stdout}", failures)

            manifest = run_cli([
                "plan-evidence",
                "create",
                "--plan-id",
                str(plan_id),
                "--run-id",
                str(run_id),
                "--mismatch-policy",
                "block",
                "--tool-call-ids",
                str(tool_id),
                "--evaluation-ids",
                str(evaluation_id),
                "--artifact-ids",
                str(artifact_id),
            ], base_url, agent_id, workspace_id, outputs)
            manifest_payload = load_json(manifest)
            manifest_id = (manifest_payload.get("manifest") or {}).get("manifest_id")
            verification = manifest_payload.get("verification") or {}
            counts = verification.get("evidence_counts") or {}
            require(manifest.returncode == 0 and bool(manifest_id), f"manifest create failed: {manifest.stderr or manifest.stdout}", failures)
            require(verification.get("pass") is True, f"manifest verification failed: {manifest_payload}", failures)
            require((manifest_payload.get("manifest") or {}).get("status") == "verified", f"manifest not marked verified: {manifest_payload}", failures)
            require(counts.get("tool_calls", 0) >= 1 and counts.get("evaluations", 0) >= 1 and counts.get("artifacts", 0) >= 1 and counts.get("audit_logs", 0) >= 1, f"missing evidence counts: {verification}", failures)

            audit_before_reverify = db_scalar(db_path, "SELECT COUNT(*) FROM audit_logs")
            manifest_before_reverify = db_scalar(db_path, "SELECT status || '|' || updated_at FROM plan_evidence_manifests WHERE manifest_id=?", (manifest_id,))
            reverify = run_cli(["plan-evidence", "verify", "--manifest-id", str(manifest_id)], base_url, agent_id, workspace_id, outputs)
            reverify_payload = load_json(reverify)
            require(reverify.returncode == 0, f"manifest reverify failed: {reverify.stderr or reverify.stdout}", failures)
            require((reverify_payload.get("verification") or {}).get("pass") is True, f"manifest reverify did not pass: {reverify_payload}", failures)
            audit_after_reverify = db_scalar(db_path, "SELECT COUNT(*) FROM audit_logs")
            manifest_after_reverify = db_scalar(db_path, "SELECT status || '|' || updated_at FROM plan_evidence_manifests WHERE manifest_id=?", (manifest_id,))
            require(audit_before_reverify == audit_after_reverify, "read-only plan-evidence verify wrote audit rows", failures)
            require(manifest_before_reverify == manifest_after_reverify, "read-only plan-evidence verify mutated manifest status/timestamp", failures)

            listed = run_cli(["plan-evidence", "list", "--run-id", str(run_id), "--limit", "10"], base_url, agent_id, workspace_id, outputs)
            listed_ids = {row.get("manifest_id") for row in (load_json(listed).get("manifests") or [])}
            require(listed.returncode == 0 and manifest_id in listed_ids, f"manifest missing from list: {listed.stdout}", failures)
            require(not SECRET_RE.search("\n".join(outputs)), "plan evidence smoke leaked token-like material", failures)
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
