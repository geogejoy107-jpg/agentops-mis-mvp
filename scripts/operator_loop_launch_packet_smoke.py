#!/usr/bin/env python3
"""Verify the read-only Agent Work Method launch packet API and CLI."""

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
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_API_KEY=", re.IGNORECASE),
]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str, query: dict | None = None) -> tuple[int, dict]:
    suffix = f"?{urlencode(query or {})}" if query else ""
    req = Request(base_url.rstrip("/") + path + suffix, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=45) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def run_cli(base_url: str, args: list[str], env: dict) -> subprocess.CompletedProcess[str]:
    cli_env = env.copy()
    cli_env["AGENTOPS_BASE_URL"] = base_url
    return subprocess.run(
        [str(CLI), *args],
        cwd=ROOT,
        env=cli_env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def load_json(raw: str) -> dict:
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _ = http_json(base_url, "/api/operator/loop-launch-packet", {"limit": 1})
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def db_fingerprint(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        tables = [
            "tasks",
            "runs",
            "tool_calls",
            "memories",
            "approvals",
            "agent_plans",
            "plan_evidence_manifests",
            "audit_logs",
            "runtime_events",
            "knowledge_documents",
        ]
        result = {}
        for table in tables:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                result[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        return result
    finally:
        conn.close()


def leaked(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def validate_packet(payload: dict, label: str, task_id: str, agent_id: str, failures: list[str]) -> None:
    require(payload.get("operation") == "operator_loop_launch_packet", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("method") == "READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD", f"{label} method mismatch: {payload}", failures)
    require(payload.get("task_id") == task_id, f"{label} task mismatch: {payload.get('task_id')} != {task_id}", failures)
    require(payload.get("agent_id") == agent_id, f"{label} agent mismatch: {payload.get('agent_id')} != {agent_id}", failures)
    require(payload.get("token_omitted") is True, f"{label} token omission missing: {payload}", failures)
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} read_only missing: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"{label} should not mutate ledger: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"{label} should not execute live work: {safety}", failures)
    phases = [item.get("phase") for item in payload.get("launch_sequence") or []]
    require(phases == ["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"], f"{label} phases wrong: {phases}", failures)
    draft = payload.get("agent_plan_draft") or {}
    for key in [
        "task_understanding",
        "referenced_specs",
        "referenced_memories",
        "referenced_bases",
        "proposed_files_to_change",
        "risk_level",
        "approval_required",
        "execution_steps",
        "verification_plan",
        "rollback_plan",
    ]:
        require(key in draft, f"{label} draft missing {key}: {draft}", failures)
    require("PROJECT_SPEC.md" in (draft.get("referenced_specs") or []), f"{label} draft missing project spec: {draft}", failures)
    require("base_local_memory" in (draft.get("referenced_bases") or []), f"{label} draft missing memory base: {draft}", failures)
    commands = payload.get("commands") or []
    joined = "\n".join(commands)
    require("agentops agent-plan create" in joined, f"{label} missing agent-plan create command: {commands}", failures)
    require("agentops agent-plan verify" in joined, f"{label} missing plan verify command: {commands}", failures)
    require("agentops knowledge search" in joined, f"{label} missing knowledge search command: {commands}", failures)
    require("agentops operator loop-self-check" in joined, f"{label} missing loop self-check command: {commands}", failures)
    require("agentops plan-evidence create" in joined, f"{label} missing plan evidence command: {commands}", failures)
    sources = payload.get("sources") or {}
    require((sources.get("intake") or {}).get("operation") == "task_intake_checklist", f"{label} missing intake source: {sources}", failures)
    require((sources.get("knowledge_search") or {}).get("operation") == "knowledge_search", f"{label} missing knowledge source: {sources}", failures)
    require((sources.get("handoff") or {}).get("operation") == "operator_handoff", f"{label} missing handoff source: {sources}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    stamp = now_stamp()
    agent_id = f"agt_loop_launch_{stamp}"
    task_id = f"tsk_loop_launch_{stamp}"
    with tempfile.TemporaryDirectory(prefix="agentops-loop-launch-packet-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env["AGENTOPS_BASE_URL"] = base_url
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
            for args in [
                ["knowledge", "index", "--rebuild"],
                ["agent", "register", "--id", agent_id, "--name", f"Loop Launch {stamp}", "--role", "Builder", "--runtime", "codex"],
                [
                    "task",
                    "create",
                    "--task-id",
                    task_id,
                    "--title",
                    "Loop launch packet smoke task",
                    "--description",
                    "Verify a read-only packet can guide the next agent loop.",
                    "--owner-agent-id",
                    agent_id,
                    "--requester-id",
                    "usr_founder",
                    "--acceptance",
                    "Launch packet must include method phases, plan draft, retrieval, compare, verify and record commands.",
                    "--risk",
                    "medium",
                ],
            ]:
                proc_cli = run_cli(base_url, args, env)
                outputs.extend([proc_cli.stdout, proc_cli.stderr])
                require(proc_cli.returncode == 0, f"CLI setup failed for {args}: {proc_cli.stderr or proc_cli.stdout}", failures)
            before = db_fingerprint(db_path)
            status, api_payload = http_json(
                base_url,
                "/api/operator/loop-launch-packet",
                {"task_id": task_id, "agent_id": agent_id, "limit": 8, "q": "Agent Work Method Block"},
            )
            outputs.append(json.dumps(api_payload, ensure_ascii=False))
            require(status == 200, f"API status mismatch: {status} {api_payload}", failures)
            validate_packet(api_payload, "api", task_id, agent_id, failures)
            cli_proc = run_cli(
                base_url,
                ["operator", "loop-launch-packet", "--task-id", task_id, "--agent-id", agent_id, "--limit", "8", "--query", "Agent Work Method Block"],
                env,
            )
            outputs.extend([cli_proc.stdout, cli_proc.stderr])
            cli_payload = load_json(cli_proc.stdout)
            require(cli_proc.returncode == 0, f"CLI launch packet failed: {cli_proc.stderr or cli_proc.stdout}", failures)
            validate_packet(cli_payload, "cli", task_id, agent_id, failures)
            after = db_fingerprint(db_path)
            require(before == after, f"launch packet changed database fingerprint: {before} -> {after}", failures)
            require(not leaked("\n".join(outputs)), "loop launch packet leaked token-like material", failures)
        finally:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])
    result = {
        "ok": not failures,
        "operation": "operator_loop_launch_packet_smoke",
        "failures": failures,
        "secret_leaked": leaked("\n".join(outputs)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or result["secret_leaked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
