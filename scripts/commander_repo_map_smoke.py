#!/usr/bin/env python3
"""Verify Commander repo-map localization is read-only, deterministic and redacted."""

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
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
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


def run_cli(base_url: str, query: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [str(CLI), "--base-url", base_url, "commander", "repo-map", "--query", query, "--limit", "8", "--char-budget", "4800"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def table_counts(db_path: Path) -> dict[str, int]:
    tables = ["tasks", "runs", "tool_calls", "runtime_events", "approvals", "artifacts", "evaluations", "audit_logs", "memories"]
    with sqlite3.connect(db_path) as conn:
        return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in tables}


def validate(payload: dict, failures: list[str]) -> None:
    require(payload.get("provider") == "agentops-commander", f"provider mismatch: {payload}", failures)
    require(payload.get("operation") == "repo_map", f"operation mismatch: {payload}", failures)
    require(payload.get("status") == "ready", f"repo-map should find files: {payload}", failures)
    require((payload.get("ranking") or {}).get("deterministic") is True, f"determinism proof missing: {payload}", failures)
    require((payload.get("safety") or {}).get("read_only") is True, f"read-only proof missing: {payload}", failures)
    require((payload.get("safety") or {}).get("ledger_mutated") is False, f"ledger mutation proof wrong: {payload}", failures)
    require((payload.get("safety") or {}).get("raw_file_bodies_returned") is False, f"raw body proof wrong: {payload}", failures)
    require(payload.get("token_omitted") is True, f"token omission proof missing: {payload}", failures)
    require(int(payload.get("used_chars_estimate") or 0) <= int(payload.get("char_budget") or 0), f"char budget exceeded: {payload}", failures)
    files = payload.get("files") or []
    paths = {item.get("path") for item in files}
    require("server.py" in paths or "agentops_mis_cli/agentops.py" in paths, f"expected implementation file missing: {paths}", failures)
    require(len(files) > 0, f"no localized files: {payload}", failures)
    for item in files:
        require(item.get("content_hash"), f"missing content hash: {item}", failures)
        require(item.get("source_provenance", {}).get("raw_content_returned") is False, f"raw content provenance wrong: {item}", failures)
        require(item.get("source_provenance", {}).get("token_omitted") is True, f"token omission missing in provenance: {item}", failures)
        require(not str(item.get("path") or "").startswith("node_modules/"), f"node_modules leaked into repo map: {item}", failures)


def validate_launch_packet(payload: dict, failures: list[str]) -> None:
    require(payload.get("operation") == "operator_loop_launch_packet", f"launch packet operation mismatch: {payload}", failures)
    repo_map = (payload.get("sources") or {}).get("repo_map") or {}
    require(repo_map.get("operation") == "repo_map", f"launch packet repo-map source missing: {payload}", failures)
    require("agentops commander repo-map" in str(repo_map.get("command") or ""), f"launch packet repo-map command missing: {repo_map}", failures)
    require((repo_map.get("safety") or {}).get("read_only") is True, f"launch packet repo-map read-only proof missing: {repo_map}", failures)
    require(repo_map.get("snippets_omitted") is True, f"launch packet should omit repo-map snippets: {repo_map}", failures)
    require(repo_map.get("raw_content_omitted") is True, f"launch packet should omit raw repo content: {repo_map}", failures)
    require(int(repo_map.get("selected_count") or 0) > 0, f"launch packet repo-map should select files: {repo_map}", failures)
    retrieve = next((item for item in payload.get("launch_sequence") or [] if item.get("phase") == "RETRIEVE"), {})
    retrieve_commands = retrieve.get("commands") or []
    require(any("agentops commander repo-map" in str(command) for command in retrieve_commands), f"RETRIEVE phase missing repo-map command: {retrieve}", failures)
    proposed_files = (payload.get("agent_plan_draft") or {}).get("proposed_files_to_change") or []
    require(proposed_files and proposed_files != ["<declare_before_execution>"], f"agent plan draft did not inherit repo-map files: {proposed_files}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    query = "commander_repo_map cmd_commander_repo_map Handler /api/commander/repo-map"
    with tempfile.TemporaryDirectory(prefix="agentops-repo-map-") as tmp:
        tmpdir = Path(tmp)
        db_path = tmpdir / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        server = start_server(db_path, port, tmpdir / "server.log")
        try:
            wait_for_server(base_url)
            before = table_counts(db_path)
            status, api_payload, raw_one = http_json(base_url, "/api/commander/repo-map", {"q": query, "limit": 8, "char_budget": 4800})
            status_two, api_payload_two, raw_two = http_json(base_url, "/api/commander/repo-map", {"q": query, "limit": 8, "char_budget": 4800})
            status_bad, api_payload_bad, raw_bad = http_json(base_url, "/api/commander/repo-map", {"q": query, "limit": "bad", "char_budget": "bad", "candidate_limit": "bad"})
            status_launch, launch_payload, raw_launch = http_json(base_url, "/api/operator/loop-launch-packet", {"q": query, "limit": 8})
            after = table_counts(db_path)
            outputs.extend([raw_one, raw_two, raw_bad, raw_launch])
            require(status == 200, f"API status mismatch: {status} {api_payload}", failures)
            require(status_two == 200, f"second API status mismatch: {status_two} {api_payload_two}", failures)
            require(status_bad == 200, f"bad query params should fall back to bounded defaults: {status_bad} {api_payload_bad}", failures)
            require(status_launch == 200, f"launch packet status mismatch: {status_launch} {launch_payload}", failures)
            validate(api_payload, failures)
            validate(api_payload_bad, failures)
            validate_launch_packet(launch_payload, failures)
            require(api_payload_bad.get("limit") == 12, f"bad limit should use default: {api_payload_bad}", failures)
            require(api_payload_bad.get("char_budget") == 8000, f"bad char_budget should use default: {api_payload_bad}", failures)
            require([item.get("path") for item in api_payload.get("files") or []] == [item.get("path") for item in api_payload_two.get("files") or []], "repo-map ranking is not deterministic", failures)
            require(before == after, f"repo-map/launch packet mutated ledger tables: {before} -> {after}", failures)

            proc = run_cli(base_url, query)
            outputs.extend([proc.stdout, proc.stderr])
            require(proc.returncode == 0, f"CLI repo-map failed: {proc.stderr or proc.stdout}", failures)
            cli_payload = json.loads(proc.stdout or "{}")
            validate(cli_payload, failures)
            require(not leaked("\n".join(outputs)), "repo-map output leaked token-like material", failures)
        finally:
            stop_server(server)

    print(json.dumps({
        "operation": "commander_repo_map_smoke",
        "ok": not failures,
        "failures": failures,
        "secret_leaked": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
