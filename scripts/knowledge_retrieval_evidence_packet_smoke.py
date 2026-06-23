#!/usr/bin/env python3
"""Verify read-only knowledge retrieval evidence packets for agents/operators."""
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
]
READ_ONLY_TABLES = [
    "tasks",
    "runs",
    "tool_calls",
    "runtime_events",
    "evaluations",
    "audit_logs",
    "artifacts",
    "agent_plans",
    "plan_evidence_manifests",
    "knowledge_documents",
    "knowledge_chunks",
]


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(
    base_url: str,
    path: str,
    method: str = "GET",
    body: dict | None = None,
    token: str | None = None,
    workspace: str | None = None,
    query: dict | None = None,
) -> tuple[int, dict, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urlencode({key: value for key, value in query.items() if value is not None}, doseq=True)
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if workspace:
        headers["X-AgentOps-Workspace-Id"] = workspace
    data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = Request(url, data=data, method=method, headers=headers)
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
            status, _payload, _raw = http_json(base_url, "/api/agent-gateway/status")
            if status == 200:
                return
        except URLError as exc:
            last_error = str(exc)
        time.sleep(0.5)
    raise RuntimeError(f"server did not become ready: {last_error}")


def table_counts(db_path: Path) -> dict[str, int]:
    conn = sqlite3.connect(db_path)
    try:
        return {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in READ_ONLY_TABLES
        }
    finally:
        conn.close()


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def leaked_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def assert_packet(payload: dict, failures: list[str]) -> None:
    require(payload.get("operation") == "knowledge_retrieval_evidence_packet", f"wrong operation: {payload}", failures)
    require(payload.get("version") == "v0", f"missing version: {payload}", failures)
    require(payload.get("status") in {"ready", "attention"}, f"bad status: {payload}", failures)
    require(payload.get("query_omitted") is True, f"query should be omitted: {payload}", failures)
    require(bool(payload.get("query_hash")), f"query hash missing: {payload}", failures)
    require("query" not in payload, f"raw query leaked at top level: {payload}", failures)
    safety = payload.get("safety") or {}
    for key in ["read_only", "raw_prompt_omitted", "raw_response_omitted", "raw_content_omitted", "snippet_omitted", "token_omitted"]:
        require(safety.get(key) is True, f"safety flag {key} missing: {safety}", failures)
    for key in ["ledger_mutated", "task_mutated", "run_mutated", "tool_mutated", "live_execution_performed", "external_network"]:
        require(safety.get(key) is False, f"safety flag {key} should be false: {safety}", failures)
    metrics = payload.get("metrics") or {}
    require(float(metrics.get("recall_at_5") or 0) >= 0.8, f"recall baseline weak: {metrics}", failures)
    require(float(metrics.get("mrr") or 0) >= 0.5, f"MRR baseline weak: {metrics}", failures)
    require(int(metrics.get("fallback_queries") or 0) == 0, f"fallback queries should be zero: {metrics}", failures)
    primary = payload.get("primary_search") or {}
    require(primary.get("query_omitted") is True, f"primary query should be omitted: {primary}", failures)
    require("query" not in primary, f"raw primary query leaked: {primary}", failures)
    index = primary.get("index") or {}
    require(index.get("read_only") is True, f"packet search must be read-only: {index}", failures)
    require(index.get("refresh_performed") is False, f"packet search must not refresh index: {index}", failures)
    results = primary.get("results") or []
    require(results, f"packet primary results missing: {payload}", failures)
    for row in results:
        for key in ["retrieval_id", "doc_id", "path", "source_hash"]:
            require(bool(row.get(key)), f"result missing {key}: {row}", failures)
        for forbidden in ["snippet", "content", "content_summary"]:
            require(forbidden not in row, f"result leaked {forbidden}: {row}", failures)
        for flag in ["raw_content_omitted", "snippet_omitted", "content_summary_omitted", "raw_prompt_omitted", "token_omitted"]:
            require(row.get(flag) is True, f"result missing omission flag {flag}: {row}", failures)
    for case in payload.get("baseline") or []:
        require(case.get("query_hash") and "query" not in case, f"baseline query leaked: {case}", failures)
        for row in case.get("top_results") or []:
            for forbidden in ["snippet", "content", "content_summary"]:
                require(forbidden not in row, f"baseline result leaked {forbidden}: {row}", failures)


def run_cli(base_url: str, token: str, workspace: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [
            str(CLI),
            "--base-url",
            base_url,
            "--api-key",
            token,
            "--workspace-id",
            workspace,
            "knowledge",
            "evidence-packet",
            "Agent Gateway CLI commands task pull run heartbeat",
            "--limit",
            "5",
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    stamp = now_stamp()
    workspace = f"ws_knowledge_packet_{stamp}"
    agent_id = f"agt_knowledge_packet_{stamp}"
    with tempfile.TemporaryDirectory(prefix="agentops-knowledge-packet-") as tmp:
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
        token_id = None
        try:
            wait_ready(base_url, proc)
            status, enrollment, _raw = http_json(base_url, "/api/agent-gateway/enrollment/create", "POST", {
                "workspace_id": workspace,
                "agent_id": agent_id,
                "name": "Knowledge Retrieval Evidence Packet Smoke",
                "runtime_type": "mock",
                "scopes": ["knowledge:read", "knowledge:write"],
                "ttl_days": 1,
            })
            require(status == 201, f"enrollment failed: {status} {enrollment}", failures)
            token = enrollment.get("token")
            token_id = enrollment.get("token_id")
            require(bool(token), f"token missing: {enrollment}", failures)

            status, indexed, raw = http_json(
                base_url,
                "/api/agent-gateway/knowledge/index",
                "POST",
                {"rebuild": True},
                token=token,
                workspace=workspace,
            )
            outputs.append(raw)
            require(status == 200, f"knowledge index failed: {status} {indexed}", failures)
            require(int(indexed.get("indexed") or 0) >= 20, f"too few docs indexed: {indexed}", failures)
            before = table_counts(db_path)

            status, packet, raw = http_json(
                base_url,
                "/api/agent-gateway/knowledge/retrieval-evidence-packet",
                token=token,
                workspace=workspace,
                query={"q": "Agent Gateway CLI commands task pull run heartbeat", "limit": 5, "refresh": "true"},
            )
            outputs.append(raw)
            require(status == 200, f"packet API failed: {status} {packet}", failures)
            assert_packet(packet, failures)

            status, alias_packet, raw = http_json(
                base_url,
                "/api/agent-gateway/knowledge/evidence-packet",
                token=token,
                workspace=workspace,
                query={"q": "READ PLAN RETRIEVE COMPARE EXECUTE VERIFY RECORD", "limit": 5},
            )
            outputs.append(raw)
            require(status == 200, f"packet alias API failed: {status} {alias_packet}", failures)
            assert_packet(alias_packet, failures)

            status, readiness, raw = http_json(base_url, "/api/local/readiness", workspace=workspace)
            outputs.append(raw)
            require(status == 200, f"readiness failed: {status} {readiness}", failures)
            embedded = readiness.get("knowledge_retrieval_evidence") or {}
            assert_packet(embedded, failures)
            knowledge_gate = next((gate for gate in readiness.get("gates") or [] if gate.get("id") == "knowledge_memory"), {})
            require("evidence-packet" in str(knowledge_gate.get("next_action") or ""), f"readiness does not route to packet CLI: {knowledge_gate}", failures)

            status, launch, raw = http_json(
                base_url,
                "/api/operator/loop-launch-packet",
                workspace=workspace,
                query={"query": "Agent Gateway CLI commands task pull run heartbeat", "limit": 5},
            )
            outputs.append(raw)
            require(status == 200, f"loop launch failed: {status} {launch}", failures)
            launch_packet = ((launch.get("sources") or {}).get("knowledge_retrieval_evidence") or {})
            require(launch_packet.get("operation") == "knowledge_retrieval_evidence_packet", f"loop launch missing knowledge packet: {launch}", failures)
            require((launch_packet.get("safety") or {}).get("read_only") is True, f"loop launch packet safety missing: {launch_packet}", failures)

            cli = run_cli(base_url, token, workspace)
            outputs.append(cli.stdout)
            outputs.append(cli.stderr)
            require(cli.returncode == 0, f"CLI packet failed: {cli.stderr or cli.stdout}", failures)
            if cli.returncode == 0:
                assert_packet(json.loads(cli.stdout), failures)

            after = table_counts(db_path)
            require(after == before, f"read-only packet mutated DB counts: before={before} after={after}", failures)
        finally:
            if token_id:
                try:
                    http_json(base_url, "/api/agent-gateway/enrollment/revoke", "POST", {"token_id": token_id})
                except Exception:
                    pass
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
        "operation": "knowledge_retrieval_evidence_packet_smoke",
        "workspace_id": workspace,
        "failures": failures,
        "secret_leaked": secret_leaked,
        "token_omitted": True,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or secret_leaked else 0


if __name__ == "__main__":
    raise SystemExit(main())
