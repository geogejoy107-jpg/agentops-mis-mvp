#!/usr/bin/env python3
"""Verify a release-safe closure packet has only safe IDs, hashes and counts."""
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
SECRET_RE = re.compile(
    r"(Authorization:|Bearer |agtok_[A-Za-z0-9_-]{16,}|agtsess_[A-Za-z0-9_-]{16,}|sk-[A-Za-z0-9_-]{16,}|ntn_[A-Za-z0-9_-]{16,})"
)


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


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


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def run_cli(
    args: list[str],
    base_url: str,
    agent_id: str,
    workspace_id: str,
    outputs: list[str],
    timeout: int = 90,
) -> subprocess.CompletedProcess[str]:
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


def http_json(method: str, base_url: str, path: str, payload: dict | None = None) -> tuple[int, dict, str]:
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if method != "GET" else None
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
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
            with urllib.request.urlopen(base_url + "/api/agent-gateway/status", timeout=1) as resp:
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


def db_one(db_path: Path, sql: str, params: tuple = ()) -> dict:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else {}


def db_rows(db_path: Path, sql: str, params: tuple = ()) -> list[dict]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(sql, params).fetchall()]


def db_count(db_path: Path, sql: str, params: tuple = ()) -> int:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(sql, params).fetchone()
        return int(row[0] or 0) if row else 0


