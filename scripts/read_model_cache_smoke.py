#!/usr/bin/env python3
"""Verify short-TTL aggregate read-model caching is scoped, bounded, and read-only."""
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
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
]


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str, query: dict | None = None, headers: dict | None = None, method: str = "GET", payload: dict | None = None) -> tuple[int, dict, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urlencode({key: value for key, value in query.items() if value is not None})
    req_headers = {"Accept": "application/json", "Content-Type": "application/json"}
    req_headers.update(headers or {})
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, headers=req_headers, method=method)
    try:
        with urlopen(req, timeout=45) as res:
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
            status, _, _ = http_json(base_url, "/api/agent-gateway/status")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def db_fingerprint(db_path: Path) -> dict:
    conn = sqlite3.connect(db_path)
    try:
        result = {}
        for table in [
            "agents",
            "tasks",
            "runs",
            "tool_calls",
            "runtime_events",
            "evaluations",
            "audit_logs",
            "approvals",
            "memories",
            "agent_plans",
            "plan_evidence_manifests",
        ]:
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                result[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] or 0)
        return result
    finally:
        conn.close()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def cache_meta(payload: dict) -> dict:
    meta = payload.get("read_model_cache") or {}
    return meta if isinstance(meta, dict) else {}


def validate_cached_pair(base_url: str, path: str, query: dict, label: str, failures: list[str], outputs: list[str], headers: dict | None = None) -> tuple[dict, dict]:
    status, first, raw_first = http_json(base_url, path, query, headers=headers)
    status2, second, raw_second = http_json(base_url, path, query, headers=headers)
    outputs.extend([raw_first, raw_second])
    require(status == 200, f"{label} first request failed: {status} {first}", failures)
    require(status2 == 200, f"{label} second request failed: {status2} {second}", failures)
    first_cache = cache_meta(first)
    second_cache = cache_meta(second)
    require(first_cache.get("status") == "miss", f"{label} first request should miss: {first_cache}", failures)
    require(second_cache.get("status") == "hit", f"{label} second request should hit: {second_cache}", failures)
    require(first_cache.get("key_hash") == second_cache.get("key_hash"), f"{label} cache key changed across identical reads", failures)
    require(first_cache.get("token_omitted") is True, f"{label} token omission missing on miss: {first_cache}", failures)
    require(second_cache.get("token_omitted") is True, f"{label} token omission missing on hit: {second_cache}", failures)
    return first, second


def create_enrollment(base_url: str) -> str:
    status, payload, _raw = http_json(
        base_url,
        "/api/agent-gateway/enrollment/create",
        method="POST",
        payload={
            "workspace_id": "ws_cache_scoped",
            "agent_id": "agt_cache_scoped",
            "name": "Read Model Cache Scoped Agent",
            "runtime_type": "mock",
            "scopes": ["tasks:read", "agents:heartbeat"],
            "ttl_days": 1,
        },
    )
    if status != 201 or not payload.get("token"):
        raise RuntimeError(f"failed to create enrollment: {status} {payload}")
    return str(payload["token"])


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-read-model-cache-") as tmp:
        db_path = Path(tmp) / "agentops_mis.db"
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env["AGENTOPS_DB_PATH"] = str(db_path)
        env["AGENTOPS_SKIP_SEED_EXPORTS"] = "1"
        env["AGENTOPS_READ_MODEL_CACHE_TTL_SEC"] = "5"
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
            scoped_token = create_enrollment(base_url)
            before = db_fingerprint(db_path)

            endpoints = [
                ("/api/operator/action-plan", {"limit": "5"}, "action_plan"),
                ("/api/operator/evidence-report", {"limit": "5"}, "evidence_report"),
                ("/api/operator/health", {"limit": "5"}, "operator_health"),
                ("/api/operator/handoff", {"limit": "5"}, "operator_handoff"),
                ("/api/operator/loop-self-check", {"limit": "5"}, "loop_self_check"),
                ("/api/dashboard/metrics", {}, "dashboard_metrics"),
            ]
            first_by_label: dict[str, dict] = {}
            for path, query, label in endpoints:
                first, _second = validate_cached_pair(base_url, path, query, label, failures, outputs)
                first_by_label[label] = first
                alt_query = dict(query)
                alt_query["cache_probe"] = "alt"
                status, alt_payload, raw_alt = http_json(base_url, path, alt_query)
                outputs.append(raw_alt)
                require(status == 200, f"{label} alt-query failed: {status} {alt_payload}", failures)
                require(cache_meta(alt_payload).get("status") == "miss", f"{label} alt-query should miss: {cache_meta(alt_payload)}", failures)
                require(
                    cache_meta(alt_payload).get("key_hash") != cache_meta(first).get("key_hash"),
                    f"{label} alt-query reused the same cache key",
                    failures,
                )

            status, bypass_payload, raw_bypass = http_json(base_url, "/api/operator/health", {"limit": "5", "refresh_cache": "true"})
            outputs.append(raw_bypass)
            require(status == 200, f"refresh_cache request failed: {status} {bypass_payload}", failures)
            require(cache_meta(bypass_payload).get("status") == "bypass", f"refresh_cache should bypass: {cache_meta(bypass_payload)}", failures)

            scoped_headers = {"Authorization": f"Bearer {scoped_token}", "X-AgentOps-Workspace-Id": "ws_cache_scoped"}
            scoped_first, _scoped_second = validate_cached_pair(
                base_url,
                "/api/operator/health",
                {"limit": "5"},
                "scoped_operator_health",
                failures,
                outputs,
                headers=scoped_headers,
            )
            require(
                cache_meta(scoped_first).get("key_hash") != cache_meta(first_by_label["operator_health"]).get("key_hash"),
                "scoped token reused local-dev operator_health cache key",
                failures,
            )

            after = db_fingerprint(db_path)
            require(before == after, f"read-model cache endpoints mutated ledger: before={before} after={after}", failures)
            joined = "\n".join(outputs)
            require(not leaked_secret(joined), "secret-like value leaked in cache smoke output", failures)
            require("agtok_" not in joined, "agent token appeared in cache output", failures)
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    if failures:
        print("read_model_cache_smoke failed:")
        for failure in failures:
            print(f"- {failure}")
        return 1
    print("read_model_cache_smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
