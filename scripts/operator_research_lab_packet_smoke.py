#!/usr/bin/env python3
"""Verify the read-only Research Lab packet API and CLI."""

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
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
LAB_ROOT = ROOT / "incubator" / "research-lab"
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


def run_cli(base_url: str, env: dict, args: list[str]) -> subprocess.CompletedProcess[str]:
    cli_env = env.copy()
    cli_env["AGENTOPS_BASE_URL"] = base_url
    cli_env.pop("AGENTOPS_API_KEY", None)
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
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _ = http_json(base_url, "/api/operator/research-lab-packet", {"limit": 1})
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def wait_external_ready(base_url: str) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        try:
            status, _ = http_json(base_url, "/api/operator/research-lab-packet", {"limit": 1})
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
            "artifacts",
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


def validate_packet(payload: dict, label: str, adapter: str, failures: list[str]) -> None:
    require(payload.get("operation") == "operator_research_lab_packet", f"{label} operation mismatch: {payload}", failures)
    require(payload.get("schema_version") == "research_lab_agent_work_packet_v1", f"{label} schema mismatch: {payload}", failures)
    require(payload.get("method") == "READ -> PLAN -> RETRIEVE -> COMPARE -> EXECUTE -> VERIFY -> RECORD", f"{label} method mismatch: {payload}", failures)
    require(payload.get("adapter") == adapter, f"{label} adapter mismatch: {payload}", failures)
    require(payload.get("status") == "ready", f"{label} packet not ready: {payload}", failures)
    require(bool(payload.get("packet_hash")), f"{label} packet hash missing: {payload}", failures)
    safety = payload.get("safety") or {}
    for key in [
        "read_only",
        "raw_prompt_omitted",
        "raw_response_omitted",
        "raw_content_omitted",
        "credentials_omitted",
        "token_omitted",
    ]:
        require(safety.get(key) is True, f"{label} safety missing {key}: {safety}", failures)
    for key in [
        "ledger_mutated",
        "live_execution_performed",
        "server_executes_shell",
        "ssh_command_executed",
        "network_probe_performed",
    ]:
        require(safety.get(key) is False, f"{label} safety should be false for {key}: {safety}", failures)
    projection = payload.get("server_projection") or {}
    require(projection.get("server_executes_shell") is False, f"{label} server projection shell boundary missing: {projection}", failures)
    require(projection.get("ledger_mutated") is False, f"{label} server projection mutated ledger: {projection}", failures)
    approval = payload.get("approval_boundary") or {}
    require(approval.get("local_spec_validation_requires_approval") is False, f"{label} local validation approval boundary wrong: {approval}", failures)
    require(approval.get("real_ssh_execution_requires_approval") is True, f"{label} SSH approval boundary missing: {approval}", failures)
    require(approval.get("credential_use_requires_approval") is True, f"{label} credential approval boundary missing: {approval}", failures)
    research_lab = payload.get("research_lab") or {}
    require(research_lab.get("root") == "incubator/research-lab", f"{label} root missing: {research_lab}", failures)
    docs = research_lab.get("docs") or []
    examples = research_lab.get("examples") or []
    require(any(item.get("path") == "docs/AGENT_PLAN.md" and item.get("exists") and item.get("sha256") for item in docs), f"{label} missing AGENT_PLAN doc metadata: {docs}", failures)
    require(any(item.get("path") == "docs/SSH_EXECUTOR.md" and item.get("exists") and item.get("sha256") for item in docs), f"{label} missing SSH_EXECUTOR doc metadata: {docs}", failures)
    confirmatory = next((item for item in examples if item.get("path") == "examples/confirmatory_experiment.json"), {})
    ssh_spec = next((item for item in examples if item.get("path") == "examples/ssh_experiment.json"), {})
    registry = next((item for item in examples if item.get("path") == "examples/servers.example.json"), {})
    require(confirmatory.get("executor") == "local", f"{label} confirmatory summary wrong: {confirmatory}", failures)
    require(confirmatory.get("trial_count") == 2, f"{label} confirmatory trial count wrong: {confirmatory}", failures)
    require(confirmatory.get("protocol_hash") and confirmatory.get("provenance_hash"), f"{label} confirmatory hashes missing: {confirmatory}", failures)
    require(ssh_spec.get("executor") == "ssh" and ssh_spec.get("profile") == "lab-gpu-01", f"{label} ssh spec summary wrong: {ssh_spec}", failures)
    require(ssh_spec.get("raw_command_omitted") is True, f"{label} ssh spec leaked command: {ssh_spec}", failures)
    require(registry.get("kind") == "server_registry", f"{label} registry summary missing: {registry}", failures)
    require(registry.get("raw_credentials_omitted") is True and registry.get("raw_hosts_omitted") is True, f"{label} registry omission missing: {registry}", failures)
    profiles = registry.get("profiles") or []
    require(bool(profiles), f"{label} registry profiles missing: {registry}", failures)
    require(all(item.get("identity_file_omitted") is True and item.get("raw_host_omitted") is True for item in profiles), f"{label} registry profile leaked sensitive refs: {profiles}", failures)
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
    require(draft.get("approval_required") is True, f"{label} draft should preserve SSH approval gate: {draft}", failures)
    phases = payload.get("phase_commands") or {}
    require(set(["READ", "PLAN", "RETRIEVE", "COMPARE", "EXECUTE", "VERIFY", "RECORD"]).issubset(set(phases)), f"{label} phase commands incomplete: {phases}", failures)
    joined = "\n".join(str(item) for item in list(phases.values()) + [lane.get("command") for lane in (payload.get("command_lanes") or []) if isinstance(lane, dict)])
    for expected in [
        "agentops operator research-lab-packet",
        "python3 -m research_lab inventory",
        "python3 -m research_lab validate-spec --spec examples/confirmatory_experiment.json",
        "python3 -m research_lab validate-spec --spec examples/ssh_experiment.json --servers examples/servers.example.json",
        "python3 -m research_lab server-list --servers examples/servers.example.json",
        "python3 scripts/operator_research_lab_packet_smoke.py",
    ]:
        require(expected in joined, f"{label} missing command {expected}: {joined}", failures)
    payload_text = json.dumps(payload)
    require("~/.ssh/id_research_lab" not in payload_text, f"{label} leaked raw identity file path", failures)
    require("gpu01.example.org" not in payload_text, f"{label} leaked raw host", failures)
    require("/srv/agentops-research-lab" not in payload_text, f"{label} leaked raw remote root", failures)
    require(not leaked(json.dumps(payload)), f"{label} leaked secret-like text", failures)