def main() -> int:
    suffix = stamp()
    port = choose_port()
    base_url = f"http://127.0.0.1:{port}"
    workspace_id = f"ws_safe_closure_{suffix}"
    agent_id = f"agt_safe_closure_{suffix}"
    task_id = f"tsk_safe_closure_{suffix}"
    delivery_approval_id = f"ap_customer_worker_delivery_{suffix}"
    failures: list[str] = []
    outputs: list[str] = []
    server: subprocess.Popen[str] | None = None
    seed_snapshot = snapshot_seed_exports()
    evidence_packet: dict = {}

    with tempfile.TemporaryDirectory(prefix="agentops-safe-closure-") as tmp:
        db_path = Path(tmp) / "agentops_safe_closure.db"
        try:
            server = start_server(db_path, port)
            require(wait_ready(base_url, server), "isolated server did not become ready", failures)
            if failures:
                raise AssertionError(failures[-1])

            register = run_cli(
                ["agent", "register", "--id", agent_id, "--name", "Safe Closure Evidence Agent", "--role", "Builder", "--runtime", "mock"],
                base_url,
                agent_id,
                workspace_id,
                outputs,
            )
            require(register.returncode == 0, f"agent register failed: {register.stderr or register.stdout}", failures)

            task = run_cli(
                [
                    "task",
                    "create",
                    "--task-id",
                    task_id,
                    "--title",
                    "Safe closure evidence packet smoke",
                    "--description",
                    "Produce a release packet with only safe IDs, hashes, statuses and evidence counts.",
                    "--owner-agent-id",
                    agent_id,
                    "--requester-id",
                    "usr_founder",
                    "--acceptance",
                    "Plan, task, run, artifact and review IDs must be bound by verified evidence and audit rows.",
                    "--risk",
                    "high",
                ],
                base_url,
                agent_id,
                workspace_id,
                outputs,
            )
            require(task.returncode == 0, f"task create failed: {task.stderr or task.stdout}", failures)

            plan = run_cli(
                [
                    "agent-plan",
                    "create",
                    "--agent-id",
                    agent_id,
                    "--task-id",
                    task_id,
                    "--task-understanding",
                    "Close a high-risk release evidence packet only after plan approval, verified ledger evidence and human delivery review.",
                    "--referenced-specs",
                    "PROJECT_SPEC.md,AGENT_WORKFLOW.md,docs/V1_5_MERGE_READINESS_CHECKLIST.md",
                    "--referenced-memories",
                    "knowledge/shared/common_failures.md",
                    "--referenced-bases",
                    "base_local_tasks,base_local_memory",
                    "--proposed-files-to-change",
                    "scripts/safe_closure_evidence_packet_smoke.py,docs/V1_5_MERGE_READINESS_CHECKLIST.md,.github/workflows/ci.yml",
                    "--risk",
                    "high",
                    "--execution-steps",
                    "READ,PLAN,RETRIEVE,COMPARE,EXECUTE,VERIFY,RECORD",
                    "--verification-plan",
                    "Run safe_closure_evidence_packet_smoke.py against an isolated temp DB.",
                    "--rollback-plan",
                    "Remove the release packet gate and keep delivery approval blocked if verification fails.",
                ],
                base_url,
                agent_id,
                workspace_id,
                outputs,
            )
            plan_payload = load_json(plan)
            agent_plan = plan_payload.get("agent_plan") or {}
            plan_id = agent_plan.get("plan_id")
            plan_approval_id = agent_plan.get("approval_id")
            require(plan.returncode == 0 and bool(plan_id and plan_approval_id), f"agent plan create failed: {plan.stderr or plan.stdout}", failures)

            verified_plan = run_cli(["agent-plan", "verify", "--plan-id", str(plan_id)], base_url, agent_id, workspace_id, outputs)
            verified_plan_payload = load_json(verified_plan)
            require((verified_plan_payload.get("verification") or {}).get("pass") is True, f"agent plan did not verify: {verified_plan_payload}", failures)

            status, plan_approved, raw = http_json("POST", base_url, f"/api/approvals/{plan_approval_id}/approve", {})
            outputs.append(raw)
            require(status == 200 and (plan_approved.get("agent_plan") or {}).get("status") == "approved", f"plan approval failed: {status} {plan_approved}", failures)

            run = run_cli(
                [
                    "run",
                    "start",
                    "--task-id",
                    task_id,
                    "--agent-id",
                    agent_id,
                    "--runtime",
                    "mock",
                    "--plan-id",
                    str(plan_id),
                    "--input-summary",
                    "Safe closure evidence packet run.",
                ],
                base_url,
                agent_id,
                workspace_id,
                outputs,
            )
            run_payload = load_json(run)
            run_id = (run_payload.get("run") or {}).get("run_id")
            require(run.returncode == 0 and bool(run_id), f"run start failed: {run.stderr or run.stdout}", failures)

            tool = run_cli(
                [
                    "toolcall",
                    "record",
                    "--run-id",
                    str(run_id),
                    "--agent-id",
                    agent_id,
                    "--tool",
                    "safe_closure.fixture",
                    "--category",
                    "custom",
                    "--risk",
                    "low",
                    "--status",
                    "completed",
                    "--summary",
                    "Fixture tool call completed with safe summary only.",
                ],
                base_url,
                agent_id,
                workspace_id,
                outputs,
            )
            tool_id = (load_json(tool).get("tool_call") or {}).get("tool_call_id")
            require(tool.returncode == 0 and bool(tool_id), f"toolcall record failed: {tool.stderr or tool.stdout}", failures)

            evaluation = run_cli(
                [
                    "eval",
                    "submit",
                    "--run-id",
                    str(run_id),
                    "--task-id",
                    task_id,
                    "--agent-id",
                    agent_id,
                    "--gate",
                    "safe_closure_evidence_packet",
                    "--score",
                    "1",
                    "--pass",
                    "--notes",
                    "Fixture release evidence packet checks passed.",
                ],
                base_url,
                agent_id,
                workspace_id,
                outputs,
            )
            evaluation_id = (load_json(evaluation).get("evaluation") or {}).get("evaluation_id")
            require(evaluation.returncode == 0 and bool(evaluation_id), f"evaluation submit failed: {evaluation.stderr or evaluation.stdout}", failures)

            artifact = run_cli(
                [
                    "artifact",
                    "record",
                    "--run-id",
                    str(run_id),
                    "--task-id",
                    task_id,
                    "--agent-id",
                    agent_id,
                    "--type",
                    "release_safe_closure_packet",
                    "--title",
                    "Safe closure evidence packet",
                    "--summary",
                    "Safe release packet summary with IDs, hashes, statuses and counts only.",
                    "--uri",
                    f"run://{run_id}/safe-closure-packet",
                ],
                base_url,
                agent_id,
                workspace_id,
                outputs,
            )
            artifact_id = (load_json(artifact).get("artifact") or {}).get("artifact_id")
            require(artifact.returncode == 0 and bool(artifact_id), f"artifact record failed: {artifact.stderr or artifact.stdout}", failures)

            run_cli(
                ["run", "heartbeat", "--run-id", str(run_id), "--status", "completed", "--summary", "Safe closure packet fixture completed.", "--duration-ms", "1200"],
                base_url,
                agent_id,
                workspace_id,
                outputs,
            )

            manifest = run_cli(
                [
                    "plan-evidence",
                    "create",
                    "--plan-id",
                    str(plan_id),
                    "--run-id",
                    str(run_id),
                    "--agent-id",
                    agent_id,
                    "--mismatch-policy",
                    "block",
                    "--tool-call-ids",
                    str(tool_id),
                    "--evaluation-ids",
                    str(evaluation_id),
                    "--artifact-ids",
                    str(artifact_id),
                ],
                base_url,
                agent_id,
                workspace_id,
                outputs,
            )
            manifest_payload = load_json(manifest)
            manifest_id = (manifest_payload.get("manifest") or {}).get("manifest_id")
            verification = manifest_payload.get("verification") or {}
            require(manifest.returncode == 0 and bool(manifest_id), f"manifest create failed: {manifest.stderr or manifest.stdout}", failures)
            require(verification.get("pass") is True, f"manifest did not verify: {manifest_payload}", failures)

            status, approval_request, raw = http_json(
                "POST",
                base_url,
                "/api/agent-gateway/approvals/request",
                {
                    "workspace_id": workspace_id,
                    "approval_id": delivery_approval_id,
                    "run_id": run_id,
                    "agent_id": agent_id,
                    "reason": "Customer delivery safe closure review for release evidence packet.",
                },
            )
            outputs.append(raw)
            require(status == 201 and (approval_request.get("approval") or {}).get("approval_id") == delivery_approval_id, f"delivery approval request failed: {status} {approval_request}", failures)

            status, review_queue, raw = http_json("GET", base_url, "/api/review/queue?limit=20")
            outputs.append(raw)
            review_items = review_queue.get("review_items") or []
            require(status == 200 and review_queue.get("operation") == "human_review_queue", f"review queue failed: {status} {review_queue}", failures)
            require(
                any(item.get("item_type") == "approval" and item.get("item_id") == delivery_approval_id for item in review_items),
                f"delivery approval missing from review queue: {review_queue}",
                failures,
            )

            status, delivery_approved, raw = http_json("POST", base_url, f"/api/approvals/{delivery_approval_id}/approve", {})
            outputs.append(raw)
            delivery_decision = (delivery_approved.get("approval") or delivery_approved).get("decision")
            require(status == 200 and delivery_decision == "approved", f"delivery approval failed: {status} {delivery_approved}", failures)

            candidate_memories = db_rows(
                db_path,
                "SELECT memory_id FROM memories WHERE review_status='candidate' AND (task_id=? OR source_ref=?) ORDER BY created_at",
                (task_id, run_id),
            )
            for memory in candidate_memories:
                memory_id = str(memory.get("memory_id") or "")
                if not memory_id:
                    continue
                status, memory_approved, raw = http_json("POST", base_url, f"/api/memories/{memory_id}/approve", {})
                outputs.append(raw)
                require(status == 200 and memory_approved.get("review_status") == "approved", f"memory approval failed: {status} {memory_approved}", failures)

            status, report, raw = http_json("GET", base_url, f"/api/operator/evidence-report?workspace_id={workspace_id}&run_id={run_id}&limit=5")
            outputs.append(raw)
            report_item = (report.get("runs") or [{}])[0]
            require(status == 200 and report.get("operation") == "operator_evidence_report", f"operator evidence report failed: {status} {report}", failures)
            require(report_item.get("run_id") == run_id and report_item.get("status") == "ready", f"evidence report did not mark run ready: {report_item}", failures)
            require((report_item.get("plan_evidence_manifest") or {}).get("verification_pass") is True, f"report missing verified manifest: {report_item}", failures)

            run_row = db_one(db_path, "SELECT run_id, task_id, agent_id, agent_plan_id, plan_hash, status, approval_required FROM runs WHERE run_id=?", (run_id,))
            plan_row = db_one(db_path, "SELECT plan_id, task_id, agent_id, status, plan_hash FROM agent_plans WHERE plan_id=?", (plan_id,))
            delivery_row = db_one(db_path, "SELECT approval_id, task_id, run_id, decision FROM approvals WHERE approval_id=?", (delivery_approval_id,))
            counts = {
                "tasks": db_count(db_path, "SELECT COUNT(*) FROM tasks WHERE task_id=?", (task_id,)),
                "runs": db_count(db_path, "SELECT COUNT(*) FROM runs WHERE run_id=?", (run_id,)),
                "agent_plans": db_count(db_path, "SELECT COUNT(*) FROM agent_plans WHERE plan_id=?", (plan_id,)),
                "plan_evidence_manifests": db_count(db_path, "SELECT COUNT(*) FROM plan_evidence_manifests WHERE manifest_id=? AND status='verified'", (manifest_id,)),
                "tool_calls": db_count(db_path, "SELECT COUNT(*) FROM tool_calls WHERE tool_call_id=? AND run_id=?", (tool_id, run_id)),
                "evaluations": db_count(db_path, "SELECT COUNT(*) FROM evaluations WHERE evaluation_id=? AND run_id=?", (evaluation_id, run_id)),
                "artifacts": db_count(db_path, "SELECT COUNT(*) FROM artifacts WHERE artifact_id=? AND run_id=?", (artifact_id, run_id)),
                "approved_memories": db_count(db_path, "SELECT COUNT(*) FROM memories WHERE review_status='approved' AND (task_id=? OR source_ref=?)", (task_id, run_id)),
                "approvals": db_count(db_path, "SELECT COUNT(*) FROM approvals WHERE approval_id IN (?,?)", (plan_approval_id, delivery_approval_id)),
                "audit_logs_for_packet": db_count(
                    db_path,
                    "SELECT COUNT(*) FROM audit_logs WHERE entity_id IN (?,?,?,?,?,?,?,?)",
                    (task_id, run_id, plan_id, manifest_id, tool_id, evaluation_id, artifact_id, delivery_approval_id),
                ),
            }
            require(run_row.get("agent_plan_id") == plan_id, f"run did not bind agent_plan_id: {run_row}", failures)
            require(bool(run_row.get("plan_hash")) and run_row.get("plan_hash") == plan_row.get("plan_hash"), f"run/plan hash mismatch: run={run_row} plan={plan_row}", failures)
            require(delivery_row.get("decision") == "approved", f"delivery approval not approved in DB: {delivery_row}", failures)
            for key, value in counts.items():
                minimum = 2 if key == "approvals" else 1
                require(value >= minimum, f"missing {key} evidence count: {counts}", failures)

            evidence_packet = {
                "workspace_id": workspace_id,
                "agent_id": agent_id,
                "task_id": task_id,
                "run_id": run_id,
                "agent_plan_id": plan_id,
                "plan_hash": run_row.get("plan_hash"),
                "plan_approval_id": plan_approval_id,
                "delivery_review_id": delivery_approval_id,
                "tool_call_id": tool_id,
                "evaluation_id": evaluation_id,
                "artifact_id": artifact_id,
                "plan_evidence_manifest_id": manifest_id,
                "operator_report_status": report_item.get("status"),
                "verification_pass": verification.get("pass"),
                "evidence_counts": counts,
                "review_queue_observed": True,
                "token_omitted": True,
            }
            require(not SECRET_RE.search("\n".join(outputs) + json.dumps(evidence_packet, ensure_ascii=False)), "safe closure evidence packet leaked token-like material", failures)
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
        "evidence_packet": evidence_packet,
        "secret_leaked": False if not SECRET_RE.search("\n".join(outputs)) else True,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
