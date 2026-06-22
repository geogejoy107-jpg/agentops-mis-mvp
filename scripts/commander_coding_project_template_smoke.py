#!/usr/bin/env python3
"""Verify the Commander local coding project template is read-only and complete."""
from __future__ import annotations

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
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_server(db_path: Path, port: int, log_path: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
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
            with urllib.request.urlopen(base_url + "/api/agent-gateway/status", timeout=1.0) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def http_json(base_url: str, path: str, query: dict[str, str | int] | None = None) -> tuple[int, dict, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode("utf-8")
        return resp.status, json.loads(raw), raw


def run_cli(base_url: str, query: str, project_id: str, task_id: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [
            str(CLI),
            "--base-url",
            base_url,
            "commander",
            "coding-template",
            "--query",
            query,
            "--project-id",
            project_id,
            "--task-id",
            task_id,
            "--limit",
            "8",
            "--char-budget",
            "4800",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def table_counts(db_path: Path) -> dict[str, int]:
    tables = ["tasks", "runs", "tool_calls", "runtime_events", "approvals", "artifacts", "evaluations", "audit_logs", "memories", "workflow_jobs"]
    with sqlite3.connect(db_path) as conn:
        return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}


def validate(payload: dict, query: str, project_id: str, task_id: str, failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-commander", f"provider mismatch: {payload}", failures)
    require(payload.get("operation") == "coding_project_template", f"operation mismatch: {payload}", failures)
    require(payload.get("status") in {"ready", "attention"}, f"bad status: {payload}", failures)
    require(payload.get("query") == query, f"query mismatch: {payload.get('query')}", failures)
    require(payload.get("project_id") == project_id, f"project_id mismatch: {payload}", failures)
    require(payload.get("task_id") == task_id, f"task_id mismatch: {payload}", failures)
    template = payload.get("template") or {}
    require(template.get("template_id") == "tpl_local_coding_project_v1", f"template id missing: {template}", failures)
    require(template.get("scenario") == "local_coding_project", f"scenario missing: {template}", failures)
    require(template.get("loop_protocol") == ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"], f"loop protocol wrong: {template}", failures)
    contract = payload.get("work_package_contract") or {}
    require("agentops commander plan" in str(contract.get("plan_command") or ""), f"plan command missing: {contract}", failures)
    require(contract.get("localization_artifact_type") == "commander_repo_map_localization", f"localization contract missing: {contract}", failures)
    workspace = payload.get("workspace_contract") or {}
    commands = workspace.get("commands") or {}
    require(workspace.get("branch_name") == f"codex/{task_id}", f"branch name wrong: {workspace}", failures)
    require("git worktree add" in str(commands.get("create_worktree") or ""), f"worktree command missing: {workspace}", failures)
    require("diff --binary" in str(commands.get("capture_patch") or ""), f"patch command missing: {workspace}", failures)
    gate_ids = {item.get("id") for item in payload.get("evidence_gates") or []}
    for gate_id in ["clean_start", "repo_map_localization", "verified_agent_plan", "scoped_patch_artifact", "tests_pass", "plan_evidence_manifest_verified", "merge_gate"]:
        require(gate_id in gate_ids, f"gate missing: {gate_id} from {gate_ids}", failures)
    required_artifacts = set(payload.get("required_artifacts") or [])
    for artifact_type in ["commander_repo_map_localization", "agent_plan", "patch", "test_log", "verifier_report", "plan_evidence_manifest", "merge_gate_receipt"]:
        require(artifact_type in required_artifacts, f"required artifact missing: {artifact_type}", failures)
    repo_map = payload.get("repo_map_localization") or {}
    require(repo_map.get("operation") == "repo_map", f"repo-map source missing: {repo_map}", failures)
    require(int(repo_map.get("selected_count") or 0) > 0, f"repo-map selected no files: {repo_map}", failures)
    require(repo_map.get("raw_content_omitted") is True and repo_map.get("snippets_omitted") is True, f"repo-map omissions missing: {repo_map}", failures)
    require(repo_map.get("manifest_hash"), f"manifest hash missing: {repo_map}", failures)
    files = repo_map.get("files") or []
    require(files and all((item.get("raw_content_omitted") is True and item.get("token_omitted") is True) for item in files), f"unsafe file entries: {files}", failures)
    actions = " ".join(payload.get("recommended_next_actions") or [])
    require("agentops commander plan" in actions and "merge_readiness_status_smoke.py" in actions, f"recommended actions incomplete: {actions}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"read-only proof missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"ledger mutation proof wrong: {safety}", failures)
    require(safety.get("worktree_created") is False and safety.get("patch_created") is False, f"template must not create worktree/patch: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"template must not run live work: {safety}", failures)
    require(safety.get("repo_root_omitted") is True, f"repo root omission proof missing: {safety}", failures)
    require(payload.get("token_omitted") is True, "token omission proof missing", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    query = "P1-02 local coding project template WorkPackage worktree patch verifier merge gate"
    project_id = "proj_coding_template_smoke"
    task_id = "tsk_coding_template_smoke"
    with tempfile.TemporaryDirectory(prefix="agentops-coding-template-") as tmp:
        tmpdir = Path(tmp)
        db_path = tmpdir / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        server = start_server(db_path, port, tmpdir / "server.log")
        try:
            wait_for_server(base_url)
            before = table_counts(db_path)
            status, api_payload, raw_api = http_json(
                base_url,
                "/api/commander/coding-project-template",
                {"q": query, "project_id": project_id, "task_id": task_id, "limit": 8, "char_budget": 4800},
            )
            outputs.append(raw_api)
            require(status == 200, f"API status mismatch: {status} {api_payload}", failures)
            validate(api_payload, query, project_id, task_id, failures)
            cli = run_cli(base_url, query, project_id, task_id)
            outputs.extend([cli.stdout, cli.stderr])
            require(cli.returncode == 0, f"CLI failed: {cli.stderr or cli.stdout}", failures)
            try:
                cli_payload = json.loads(cli.stdout or "{}")
            except json.JSONDecodeError:
                cli_payload = {}
            validate(cli_payload, query, project_id, task_id, failures)
            after = table_counts(db_path)
            require(before == after, f"coding template mutated ledger tables: {before} -> {after}", failures)
            require(not leaked("\n".join(outputs)), "coding template output leaked token-like material", failures)
        finally:
            stop_server(server)

    print(json.dumps({
        "operation": "commander_coding_project_template_smoke",
        "ok": not failures,
        "failures": failures,
        "secret_leaked": leaked("\n".join(outputs)),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
