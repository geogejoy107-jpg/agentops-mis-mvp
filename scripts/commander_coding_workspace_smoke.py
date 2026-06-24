#!/usr/bin/env python3
"""Verify Commander coding worktree prepare, evidence collection and cleanup."""
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
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(db_path: Path, port: int, worktree_root: Path, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
    env["AGENTOPS_CODING_WORKTREE_ROOT"] = str(worktree_root)
    log_fh = log_path.open("w", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port), "--reset", "--serve"],
        cwd=ROOT,
        env=env,
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        text=True,
    )
    proc._agentops_log_fh = log_fh  # type: ignore[attr-defined]
    return proc


def stop_server(proc: subprocess.Popen) -> None:
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=8)
    log_fh = getattr(proc, "_agentops_log_fh", None)
    if log_fh:
        log_fh.close()


def wait_for_server(base_url: str, timeout: float = 45.0) -> None:
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            with urlopen(base_url + "/api/agent-gateway/status", timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def http_json(base_url: str, method: str, path: str, payload: dict | None = None, timeout: int = 180) -> tuple[int, dict]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach MIS server: {exc.reason}") from exc


def run_cli(base_url: str, worktree_root: Path, args: list[str], timeout: int = 180) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_CODING_WORKTREE_ROOT"] = str(worktree_root)
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def load_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return {}


def count_rows(db_path: Path, sql: str, params=()) -> int:
    with sqlite3.connect(db_path) as conn:
        return int((conn.execute(sql, params).fetchone() or [0])[0] or 0)


def cleanup_git_worktree(worktree_path: Path, branch: str) -> None:
    subprocess.run(["git", "worktree", "remove", "--force", str(worktree_path)], cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    subprocess.run(["git", "worktree", "prune"], cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    subprocess.run(["git", "branch", "-D", branch], cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)


def main() -> int:
    suffix = stamp()
    project_id = f"proj_coding_workspace_{suffix}"
    plan_id = f"cmdplan_coding_workspace_{suffix}"
    task_id = ""
    branch = ""
    failures: list[str] = []
    transcripts: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-coding-workspace-") as tmp:
        tmpdir = Path(tmp)
        db_path = tmpdir / "agentops_mis.db"
        worktree_root = tmpdir / "worktrees"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        server = start_server(db_path, port, worktree_root, tmpdir / "server.log")
        try:
            wait_for_server(base_url)
            status, created = http_json(base_url, "POST", "/api/commander/work-packages/plan", {
                "project_id": project_id,
                "plan_id": plan_id,
                "goal": "Verify the local coding worktree, patch, tests and merge-gate evidence loop.",
                "max_packages": 1,
                "confirm_create": True,
                "lanes": [{
                    "lane_id": "workspace",
                    "title": "Prepare coding workspace and verifier evidence",
                    "owner_agent_id": "agt_builder",
                    "priority": "high",
                    "risk_level": "medium",
                    "scope": "coding worktree, patch manifest, test log, verifier report, merge gate receipt",
                    "avoid_scope": "do not merge, push, store raw patch, or execute live runtime",
                    "verification": ["git diff --check", "python3 -m py_compile server.py agentops_mis_cli/*.py agentops_mis_core/*.py agentops_mis_runtime/*.py scripts/*.py"],
                }],
            })
            transcripts.append(json.dumps(created, ensure_ascii=False))
            require(status == 201, f"plan create failed: {status} {created}", failures)
            task_ids = created.get("created_task_ids") or []
            require(len(task_ids) == 1, f"expected one task: {created}", failures)
            task_id = task_ids[0]
            branch = f"codex/coding-workspace-smoke-{suffix}"
            worktree_path = worktree_root / task_id

            dispatch_status, dispatch = http_json(base_url, "POST", f"/api/commander/work-packages/{task_id}/dispatch", {"adapter": "mock"}, timeout=220)
            transcripts.append(json.dumps(dispatch, ensure_ascii=False))
            run_id = dispatch.get("run_id")
            require(dispatch_status == 201 and dispatch.get("ok") is True and run_id, f"dispatch failed: {dispatch_status} {dispatch}", failures)

            preview = run_cli(base_url, worktree_root, ["commander", "coding-workspace", "--task-id", task_id])
            transcripts.extend([preview.stdout, preview.stderr])
            preview_payload = load_json(preview)
            require(preview.returncode == 0 and preview_payload.get("dry_run") is True, f"workspace preview failed: {preview.stderr or preview.stdout}", failures)
            require((preview_payload.get("safety") or {}).get("worktree_created") is False, f"preview created worktree: {preview_payload}", failures)

            prepare = run_cli(base_url, worktree_root, ["commander", "coding-workspace", "--task-id", task_id, "--branch", branch, "--confirm-create"], timeout=220)
            transcripts.extend([prepare.stdout, prepare.stderr])
            prepare_payload = load_json(prepare)
            require(prepare.returncode == 0, f"workspace create CLI failed: {prepare.stderr or prepare.stdout}", failures)
            require(prepare_payload.get("operation") == "coding_workspace_prepare" and prepare_payload.get("dry_run") is False, f"workspace create wrong payload: {prepare_payload}", failures)
            require((prepare_payload.get("safety") or {}).get("worktree_created") is True, f"workspace not marked created: {prepare_payload}", failures)
            require(worktree_path.exists(), f"worktree path missing: {worktree_path}", failures)

            marker_path = worktree_path / "docs" / "COMMANDER_WORK_PACKAGE_PLANNER.md"
            marker_path.write_text(marker_path.read_text(encoding="utf-8") + f"\n<!-- coding workspace smoke {suffix} -->\n", encoding="utf-8")

            evidence = run_cli(base_url, worktree_root, [
                "commander",
                "coding-evidence",
                "--task-id",
                task_id,
                "--run-id",
                str(run_id),
                "--branch",
                branch,
                "--collect-from-worktree",
                "--confirm-record",
            ], timeout=240)
            transcripts.extend([evidence.stdout, evidence.stderr])
            evidence_payload = load_json(evidence)
            require(evidence.returncode == 0, f"coding evidence CLI failed: {evidence.stderr or evidence.stdout}", failures)
            artifact_ids = evidence_payload.get("artifact_ids") or []
            artifact_types = evidence_payload.get("artifact_types") or []
            require(evidence_payload.get("dry_run") is False and len(artifact_ids) == 5, f"coding evidence artifacts wrong: {evidence_payload}", failures)
            require("commander_worktree_workspace" in artifact_types, f"workspace evidence type missing: {evidence_payload}", failures)
            require(((evidence_payload.get("collection") or {}).get("changed_files_count") or 0) >= 1, f"worktree changed files not collected: {evidence_payload}", failures)
            require((evidence_payload.get("collection") or {}).get("patch_hash"), f"patch hash missing: {evidence_payload}", failures)
            require((evidence_payload.get("evaluation") or {}).get("pass_fail") == "pass", f"coding evidence eval did not pass: {evidence_payload}", failures)

            read_status, readback = http_json(base_url, "GET", f"/api/commander/work-packages?project_id={project_id}&limit=5")
            transcripts.append(json.dumps(readback, ensure_ascii=False))
            require(read_status == 200, f"readback failed: {read_status} {readback}", failures)
            package = (readback.get("work_packages") or [{}])[0]
            coding_gate = package.get("coding_evidence_gate") or {}
            require(coding_gate.get("status") == "recorded", f"coding evidence gate not recorded: {coding_gate}", failures)
            require((readback.get("summary", {}).get("coding_evidence") or {}).get("coverage_percent") == 100.0, f"coding evidence summary incomplete: {readback}", failures)

            artifacts = count_rows(db_path, "SELECT COUNT(*) FROM artifacts WHERE task_id=? AND artifact_type IN ('commander_worktree_workspace','commander_patch_manifest','commander_test_log','commander_verifier_report','commander_merge_gate_receipt')", (task_id,))
            evaluations = count_rows(db_path, "SELECT COUNT(*) FROM evaluations WHERE task_id=? AND evaluator_type='rule'", (task_id,))
            runtime_events = count_rows(db_path, "SELECT COUNT(*) FROM runtime_events WHERE task_id=? AND event_type LIKE 'commander.coding_%'", (task_id,))
            require(artifacts >= 5, f"missing coding artifacts: {artifacts}", failures)
            require(evaluations >= 1, f"missing coding evaluation: {evaluations}", failures)
            require(runtime_events >= 2, f"missing coding runtime events: {runtime_events}", failures)

            cleanup = run_cli(base_url, worktree_root, ["commander", "coding-workspace-cleanup", "--task-id", task_id, "--branch", branch, "--confirm-cleanup"], timeout=180)
            transcripts.extend([cleanup.stdout, cleanup.stderr])
            cleanup_payload = load_json(cleanup)
            require(cleanup.returncode == 0, f"cleanup CLI failed: {cleanup.stderr or cleanup.stdout}", failures)
            require((cleanup_payload.get("safety") or {}).get("worktree_removed") is True, f"cleanup did not remove worktree: {cleanup_payload}", failures)
            require(not worktree_path.exists(), f"worktree still exists after cleanup: {worktree_path}", failures)
            branch_probe = subprocess.run(["git", "show-ref", "--verify", f"refs/heads/{branch}"], cwd=ROOT, capture_output=True, text=True, timeout=20, check=False)
            require(branch_probe.returncode != 0, f"branch still exists after cleanup: {branch}", failures)
            require(not leaked_secret("\n".join(transcripts)), "coding workspace output leaked token-like material", failures)
        except Exception as exc:
            failures.append(str(exc))
        finally:
            stop_server(server)
            if task_id:
                cleanup_git_worktree(worktree_root / task_id, branch or f"codex/{task_id}")

    print(json.dumps({
        "operation": "commander_coding_workspace_smoke",
        "ok": not failures,
        "project_id": project_id,
        "plan_id": plan_id,
        "task_id": task_id,
        "secret_leaked": leaked_secret("\n".join(transcripts)),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