def run_research_lab_command(args: list[str], failures: list[str]) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "research_lab", *args],
        cwd=LAB_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    require(proc.returncode == 0, f"research_lab command failed {args}: stdout={proc.stdout} stderr={proc.stderr}", failures)
    require(not leaked(proc.stdout + proc.stderr), f"research_lab command leaked secret-like text {args}", failures)


def exercise(base_url: str, env: dict, failures: list[str]) -> None:
    status, api_payload = http_json(base_url, "/api/operator/research-lab-packet", {"adapter": "openclaw", "limit": 8, "profile": "lab-gpu-01"})
    require(status == 200, f"API status {status}: {api_payload}", failures)
    validate_packet(api_payload, "api", "openclaw", failures)
    cli = run_cli(base_url, env, ["operator", "research-lab-packet", "--adapter", "hermes", "--limit", "8", "--profile", "lab-gpu-01"])
    require(cli.returncode == 0, f"CLI failed: stdout={cli.stdout} stderr={cli.stderr}", failures)
    cli_payload = load_json(cli.stdout)
    validate_packet(cli_payload, "cli", "hermes", failures)
    require(not leaked(cli.stdout + cli.stderr), "CLI leaked secret-like text", failures)
    run_research_lab_command(["validate-spec", "--spec", "examples/confirmatory_experiment.json"], failures)
    run_research_lab_command(["validate-spec", "--spec", "examples/ssh_experiment.json", "--servers", "examples/servers.example.json"], failures)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="")
    args = parser.parse_args()
    failures: list[str] = []
    if args.base_url:
        env = os.environ.copy()
        base_url = args.base_url.rstrip("/")
        wait_external_ready(base_url)
        exercise(base_url, env, failures)
    else:
        with tempfile.TemporaryDirectory(prefix="agentops-research-lab-packet-") as tmp:
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
                before = db_fingerprint(db_path)
                exercise(base_url, env, failures)
                after = db_fingerprint(db_path)
                require(before == after, f"Research Lab packet mutated ledger: before={before} after={after}", failures)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
    if failures:
        print(json.dumps({"ok": False, "failures": failures}, indent=2, ensure_ascii=False))
        return 1
    print(json.dumps({"ok": True, "operation": "operator_research_lab_packet_smoke", "stamp": now_stamp()}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
