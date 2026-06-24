#!/usr/bin/env python3
"""Verify local MIS runtime identity and current-code fail-closed checks."""
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
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def git_head() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10, check=False)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def http_json(base_url: str, path: str) -> tuple[int, dict, str]:
    req = Request(base_url.rstrip("/") + path, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=30) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}, raw
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw), raw
        except Exception:
            return exc.code, {"raw": raw}, raw


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _payload, _raw = http_json(base_url, "/api/agent-gateway/status")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def run_cli(base_url: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [str(CLI), "--base-url", base_url, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def load_cli_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"stdout": proc.stdout, "stderr": proc.stderr}


def assert_runtime_identity(payload: dict, expected_head: str, failures: list[str]) -> None:
    runtime = payload.get("running_instance") or {}
    require(runtime.get("operation") == "running_instance_identity", f"runtime identity missing: {payload}", failures)
    require(runtime.get("status") == "current", f"runtime should be current: {runtime}", failures)
    require(runtime.get("current") is True, f"runtime current flag missing: {runtime}", failures)
    require(runtime.get("server_started_after_source_mtime") is True, f"server/source freshness missing: {runtime}", failures)
    require(runtime.get("git_head_sha") == expected_head, f"git head mismatch: {runtime}", failures)
    require(bool(runtime.get("latest_source_path")), f"latest source path missing: {runtime}", failures)
    require((runtime.get("safety") or {}).get("read_only") is True, f"runtime safety missing: {runtime}", failures)
    require((runtime.get("safety") or {}).get("external_network") is False, f"runtime should not use external network: {runtime}", failures)
    require(runtime.get("token_omitted") is True, f"runtime token omission missing: {runtime}", failures)


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    expected_head = git_head()
    require(bool(expected_head), "could not resolve git HEAD", failures)
    with tempfile.TemporaryDirectory(prefix="agentops-runtime-identity-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
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
            status, gateway, raw = http_json(base_url, "/api/agent-gateway/status")
            outputs.append(raw)
            require(status == 200, f"gateway status failed: {status} {gateway}", failures)
            assert_runtime_identity(gateway, expected_head, failures)

            status, readiness, raw = http_json(base_url, "/api/local/readiness")
            outputs.append(raw)
            require(status == 200, f"local readiness failed: {status} {readiness}", failures)
            assert_runtime_identity(readiness, expected_head, failures)
            gate = next((item for item in readiness.get("gates") or [] if item.get("id") == "running_instance_freshness"), {})
            require(gate.get("ok") is True, f"running instance gate should pass: {gate}", failures)
            require("require-current-code" in str(gate.get("next_action") or ""), f"running instance next action missing strict CLI: {gate}", failures)

            status_cli = run_cli(base_url, "status", "--require-current-code", "--expect-head-sha", expected_head)
            outputs.extend([status_cli.stdout, status_cli.stderr])
            require(status_cli.returncode == 0, f"strict status CLI failed: {status_cli.stderr or status_cli.stdout}", failures)
            if status_cli.returncode == 0:
                payload = load_cli_json(status_cli)
                require((payload.get("local_code_check") or {}).get("ok") is True, f"strict status code check missing: {payload}", failures)

            readiness_cli = run_cli(base_url, "local", "readiness", "--require-current-code", "--expect-head-sha", expected_head)
            outputs.extend([readiness_cli.stdout, readiness_cli.stderr])
            require(readiness_cli.returncode == 0, f"strict readiness CLI failed: {readiness_cli.stderr or readiness_cli.stdout}", failures)
            if readiness_cli.returncode == 0:
                payload = load_cli_json(readiness_cli)
                require((payload.get("local_code_check") or {}).get("ok") is True, f"strict readiness code check missing: {payload}", failures)

            mismatch_cli = run_cli(base_url, "local", "readiness", "--expect-head-sha", "deadbeef")
            outputs.extend([mismatch_cli.stdout, mismatch_cli.stderr])
            require(mismatch_cli.returncode == 2, f"mismatched head should exit 2: {mismatch_cli.returncode} {mismatch_cli.stdout}", failures)
            mismatch_payload = load_cli_json(mismatch_cli)
            require((mismatch_payload.get("local_code_check") or {}).get("ok") is False, f"mismatched code check should fail: {mismatch_payload}", failures)
        finally:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])
    secret_leaked = leaked_secret("\n".join(outputs))
    result = {
        "ok": not failures and not secret_leaked,
        "operation": "local_runtime_identity_smoke",
        "head_sha": expected_head,
        "failures": failures,
        "secret_leaked": secret_leaked,
        "token_omitted": True,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or secret_leaked else 0


if __name__ == "__main__":
    raise SystemExit(main())
