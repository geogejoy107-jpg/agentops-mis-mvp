#!/usr/bin/env python3
"""Smoke test governed live harness acceptance preview mode only."""
from __future__ import annotations

import json
import os
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
SCRIPT = ROOT / "scripts" / "local_harness_governed_live_acceptance.py"


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str) -> tuple[int, dict]:
    req = Request(base_url.rstrip("/") + path, headers={"Accept": "application/json"}, method="GET")
    try:
        with urlopen(req, timeout=30) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}


def wait_ready(base_url: str, proc: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"server exited early with code {proc.returncode}")
        try:
            status, _ = http_json(base_url, "/api/operator/local-harness-proof?limit=1")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def ledger_counts(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        return {
            "runs": int(conn.execute("SELECT COUNT(*) AS c FROM runs").fetchone()["c"]),
            "audit_logs": int(conn.execute("SELECT COUNT(*) AS c FROM audit_logs").fetchone()["c"]),
            "runtime_events": int(conn.execute("SELECT COUNT(*) AS c FROM runtime_events").fetchone()["c"]),
        }
    finally:
        conn.close()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(raw: str) -> dict:
    try:
        parsed = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-local-harness-governed-live-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
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
            before = ledger_counts(db_path)
            preview = subprocess.run(
                [sys.executable, str(SCRIPT), "--base-url", base_url, "--adapter", "openclaw"],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            outputs.extend([preview.stdout, preview.stderr])
            payload = load_json(preview.stdout)
            after = ledger_counts(db_path)
            require(preview.returncode == 0, f"preview failed: {preview.returncode} {preview.stderr}", failures)
            require(payload.get("operation") == "local_harness_governed_live_acceptance", f"wrong operation: {payload}", failures)
            require(payload.get("mode") == "preview", f"preview mode missing: {payload}", failures)
            require((payload.get("safety") or {}).get("live_execution_performed") is False, f"preview must not execute live: {payload}", failures)
            require((payload.get("safety") or {}).get("ledger_mutated") is False, f"preview must not mutate ledger: {payload}", failures)
            require(before == after, f"preview mutated ledger counts: {before} -> {after}", failures)
            result = (payload.get("results") or [{}])[0]
            governed = result.get("governed") or {}
            require("--confirm-run" in str(governed.get("confirmed_command") or ""), f"confirmed command missing confirm: {governed}", failures)
            require("--source local_harness_proof.governed_launch" in str(governed.get("receipt_readback_command") or ""), f"receipt readback source filter missing: {governed}", failures)
            require("--action-id local_harness_proof:openclaw" in str(governed.get("receipt_readback_command") or ""), f"receipt readback action-id missing: {governed}", failures)
            require("--action-signature" in str(governed.get("receipt_readback_command") or ""), f"receipt readback signature missing: {governed}", failures)
            require(result.get("receipt_presence_is_runtime_success") is False, f"receipt boundary missing: {result}", failures)
        finally:
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])
    output = {
        "ok": not failures,
        "operation": "local_harness_governed_live_acceptance_smoke",
        "failures": failures,
        "secret_leaked": any(marker in "\n".join(outputs) for marker in ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"]),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or output["secret_leaked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
