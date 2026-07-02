#!/usr/bin/env python3
"""Verify Commander lane packets are machine-readable, safe, and read-only."""
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
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[opsu]_[A-Za-z0-9_]+"),
]
LEDGER_TABLES = [
    "agents",
    "tasks",
    "runs",
    "runtime_events",
    "tool_calls",
    "evaluations",
    "audit_logs",
    "artifacts",
    "approvals",
    "memories",
    "workflow_jobs",
]
REQUIRED_PACKET_KEYS = {
    "packet_kind",
    "packet_version",
    "workspace_id",
    "project_id",
    "plan_id",
    "lane_id",
    "task_id",
    "objective",
    "owner",
    "runtime",
    "phase",
    "run_id",
    "blocked_reason",
    "next_command",
    "verification_command",
    "verification_commands",
    "evidence_refs",
    "evidence_counts",
    "claim_limit",
    "packet_hash",
    "allowed_commands",
    "forbidden_actions",
    "required_gates",
    "safety",
    "token_omitted",
    "live_execution_performed",
}


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


def http_json(
    base_url: str,
    method: str,
    path: str,
    payload: dict | None = None,
    query: dict[str, str | int] | None = None,
    timeout: int = 90,
) -> tuple[int, dict, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}, raw
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw), raw
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}, raw


def run_cli(base_url: str, project_id: str, limit: int = 10) -> subprocess.CompletedProcess[str]:
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
            "lane-packets",
            "--project-id",
            project_id,
            "--limit",
            str(limit),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=90,
        check=False,
    )


def table_counts(db_path: Path) -> dict[str, int]:
    with sqlite3.connect(db_path) as conn:
        return {table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]) for table in LEDGER_TABLES}


