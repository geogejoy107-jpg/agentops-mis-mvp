#!/usr/bin/env python3
"""Verify Agent Gateway knowledge search enforces workspace visibility metadata."""
from __future__ import annotations

import datetime as dt
import hashlib
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


def stable_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def now_stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(base_url: str, path: str, method: str = "GET", body: dict | None = None, token: str | None = None, workspace: str | None = None, query: dict | None = None) -> tuple[int, dict, str]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
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


def insert_private_doc(db_path: Path, workspace_id: str, doc_id: str, marker: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        now = dt.datetime.now(dt.timezone.utc).isoformat()
        path = f"customer_private/{workspace_id}/{doc_id}.md"
        title = f"Private Knowledge {workspace_id}"
        content = f"# {title}\n\n{marker} belongs only to {workspace_id}."
        source_hash = stable_hash({"path": path, "content": content})
        conn.execute(
            """INSERT OR REPLACE INTO knowledge_documents(
                doc_id, workspace_id, project_id, access_level, path, title,
                category, scope, source_hash, content_summary, indexed_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                doc_id,
                workspace_id,
                f"customer:{workspace_id}",
                "private",
                path,
                title,
                "customer_private",
                "project",
                source_hash,
                content,
                now,
                now,
            ),
        )
        try:
            conn.execute("DELETE FROM knowledge_fts WHERE doc_id=?", (doc_id,))
            conn.execute("INSERT INTO knowledge_fts(doc_id,path,title,content) VALUES(?,?,?,?)", (doc_id, path, title, content))
        except sqlite3.OperationalError:
            pass
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    failures: list[str] = []
    outputs: list[str] = []
    stamp = now_stamp()
    workspace_a = f"ws_knowledge_a_{stamp}"
    workspace_b = f"ws_knowledge_b_{stamp}"
    marker_a = f"ScopePrivateAlpha{stamp}"
    marker_b = f"ScopePrivateBeta{stamp}"
    redaction_marker = f"KnowledgeRedactionSmoke{stamp}"
    fake_secret = "sk-" + f"knowledgeScopeSecret{stamp}"
    temp_doc = ROOT / "knowledge" / "runbooks" / f"knowledge_scope_redaction_{stamp}.md"
    temp_excluded_dir = ROOT / "knowledge" / "raw_customer"
    temp_excluded_doc = temp_excluded_dir / f"raw_customer_scope_{stamp}.md"

    with tempfile.TemporaryDirectory(prefix="agentops-knowledge-scope-") as tmp:
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
            temp_excluded_dir.mkdir(parents=True, exist_ok=True)
            temp_excluded_doc.write_text(
                f"# Raw Customer Fixture\n\n{marker_b} should never be indexed from raw customer files.\n",
                encoding="utf-8",
            )
            temp_doc.write_text(
                f"# Knowledge Scope Redaction Smoke\n\n{redaction_marker} must redact {fake_secret} before indexing.\n",
                encoding="utf-8",
            )
            status, enrollment, raw = http_json(base_url, "/api/agent-gateway/enrollment/create", "POST", {
                "workspace_id": workspace_a,
                "agent_id": f"agt_knowledge_scope_{stamp}",
                "name": "Knowledge Scope Smoke",
                "runtime_type": "mock",
                "scopes": ["knowledge:read", "knowledge:write"],
                "ttl_days": 1,
            })
            require(status == 201, f"enrollment failed: {status} {enrollment}", failures)
            token = enrollment.get("token")
            token_id = enrollment.get("token_id")
            require(bool(token), f"token missing: {enrollment}", failures)

            status, indexed, raw = http_json(base_url, "/api/agent-gateway/knowledge/index", "POST", {"rebuild": True}, token=token, workspace=workspace_a)
            outputs.append(raw)
            require(status == 200, f"knowledge index failed: {status} {indexed}", failures)
            require(indexed.get("token_omitted") is True, f"token omission missing: {indexed}", failures)
            require(int(indexed.get("excluded") or 0) >= 1, f"excluded count missing: {indexed}", failures)
            require("excluded_dir:raw_customer" in set(indexed.get("excluded_reasons") or []), f"raw customer exclusion reason missing: {indexed}", failures)

            status, redacted_search, raw = http_json(base_url, "/api/agent-gateway/knowledge/search", token=token, workspace=workspace_a, query={"q": redaction_marker, "limit": 5})
            outputs.append(raw)
            require(status == 200, f"redaction search failed: {status} {redacted_search}", failures)
            redaction_text = json.dumps(redacted_search, ensure_ascii=False)
            require(redaction_marker in redaction_text, f"redaction smoke doc missing: {redacted_search}", failures)
            require(fake_secret not in redaction_text, "raw fake secret appeared in search output", failures)
            require("[SECRET_REDACTED]" in redaction_text, f"redacted marker missing from search output: {redacted_search}", failures)
            fts_quality = redacted_search.get("search_quality") or {}
            require(fts_quality.get("search_mode") == "fts5", f"normal knowledge search should report fts5 quality: {fts_quality}", failures)
            require(fts_quality.get("fallback_used") is False, f"normal knowledge search should not report fallback: {fts_quality}", failures)
            require(fts_quality.get("content_body_searched") is True, f"normal knowledge search should report body search: {fts_quality}", failures)

            status, fallback_search, raw = http_json(base_url, "/api/agent-gateway/knowledge/search", token=token, workspace=workspace_a, query={"q": "!!!", "limit": 5})
            outputs.append(raw)
            require(status == 200, f"fallback search failed: {status} {fallback_search}", failures)
            fallback_quality = fallback_search.get("search_quality") or {}
            require(fallback_search.get("search_mode") == "like", f"fallback search_mode not explicit: {fallback_search}", failures)
            require(fallback_quality.get("fallback_used") is True, f"fallback flag missing: {fallback_quality}", failures)
            require(fallback_quality.get("fallback_reason") == "empty_fts_query", f"fallback reason missing: {fallback_quality}", failures)
            require(fallback_quality.get("content_body_searched") is False, f"fallback should report no body search: {fallback_quality}", failures)
            require(fallback_quality.get("result_quality") == "metadata_summary_like", f"fallback result quality missing: {fallback_quality}", failures)
            require("content_summary" in set(fallback_quality.get("searched_fields") or []), f"fallback searched_fields missing summary disclosure: {fallback_quality}", failures)
            require(bool(fallback_quality.get("warning")), f"fallback warning missing: {fallback_quality}", failures)

            status, excluded_search, raw = http_json(base_url, "/api/agent-gateway/knowledge/search", token=token, workspace=workspace_a, query={"q": marker_b, "limit": 10})
            outputs.append(raw)
            require(status == 200, f"excluded raw customer search failed: {status} {excluded_search}", failures)
            require(not any("raw_customer" in str(row.get("path") or "") for row in excluded_search.get("results") or []), f"raw customer file leaked into search: {excluded_search}", failures)

            status, noop_index, raw = http_json(base_url, "/api/agent-gateway/knowledge/index", "POST", {"rebuild": False}, token=token, workspace=workspace_a)
            outputs.append(raw)
            require(status == 200, f"incremental index failed: {status} {noop_index}", failures)
            require(noop_index.get("changed") == 0, f"incremental index changed unchanged docs: {noop_index}", failures)
            require(noop_index.get("deleted") == 0, f"incremental index deleted unchanged docs: {noop_index}", failures)
            require(noop_index.get("incremental_noop") is True, f"incremental no-op flag missing: {noop_index}", failures)

            insert_private_doc(db_path, workspace_a, "kdoc_private_a", marker_a)
            insert_private_doc(db_path, workspace_b, "kdoc_private_b", marker_b)

            status, global_search, raw = http_json(base_url, "/api/agent-gateway/knowledge/search", token=token, workspace=workspace_a, query={"q": "AgentOps", "limit": 10})
            outputs.append(raw)
            require(status == 200, f"global search failed: {status} {global_search}", failures)
            require((global_search.get("visibility") or {}).get("bound_visibility_enforced") is True, f"visibility not enforced: {global_search}", failures)
            global_results = global_search.get("results") or []
            require(any(row.get("workspace_id") == "global" for row in global_results), f"global docs missing: {global_results}", failures)
            for row in global_results:
                require(bool(row.get("retrieval_id")), f"retrieval_id missing: {row}", failures)
                require(bool(row.get("source_hash")), f"source_hash missing: {row}", failures)
                require(row.get("raw_content_omitted") is True, f"raw_content_omitted missing: {row}", failures)
                require(row.get("workspace_id") in {"global", workspace_a}, f"unexpected workspace leaked: {row}", failures)
                require(bool(row.get("access_level")), f"access_level missing: {row}", failures)

            status, own_private, raw = http_json(base_url, "/api/agent-gateway/knowledge/search", token=token, workspace=workspace_a, query={"q": marker_a, "limit": 10})
            outputs.append(raw)
            require(status == 200, f"own private search failed: {status} {own_private}", failures)
            own_paths = {row.get("path") for row in own_private.get("results") or []}
            require(any(marker_a in (row.get("snippet") or row.get("content_summary") or "") or row.get("doc_id") == "kdoc_private_a" for row in own_private.get("results") or []), f"own private doc missing: {own_private}", failures)
            require(all(workspace_b not in str(path) for path in own_paths), f"workspace B leaked in own search: {own_private}", failures)

            status, other_private, raw = http_json(base_url, "/api/agent-gateway/knowledge/search", token=token, workspace=workspace_a, query={"q": marker_b, "limit": 10})
            outputs.append(raw)
            require(status == 200, f"other private search failed: {status} {other_private}", failures)
            require(not any(row.get("doc_id") == "kdoc_private_b" for row in other_private.get("results") or []), f"workspace B private doc leaked: {other_private}", failures)

            status, spoofed, raw = http_json(base_url, "/api/agent-gateway/knowledge/search", token=token, workspace=workspace_b, query={"q": marker_b, "limit": 10})
            outputs.append(raw)
            require(status == 403, f"workspace header spoof should fail: {status} {spoofed}", failures)

            status, qs_spoofed, raw = http_json(base_url, "/api/agent-gateway/knowledge/search", token=token, workspace=workspace_a, query={"q": marker_b, "workspace_id": workspace_b, "limit": 10})
            outputs.append(raw)
            require(status == 403, f"workspace query spoof should fail: {status} {qs_spoofed}", failures)

            require(not leaked_secret("\n".join(outputs)), "knowledge scope smoke leaked token-like material", failures)
        finally:
            if token_id:
                http_json(base_url, "/api/agent-gateway/enrollment/revoke", "POST", {"token_id": token_id})
            try:
                temp_doc.unlink()
            except FileNotFoundError:
                pass
            try:
                temp_excluded_doc.unlink()
                temp_excluded_dir.rmdir()
            except OSError:
                pass
            proc.terminate()
            try:
                stdout, stderr = proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                stdout, stderr = proc.communicate(timeout=10)
            outputs.extend([stdout or "", stderr or ""])

    result = {
        "ok": not failures,
        "operation": "knowledge_scope_policy_smoke",
        "workspace_a": workspace_a,
        "workspace_b": workspace_b,
        "failures": failures,
        "secret_leaked": leaked_secret("\n".join(outputs)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures or result["secret_leaked"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
