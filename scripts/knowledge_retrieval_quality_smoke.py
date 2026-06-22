#!/usr/bin/env python3
"""Measure a small bilingual AgentOps knowledge retrieval quality baseline."""
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

TEST_SET = [
    {
        "id": "en_gateway_cli",
        "language": "en",
        "query": "Agent Gateway CLI commands task pull run heartbeat approval memory eval audit",
        "expected_paths": {"docs/AGENT_GATEWAY_CLI_SPEC.md"},
    },
    {
        "id": "en_actor_model",
        "language": "en",
        "query": "Solo owner team member human approver AI digital employee external runtime surface model template model",
        "expected_paths": {"docs/PRODUCT_USAGE_AND_ACTOR_MODEL.md"},
    },
    {
        "id": "en_method_block",
        "language": "en",
        "query": "READ PLAN RETRIEVE COMPARE EXECUTE VERIFY RECORD method block",
        "expected_paths": {"AGENT_WORKFLOW.md", "docs/AGENT_WORK_METHOD_BLOCK.md", "knowledge/runbooks/agent_work_method_runbook.md"},
    },
    {
        "id": "zh_hermes_openclaw",
        "language": "zh",
        "query": "Hermes OpenClaw Loop Runbook mis-ledger plan_evidence_manifest 回写 证据",
        "expected_paths": {"docs/HERMES_OPENCLAW_LOOP_RUNBOOK.md", "docs/REMOTE_WORKER_OPERATIONS_RUNBOOK.md"},
    },
    {
        "id": "en_pixel_office",
        "language": "en",
        "query": "Pixel Office operating map zones route formal MIS pages task hall inspector operations bar",
        "expected_paths": {"docs/PIXEL_OPERATING_MAP_SPEC.md", "docs/PIXEL_OPERATING_MAP_ACCEPTANCE.md"},
    },
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
            status, _, _ = http_json(base_url, "/api/agent-gateway/status")
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


def percentile(values: list[float], percent: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((percent / 100.0) * (len(ordered) - 1)))))
    return ordered[index]


def reciprocal_rank(paths: list[str], expected_paths: set[str]) -> float:
    for index, path in enumerate(paths, start=1):
        if path in expected_paths:
            return 1.0 / index
    return 0.0


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    stamp = now_stamp()
    workspace = f"ws_knowledge_quality_{stamp}"
    agent_id = f"agt_knowledge_quality_{stamp}"

    with tempfile.TemporaryDirectory(prefix="agentops-knowledge-quality-") as tmp:
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
            status, enrollment, raw = http_json(base_url, "/api/agent-gateway/enrollment/create", "POST", {
                "workspace_id": workspace,
                "agent_id": agent_id,
                "name": "Knowledge Retrieval Quality Smoke",
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
            require(indexed.get("operation") == "knowledge_index", f"wrong index operation: {indexed}", failures)
            require(int(indexed.get("indexed") or 0) >= 20, f"too few docs indexed for quality smoke: {indexed}", failures)
            require(indexed.get("token_omitted") is True, f"index token omission missing: {indexed}", failures)

            per_query = []
            latencies_ms: list[float] = []
            reciprocal_ranks: list[float] = []
            hits = 0
            for case in TEST_SET:
                started = time.perf_counter()
                status, payload, raw = http_json(
                    base_url,
                    "/api/agent-gateway/knowledge/search",
                    token=token,
                    workspace=workspace,
                    query={"q": case["query"], "limit": 5},
                )
                elapsed_ms = (time.perf_counter() - started) * 1000
                outputs.append(raw)
                require(status == 200, f"search failed for {case['id']}: {status} {payload}", failures)
                quality = payload.get("search_quality") or {}
                rows = payload.get("results") or []
                paths = [str(row.get("path") or "") for row in rows]
                rr = reciprocal_rank(paths, case["expected_paths"])
                hit = rr > 0
                hits += 1 if hit else 0
                reciprocal_ranks.append(rr)
                latencies_ms.append(elapsed_ms)
                require(payload.get("operation") == "knowledge_search", f"wrong search operation for {case['id']}: {payload}", failures)
                require(quality.get("result_quality") in {"full_text_fts5", "heading_chunk_fts5"}, f"degraded search quality for {case['id']}: {quality}", failures)
                require(quality.get("fallback_used") is False, f"fallback used for quality query {case['id']}: {quality}", failures)
                require(quality.get("content_body_searched") is True, f"body search not reported for {case['id']}: {quality}", failures)
                require(all(row.get("raw_content_omitted") is True for row in rows), f"raw content omission missing for {case['id']}: {rows}", failures)
                require(all(row.get("retrieval_id") for row in rows), f"retrieval ids missing for {case['id']}: {rows}", failures)
                require(quality.get("heading_aware_chunks") is True, f"heading-aware chunk search not reported for {case['id']}: {quality}", failures)
                require(any(row.get("retrieval_granularity") == "heading_chunk" and row.get("chunk_id") for row in rows), f"heading chunk result missing for {case['id']}: {rows}", failures)
                require(hit, f"expected path not found in top 5 for {case['id']}: expected={sorted(case['expected_paths'])} actual={paths}", failures)
                per_query.append({
                    "id": case["id"],
                    "language": case["language"],
                    "hit_at_5": hit,
                    "rank": int(1 / rr) if rr else None,
                    "latency_ms": round(elapsed_ms, 2),
                    "expected_paths": sorted(case["expected_paths"]),
                    "top_paths": paths,
                    "search_mode": payload.get("search_mode"),
                    "result_quality": quality.get("result_quality"),
                    "fallback_used": quality.get("fallback_used"),
                })

            total = len(TEST_SET)
            recall_at_5 = hits / total if total else 0.0
            mrr = sum(reciprocal_ranks) / total if total else 0.0
            p95_ms = percentile(latencies_ms, 95)
            require(recall_at_5 >= 0.8, f"Recall@5 below baseline: {recall_at_5:.2f}", failures)
            require(mrr >= 0.5, f"MRR below baseline: {mrr:.2f}", failures)
            require(p95_ms <= 1000, f"p95 latency above local baseline: {p95_ms:.2f}ms", failures)
            require(not leaked_secret("\n".join(outputs)), "knowledge retrieval quality smoke leaked token-like material", failures)

            result = {
                "ok": not failures,
                "operation": "knowledge_retrieval_quality_smoke",
                "workspace_id": workspace,
                "indexed": {
                    "count": indexed.get("indexed"),
                    "changed": indexed.get("changed"),
                    "fts_available": indexed.get("fts_available"),
                },
                "metrics": {
                    "queries": total,
                    "recall_at_5": round(recall_at_5, 4),
                    "mrr": round(mrr, 4),
                    "p95_ms": round(p95_ms, 2),
                },
                "per_query": per_query,
                "failures": failures,
                "secret_leaked": leaked_secret("\n".join(outputs)),
                "token_omitted": True,
            }
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
            return 1 if failures or result["secret_leaked"] else 0
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


if __name__ == "__main__":
    raise SystemExit(main())