def validate_bundle(payload: dict, project_id: str, expected_count: int, failures: list[str]) -> list[dict]:
    require(payload.get("provider") == "agentops-commander", f"provider mismatch: {payload}", failures)
    require(payload.get("operation") == "commander_lane_packets", f"operation mismatch: {payload}", failures)
    require(payload.get("schema_version") == "commander_lane_packet_bundle_v1", f"schema mismatch: {payload}", failures)
    require(payload.get("status") == "ready", f"bundle should be ready: {payload}", failures)
    require((payload.get("filter") or {}).get("project_id") == project_id, f"project filter mismatch: {payload}", failures)
    require((payload.get("summary") or {}).get("packet_count") == expected_count, f"packet count mismatch: {payload}", failures)
    require((payload.get("summary") or {}).get("all_read_only") is True, f"summary read-only proof missing: {payload}", failures)
    require((payload.get("summary") or {}).get("all_tokens_omitted") is True, f"summary token proof missing: {payload}", failures)
    safety = payload.get("safety") or {}
    for key in ["read_only", "raw_prompt_omitted", "raw_response_omitted", "raw_source_omitted", "token_omitted"]:
        require(safety.get(key) is True, f"safety flag {key} missing: {safety}", failures)
    for key in ["ledger_mutated", "task_created", "run_created", "live_execution_performed"]:
        require(safety.get(key) is False, f"safety flag {key} should be false: {safety}", failures)
    packets = payload.get("lane_packets") or []
    require(len(packets) == expected_count, f"lane packet length mismatch: {packets}", failures)
    phases = {packet.get("phase") for packet in packets}
    require("PLAN" in phases, f"planned package phase missing: {phases}", failures)
    require("VERIFY" in phases, f"review package phase missing after mock dispatch: {phases}", failures)
    for packet in packets:
        missing = REQUIRED_PACKET_KEYS - set(packet)
        require(not missing, f"packet missing keys {sorted(missing)}: {packet}", failures)
        require(packet.get("packet_kind") == "commander_lane_packet", f"packet kind wrong: {packet}", failures)
        require(packet.get("packet_version") == "commander_lane_packet_v1", f"packet version wrong: {packet}", failures)
        require(packet.get("project_id") == project_id, f"packet project mismatch: {packet}", failures)
        require(str(packet.get("packet_hash") or "").startswith("sha256:"), f"packet hash missing: {packet}", failures)
        require(packet.get("token_omitted") is True, f"packet token proof missing: {packet}", failures)
        require(packet.get("live_execution_performed") is False, f"packet marked live: {packet}", failures)
        packet_safety = packet.get("safety") or {}
        require(packet_safety.get("read_only") is True, f"packet read-only proof missing: {packet}", failures)
        require(packet_safety.get("ledger_mutated") is False, f"packet ledger mutation flag wrong: {packet}", failures)
        require(packet_safety.get("raw_prompt_omitted") is True, f"packet prompt omission missing: {packet}", failures)
        require(packet_safety.get("raw_response_omitted") is True, f"packet response omission missing: {packet}", failures)
        require(packet_safety.get("raw_source_omitted") is True, f"packet source omission missing: {packet}", failures)
        require(packet_safety.get("token_omitted") is True, f"packet token omission missing: {packet}", failures)
        require("do_not_scrape_browser_ui" in (packet.get("forbidden_actions") or []), f"browser scrape guard missing: {packet}", failures)
        require("do_not_run_live_adapter_without_confirm_run_or_approval" in (packet.get("forbidden_actions") or []), f"live confirm guard missing: {packet}", failures)
        require(bool(packet.get("next_command")), f"next command missing: {packet}", failures)
        require(bool(packet.get("verification_command")), f"verification command missing: {packet}", failures)
        require(bool(packet.get("objective")), f"objective missing: {packet}", failures)
        require(any(ref.get("type") == "task" and ref.get("id") == packet.get("task_id") for ref in packet.get("evidence_refs") or []), f"task evidence ref missing: {packet}", failures)
        require(str(packet.get("claim_limit") or "").find("no raw prompts") >= 0, f"claim limit missing raw prompt boundary: {packet}", failures)
    return packets


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-lane-packet-") as tmp:
        tmpdir = Path(tmp)
        db_path = tmpdir / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        server = start_server(db_path, port, tmpdir / "server.log")
        project_id = f"proj_lane_packet_smoke_{int(time.time() * 1000)}"
        plan_id = f"plan_lane_packet_smoke_{int(time.time() * 1000)}"
        try:
            wait_for_server(base_url)
            create_status, created, raw_create = http_json(base_url, "POST", "/api/commander/work-packages/plan", {
                "project_id": project_id,
                "plan_id": plan_id,
                "goal": "Coordinate AgentOps MIS implementation lanes with machine-readable work packets.",
                "max_packages": 2,
                "confirm_create": True,
            })
            outputs.append(raw_create)
            require(create_status == 201, f"create failed: {create_status} {created}", failures)
            task_ids = created.get("created_task_ids") or []
            require(len(task_ids) == 2, f"expected two task ids: {created}", failures)
            if len(task_ids) == 2:
                dispatch_status, dispatched, raw_dispatch = http_json(
                    base_url,
                    "POST",
                    f"/api/commander/work-packages/{task_ids[0]}/dispatch",
                    {"adapter": "mock", "confirm_run": False},
                    timeout=180,
                )
                outputs.append(raw_dispatch)
                require(dispatch_status == 201, f"mock dispatch failed: {dispatch_status} {dispatched}", failures)
                require(dispatched.get("live_execution_performed") is False, f"mock dispatch marked live: {dispatched}", failures)

            before_readback = table_counts(db_path)
            api_status, api_payload, raw_api = http_json(
                base_url,
                "GET",
                "/api/commander/lane-packets",
                query={"project_id": project_id, "limit": 10},
            )
            after_api_readback = table_counts(db_path)
            outputs.append(raw_api)
            require(api_status == 200, f"lane packet API failed: {api_status} {api_payload}", failures)
            api_packets = validate_bundle(api_payload, project_id, 2, failures)
            require(before_readback == after_api_readback, f"API lane packet readback mutated DB: {before_readback} -> {after_api_readback}", failures)

            cli = run_cli(base_url, project_id, limit=10)
            outputs.extend([cli.stdout, cli.stderr])
            require(cli.returncode == 0, f"CLI lane packet failed: {cli.stderr or cli.stdout}", failures)
            try:
                cli_payload = json.loads(cli.stdout or "{}")
            except json.JSONDecodeError:
                cli_payload = {}
            cli_packets = validate_bundle(cli_payload, project_id, 2, failures)
            after_cli_readback = table_counts(db_path)
            require(after_api_readback == after_cli_readback, f"CLI lane packet readback mutated DB: {after_api_readback} -> {after_cli_readback}", failures)

            api_hashes = {packet.get("task_id"): packet.get("packet_hash") for packet in api_packets}
            cli_hashes = {packet.get("task_id"): packet.get("packet_hash") for packet in cli_packets}
            require(api_hashes == cli_hashes, f"API/CLI packet hashes differ: api={api_hashes} cli={cli_hashes}", failures)
            require(not leaked("\n".join(outputs)), "lane packet output leaked token-like material", failures)
        except Exception as exc:
            failures.append(str(exc))
        finally:
            stop_server(server)

    print(json.dumps({
        "operation": "commander_lane_packet_smoke",
        "ok": not failures,
        "failures": failures,
        "secret_leaked": leaked("\n".join(outputs)),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
