#!/usr/bin/env python3
"""Prove a real Worker-to-Human-review loop without starting the Python API."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
NEXT_APP = ROOT / "ui" / "next-app"
CONTRACT_ID = "nextjs_postgres_real_worker_human_review_v1"
WORKSPACE_ID = "ws_real_worker_human_review"
OTHER_WORKSPACE_ID = "ws_real_worker_human_review_other"
REQUESTER_ID = "usr_founder"
OWNER_USERNAME = "real-worker-owner"
SCOPES = [
    "agents:write",
    "agents:heartbeat",
    "tasks:read",
    "tasks:claim",
    "agent_plans:write",
    "runs:write",
    "toolcalls:write",
    "evaluations:submit",
    "artifacts:write",
    "memories:propose",
    "audit:write",
    "plan_evidence:write",
]

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SCRIPTS))

import server  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
from nextjs_playwright_snapshot_smoke import free_port, start_process, stop_process  # noqa: E402


NODE_PG_HELPER = r"""
const fs = require('node:fs');
const { Client } = require('./ui/next-app/node_modules/pg');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));

function translateQmarks(sql) {
  let output = '';
  let inSingle = false;
  let parameter = 0;
  for (let index = 0; index < sql.length; index += 1) {
    const char = sql[index];
    if (char === "'") {
      output += char;
      if (inSingle && sql[index + 1] === "'") {
        output += sql[index + 1];
        index += 1;
      } else {
        inSingle = !inSingle;
      }
    } else if (char === '?' && !inSingle) {
      parameter += 1;
      output += `$${parameter}`;
    } else {
      output += char;
    }
  }
  return output;
}

(async () => {
  const client = new Client({
    connectionString: process.env.AGENTOPS_NODE_PG_DSN,
    application_name: 'agentops-real-worker-human-review-smoke',
  });
  try {
    await client.connect();
    const query = input.script ? input.sql : translateQmarks(input.sql);
    const response = await client.query(query, input.params || []);
    process.stdout.write(JSON.stringify({ rows: response.rows || [], row_count: response.rowCount || 0 }));
  } finally {
    await client.end().catch(() => undefined);
  }
})().catch((error) => {
  process.stderr.write(String(error && error.message ? error.message : error));
  process.exitCode = 1;
});
"""


class NodePgAdapter:
    """Test-only structured Postgres client using the Next runtime's pinned pg."""

    def __init__(self, dsn: str, node_binary: str):
        self.dsn = dsn
        self.node_binary = node_binary

    def _request(self, sql: str, params: tuple[Any, ...] = (), *, script: bool = False) -> dict[str, Any]:
        env = os.environ.copy()
        env["AGENTOPS_NODE_PG_DSN"] = self.dsn
        completed = subprocess.run(
            [self.node_binary, "-e", NODE_PG_HELPER],
            cwd=ROOT,
            env=env,
            input=json.dumps({"sql": sql, "params": list(params), "script": script}, ensure_ascii=False),
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"Node Postgres query failed: {completed.stderr[-1000:]}")
        return json.loads(completed.stdout or "{}")

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any]:
        return self._request(sql, params)

    def executescript(self, sql: str) -> None:
        self._request(sql, script=True)

    def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        rows = self._request(sql, params).get("rows") or []
        return rows[0] if rows else None

    def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return list(self._request(sql, params).get("rows") or [])

    def commit(self) -> None:
        return None

    def close(self) -> None:
        return None


def redact(value: object, sensitive: list[str]) -> str:
    output = str(value)
    for secret in sorted((item for item in sensitive if item), key=len, reverse=True):
        output = output.replace(secret, "[REDACTED]")
    return output


def result(payload: dict[str, Any], sensitive: list[str]) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    print(redact(rendered, sensitive))


def dsn_with_search_path(dsn: str, schema: str) -> str:
    parsed = urllib.parse.urlsplit(dsn)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("--postgres-dsn must be a postgres URL")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    existing = [value for key, value in query if key == "options"]
    query = [(key, value) for key, value in query if key != "options"]
    query.append(("options", " ".join([*existing, f"-c search_path={schema}"]).strip()))
    return urllib.parse.urlunsplit((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        urllib.parse.urlencode(query, quote_via=urllib.parse.quote),
        parsed.fragment,
    ))


def http_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    *,
    headers: dict[str, str] | None = None,
    timeout: int = 30,
) -> tuple[int, Any, dict[str, str]]:
    request_headers = dict(headers or {})
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            return int(response.status), json.loads(raw) if raw else {}, response_headers
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw_omitted": True}
        response_headers = {key.lower(): value for key, value in exc.headers.items()}
        return int(exc.code), payload, response_headers


def raw_cookie(headers: dict[str, str]) -> str:
    prefix = "agentops_human_session="
    for part in headers.get("set-cookie", "").split(";"):
        item = part.strip()
        if item.startswith(prefix):
            return item[len(prefix):]
    return ""


def wait_for_next(base_url: str, proc: subprocess.Popen[str], sensitive: list[str]) -> None:
    deadline = time.time() + 90
    last = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            stdout, stderr = proc.communicate(timeout=2)
            raise RuntimeError(
                redact(
                    f"Next exited early (code={proc.returncode}): {(stdout or '')[-800:]} {(stderr or '')[-800:]}",
                    sensitive,
                )
            )
        try:
            status, payload, _ = http_json(
                "GET",
                f"{base_url}/api/agent-gateway/tasks/pull?workspace_id={WORKSPACE_ID}&limit=1&status=planned",
            )
            if status == 401 and isinstance(payload, dict) and payload.get("error") == "unauthorized":
                return
            last = f"{status}:{payload}"
        except Exception as exc:  # pragma: no cover - diagnostics only
            last = str(exc)
        time.sleep(0.25)
    raise RuntimeError(redact(f"Next Agent Gateway alias did not become ready: {last}", sensitive))


def run_npm(npm: str, runtime_dsn: str, args: list[str], *, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({"AGENTOPS_POSTGRES_DSN": runtime_dsn, "AGENTOPS_POSTGRES_SSL": "0"})
    return subprocess.run(
        [npm, "run", "--silent", *args],
        cwd=NEXT_APP,
        env=env,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=60,
        check=False,
    )


def seed_foundation(adapter: NodePgAdapter) -> None:
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    adapter.execute(
        "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
        (REQUESTER_ID, "Real Worker Requester", "real-worker-requester@local.invalid", "customer", now),
    )
    adapter.execute(
        """INSERT INTO runtime_connectors(
            runtime_connector_id,provider,connector_type,profile_name,base_url,binary_path,status,allow_real_run,
            require_confirm_run,trust_status,trust_note,trust_updated_at,last_health_at,last_error,created_at,updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            "rtc_agent_gateway_local",
            "agent_gateway",
            "local",
            "TypeScript/Postgres real Worker acceptance",
            None,
            None,
            "ready",
            1,
            1,
            "trusted",
            "Ephemeral acceptance fixture.",
            now,
            now,
            None,
            now,
            now,
        ),
    )
    adapter.commit()


def seed_workers(adapter: NodePgAdapter, adapters: list[str], tokens: dict[str, str], prompt_secret: str) -> None:
    now = dt.datetime.now(dt.timezone.utc)
    now_text = now.isoformat()
    expires = (now + dt.timedelta(hours=2)).isoformat()
    for runtime in adapters:
        agent_id = f"agt_real_{runtime}_review"
        task_id = f"tsk_real_{runtime}_review"
        adapter.execute(
            """INSERT INTO agents(
                agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,
                allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                agent_id,
                f"Real {runtime} Worker",
                "operator",
                "Ephemeral real Runtime acceptance Worker.",
                runtime,
                runtime,
                runtime,
                "idle",
                "standard",
                json.dumps(["agent_gateway.task", f"{runtime}.execute", "agent_gateway.audit"]),
                5.0,
                REQUESTER_ID,
                now_text,
                now_text,
            ),
        )
        adapter.execute(
            """INSERT INTO tasks(
                task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,
                status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                task_id,
                WORKSPACE_ID,
                f"Real {runtime} candidate review",
                f"Return a bounded delivery summary. Test prompt marker: {prompt_secret}",
                REQUESTER_ID,
                agent_id,
                "[]",
                "planned",
                "high",
                None,
                "A real Runtime call must finish and propose one reviewable memory candidate.",
                "low",
                0,
                now_text,
                now_text,
            ),
        )
        adapter.execute(
            """INSERT INTO agent_gateway_tokens(
                token_id,token_hash,workspace_id,agent_id,scopes_json,status,label,heartbeat_timeout_sec,
                created_at,expires_at,revoked_at,last_used_at,last_heartbeat_at
            ) VALUES(?,?,?,?,?,'active',?,300,?,?,NULL,NULL,NULL)""",
            (
                f"tok_real_{runtime}_review",
                hashlib.sha256(tokens[runtime].encode("utf-8")).hexdigest(),
                WORKSPACE_ID,
                agent_id,
                json.dumps(SCOPES),
                f"Real {runtime} acceptance token",
                now_text,
                expires,
            ),
        )
    adapter.commit()


def run_worker(
    runtime: str,
    base_url: str,
    token: str,
    hermes_url: str,
    openclaw_bin: str,
    sensitive: list[str],
) -> dict[str, Any]:
    agent_id = f"agt_real_{runtime}_review"
    command = [
        sys.executable,
        str(SCRIPTS / "agent_worker.py"),
        "--base-url",
        base_url,
        "--workspace-id",
        WORKSPACE_ID,
        "--agent-id",
        agent_id,
        "--adapter",
        runtime,
        "--once",
        "--confirm-run",
        "--adapter-max-attempts",
        "1",
    ]
    if runtime == "hermes":
        command.extend(["--hermes-gateway-url", hermes_url, "--hermes-model", "hermes-agent", "--hermes-timeout", "180"])
    else:
        command.extend(["--openclaw-bin", openclaw_bin, "--openclaw-agent", "main", "--openclaw-timeout", "180"])
    env = os.environ.copy()
    env["AGENTOPS_API_KEY"] = token
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        timeout=240,
        check=False,
    )
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(redact(f"{runtime} Worker returned invalid JSON: {completed.stdout[-1600:]}", sensitive)) from exc
    if completed.returncode != 0:
        state = payload.get("state") if isinstance(payload, dict) else None
        last_result = state.get("last_result") if isinstance(state, dict) else None
        failure = {
            "returncode": completed.returncode,
            "status": state.get("status") if isinstance(state, dict) else None,
            "last_result": last_result if isinstance(last_result, dict) else None,
            "stderr_tail": completed.stderr[-600:],
            "raw_worker_output_omitted": True,
        }
        raise RuntimeError(redact(f"{runtime} Worker failed: {json.dumps(failure, ensure_ascii=False, sort_keys=True)}", sensitive))
    if not payload.get("ok") or payload.get("processed") != 1:
        raise RuntimeError(redact(f"{runtime} Worker did not complete one task: {payload}", sensitive))
    if token in completed.stdout or token in completed.stderr:
        raise RuntimeError(f"{runtime} Worker output exposed its Agent Gateway credential")
    return payload


def check_runtime_evidence(
    adapter: NodePgAdapter,
    runtime: str,
    worker_payload: dict[str, Any],
    sensitive: list[str],
) -> dict[str, Any]:
    iteration = (worker_payload.get("results") or [{}])[0]
    run_id = str(iteration.get("run_id") or "")
    if (
        not run_id.startswith("run_gw_")
        or iteration.get("plan_evidence_pass") is not True
        or iteration.get("provider_call_performed") is not True
        or iteration.get("dry_run") is not False
    ):
        raise RuntimeError(f"{runtime} Worker did not return a verified run/plan-evidence receipt")
    run = adapter.fetchone("SELECT run_id,status,runtime_type FROM runs WHERE run_id=?", (run_id,))
    tool = adapter.fetchone(
        """SELECT tool_name,status,target_resource,normalized_args_json,result_summary
        FROM tool_calls WHERE run_id=? AND agent_id=?""",
        (run_id, f"agt_real_{runtime}_review"),
    )
    memory = adapter.fetchone(
        """SELECT memory_id,workspace_id,task_id,agent_id,canonical_text,source_type,source_ref,review_status
        FROM memories WHERE workspace_id=? AND agent_id=? AND source_type='run_log' AND source_ref=?""",
        (WORKSPACE_ID, f"agt_real_{runtime}_review", run_id),
    )
    manifest = adapter.fetchone(
        "SELECT manifest_id,status,run_id FROM plan_evidence_manifests WHERE run_id=?",
        (run_id,),
    )
    worker_audit = adapter.fetchone(
        """SELECT actor_type,actor_id,entity_type,entity_id,metadata_json,tamper_chain_hash
        FROM audit_logs WHERE action='agent_worker.task_processed' AND entity_type='runs' AND entity_id=?""",
        (run_id,),
    )
    adapter.commit()
    expected_target = "/v1/chat/completions" if runtime == "hermes" else "local://openclaw/main"
    if not run or run["status"] != "completed" or run["runtime_type"] != runtime:
        raise RuntimeError(f"{runtime} run ledger did not close as completed")
    if not tool or tool["status"] != "completed" or expected_target not in str(tool["target_resource"]):
        raise RuntimeError(f"{runtime} tool evidence does not prove the real adapter target")
    try:
        tool_args = json.loads(str(tool["normalized_args_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{runtime} tool evidence args are invalid") from exc
    if tool_args.get("provider_call_performed") is not True or tool_args.get("dry_run") is not False:
        raise RuntimeError(f"{runtime} tool evidence does not prove a non-dry-run provider call")
    if not manifest or manifest["status"] != "verified":
        raise RuntimeError(f"{runtime} plan-evidence manifest is not verified")
    if not memory or memory["review_status"] != "candidate" or memory["source_ref"] != run_id:
        raise RuntimeError(f"{runtime} real run did not create a bound memory candidate")
    if not worker_audit or not worker_audit["tamper_chain_hash"]:
        raise RuntimeError(f"{runtime} Worker audit is absent from the tamper-evident chain")
    try:
        audit_metadata = json.loads(str(worker_audit["metadata_json"] or "{}"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{runtime} Worker audit metadata is invalid") from exc
    if not (
        worker_audit["actor_type"] == "agent"
        and worker_audit["actor_id"] == f"agt_real_{runtime}_review"
        and audit_metadata.get("provider_call_performed") is True
        and audit_metadata.get("dry_run") is False
    ):
        raise RuntimeError(f"{runtime} Worker audit does not bind the server-derived agent/provider-call evidence")
    evidence = adapter.fetchall(
        """SELECT input_summary,output_summary,error_message,raw_payload_hash FROM runtime_events
        WHERE run_id=? OR agent_id=? ORDER BY created_at""",
        (run_id, f"agt_real_{runtime}_review"),
    )
    evidence_text = json.dumps(
        {"tool": tool, "memory": memory, "audit": worker_audit, "events": evidence},
        ensure_ascii=False,
        default=str,
    )
    for secret in sensitive:
        if secret and secret in evidence_text:
            raise RuntimeError(f"{runtime} persisted runtime evidence exposed protected input material")
    return {
        "run_id": run_id,
        "memory_id": str(memory["memory_id"]),
        "manifest_id": str(manifest["manifest_id"]),
        "source_type": str(memory["source_type"]),
        "provider_call_performed": True,
        "dry_run": False,
    }


def login_owner(base_url: str, password: str) -> tuple[str, str]:
    status, payload, headers = http_json(
        "POST",
        f"{base_url}/api/mis/human-auth/login",
        {"username": OWNER_USERNAME, "password": password},
        headers={"Origin": base_url},
    )
    cookie = raw_cookie(headers)
    csrf = str(payload.get("csrf_token") or "") if isinstance(payload, dict) else ""
    if status != 200 or not cookie or not csrf:
        raise RuntimeError(f"Human Owner login failed closed with status {status}")
    return cookie, csrf


def human_review(
    adapter: NodePgAdapter,
    base_url: str,
    cookie: str,
    csrf: str,
    runtime: str,
    receipt: dict[str, str],
) -> dict[str, Any]:
    list_headers = {
        "Cookie": f"agentops_human_session={cookie}",
        "X-AgentOps-Workspace-Id": WORKSPACE_ID,
    }
    status, candidates, _ = http_json(
        "GET",
        f"{base_url}/api/mis/memories?workspace_id={WORKSPACE_ID}",
        headers=list_headers,
    )
    candidate_ids = {str(item.get("memory_id")) for item in candidates} if isinstance(candidates, list) else set()
    if status != 200 or receipt["memory_id"] not in candidate_ids:
        raise RuntimeError(f"{runtime} candidate is absent from the Human workspace queue")
    key = f"real-worker-{runtime}-approve-0001"
    write_headers = {
        **list_headers,
        "Origin": base_url,
        "X-AgentOps-CSRF": csrf,
        "Idempotency-Key": key,
    }
    route = f"{base_url}/api/mis/memories/{urllib.parse.quote(receipt['memory_id'])}/approve"
    first_status, first, _ = http_json("POST", route, {"workspace_id": WORKSPACE_ID}, headers=write_headers)
    replay_status, replay, _ = http_json("POST", route, {"workspace_id": WORKSPACE_ID}, headers=write_headers)
    foreign_headers = {**list_headers, "X-AgentOps-Workspace-Id": OTHER_WORKSPACE_ID}
    foreign_status, _, _ = http_json(
        "GET",
        f"{base_url}/api/mis/memories?workspace_id={OTHER_WORKSPACE_ID}",
        headers=foreign_headers,
    )
    memory = adapter.fetchone(
        "SELECT review_status,owner_user_id FROM memories WHERE memory_id=? AND workspace_id=?",
        (receipt["memory_id"], WORKSPACE_ID),
    )
    request_count = int((adapter.fetchone(
        "SELECT COUNT(*) AS count FROM human_memory_review_requests WHERE workspace_id=? AND memory_id=?",
        (WORKSPACE_ID, receipt["memory_id"]),
    ) or {"count": 0})["count"])
    audit_count = int((adapter.fetchone(
        """SELECT COUNT(*) AS count FROM audit_logs
        WHERE actor_type='user' AND action='memory.approved' AND entity_type='memories' AND entity_id=?""",
        (receipt["memory_id"],),
    ) or {"count": 0})["count"])
    event_count = int((adapter.fetchone(
        "SELECT COUNT(*) AS count FROM runtime_events WHERE event_type='memory.approved' AND task_id=? AND agent_id=?",
        (f"tsk_real_{runtime}_review", f"agt_real_{runtime}_review"),
    ) or {"count": 0})["count"])
    adapter.commit()
    if not (
        first_status == 200
        and first.get("outcome") == "updated"
        and replay_status == 200
        and replay.get("outcome") == "unchanged"
        and foreign_status == 403
        and memory
        and memory["review_status"] == "approved"
        and request_count == audit_count == event_count == 1
    ):
        raise RuntimeError(f"{runtime} Human review evidence or replay/isolation contract failed")
    return {
        "queue_visible": True,
        "first_outcome": first.get("outcome"),
        "replay_outcome": replay.get("outcome"),
        "cross_workspace_status": foreign_status,
        "request_count": request_count,
        "human_audit_count": audit_count,
        "human_runtime_event_count": event_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run real Hermes/OpenClaw Worker -> Human Review through Next/Postgres only.")
    parser.add_argument("--postgres-dsn", required=True, help="External Postgres URL; the smoke uses and drops an isolated schema.")
    parser.add_argument("--adapter", action="append", choices=["hermes", "openclaw"], default=[])
    parser.add_argument("--hermes-gateway-url", default=os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:8642"))
    parser.add_argument("--openclaw-bin", default=os.environ.get("OPENCLAW_BIN", shutil.which("openclaw") or "/opt/homebrew/bin/openclaw"))
    args = parser.parse_args()

    adapters = list(dict.fromkeys(args.adapter or ["hermes", "openclaw"]))
    node = shutil.which("node")
    npm = shutil.which("npm")
    if not node or not npm or not (NEXT_APP / "node_modules" / "next").exists():
        result({"ok": False, "contract": CONTRACT_ID, "error": "next_runtime_unavailable"}, [])
        return 1
    if "openclaw" in adapters and not Path(args.openclaw_bin).exists():
        result({"ok": False, "contract": CONTRACT_ID, "error": "openclaw_binary_unavailable"}, [])
        return 1

    schema = f"agentops_real_worker_review_{secrets.token_hex(8)}"
    runtime_dsn = dsn_with_search_path(args.postgres_dsn, schema)
    owner_password = "Owner-" + secrets.token_urlsafe(24)
    hmac_key = secrets.token_urlsafe(48)
    prompt_secret = "sk-" + secrets.token_urlsafe(24)
    tokens = {runtime: f"agtok_real_{runtime}_{secrets.token_urlsafe(24)}" for runtime in adapters}
    sensitive = [args.postgres_dsn, runtime_dsn, owner_password, hmac_key, prompt_secret, *tokens.values()]
    setup: NodePgAdapter | None = None
    adapter: NodePgAdapter | None = None
    next_proc: subprocess.Popen[str] | None = None
    worker_receipts: dict[str, Any] = {}
    human_receipts: dict[str, Any] = {}
    try:
        setup = NodePgAdapter(args.postgres_dsn, node)
        setup.execute(f'CREATE SCHEMA "{schema}"')
        setup.commit()
        setup.close()
        setup = None

        adapter = NodePgAdapter(runtime_dsn, node)
        adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
        seed_foundation(adapter)
        adapter.close()
        adapter = None

        migrated = run_npm(npm, runtime_dsn, ["migrate:postgres"])
        if migrated.returncode != 0:
            raise RuntimeError(redact(f"Human schema migration failed: {migrated.stdout} {migrated.stderr}", sensitive))
        bootstrapped = run_npm(
            npm,
            runtime_dsn,
            [
                "bootstrap:owner",
                "--",
                "--workspace-id",
                WORKSPACE_ID,
                "--username",
                OWNER_USERNAME,
                "--display-name",
                "Real Worker Review Owner",
                "--password-stdin",
            ],
            stdin=f"{owner_password}\n",
        )
        if bootstrapped.returncode != 0:
            raise RuntimeError(redact(f"Owner bootstrap failed: {bootstrapped.stdout} {bootstrapped.stderr}", sensitive))

        adapter = NodePgAdapter(runtime_dsn, node)
        seed_workers(adapter, adapters, tokens, prompt_secret)

        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        env = os.environ.copy()
        env.update({
            "AGENTOPS_DEPLOYMENT_MODE": "production",
            "AGENTOPS_CONTROL_PLANE_MODE": "postgres",
            "AGENTOPS_TS_CONTROL_PLANE_MODE": "postgres",
            "AGENTOPS_POSTGRES_DSN": runtime_dsn,
            "AGENTOPS_POSTGRES_SSL": "0",
            "AGENTOPS_API_BASE": f"http://127.0.0.1:{free_port()}/api",
            "AGENTOPS_ALLOWED_ORIGINS": base_url,
            "AGENTOPS_HUMAN_SESSION_HMAC_KEY": hmac_key,
            "NEXT_TELEMETRY_DISABLED": "1",
        })
        next_proc = subprocess.Popen(
            [node, str(NEXT_APP / "node_modules" / "next" / "dist" / "bin" / "next"), "dev", "-p", str(port)],
            cwd=NEXT_APP,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        wait_for_next(base_url, next_proc, sensitive)

        for runtime in adapters:
            worker_payload = run_worker(
                runtime,
                base_url,
                tokens[runtime],
                args.hermes_gateway_url,
                args.openclaw_bin,
                sensitive,
            )
            worker_receipts[runtime] = check_runtime_evidence(adapter, runtime, worker_payload, sensitive)

        cookie, csrf = login_owner(base_url, owner_password)
        sensitive.extend([cookie, csrf])
        for runtime in adapters:
            human_receipts[runtime] = human_review(
                adapter,
                base_url,
                cookie,
                csrf,
                runtime,
                worker_receipts[runtime],
            )

        result({
            "ok": True,
            "contract": CONTRACT_ID,
            "control_plane": "typescript_postgres",
            "deployment_mode": "production",
            "python_api_started": False,
            "python_or_sqlite_commercial_default": False,
            "real_runtime_execution_performed": all(
                receipt.get("provider_call_performed") is True and receipt.get("dry_run") is False
                for receipt in worker_receipts.values()
            ),
            "adapters": adapters,
            "workers": worker_receipts,
            "human_reviews": human_receipts,
            "agent_gateway_legacy_path_rewrite_verified": True,
            "raw_prompt_response_omitted": True,
            "credentials_omitted": True,
            "schema_isolated_and_ephemeral": True,
        }, sensitive)
        return 0
    except Exception as exc:
        result({
            "ok": False,
            "contract": CONTRACT_ID,
            "error_type": exc.__class__.__name__,
            "error": redact(str(exc), sensitive),
            "traceback": redact(traceback.format_exc(), sensitive)[-4000:],
            "python_api_started": False,
            "real_runtime_execution_performed": bool(worker_receipts) and all(
                receipt.get("provider_call_performed") is True and receipt.get("dry_run") is False
                for receipt in worker_receipts.values()
            ),
            "credentials_omitted": True,
        }, sensitive)
        return 1
    finally:
        if next_proc is not None:
            stop_process(next_proc)
        if adapter is not None:
            adapter.close()
        if setup is not None:
            setup.close()
        cleanup: NodePgAdapter | None = None
        try:
            cleanup = NodePgAdapter(args.postgres_dsn, node)
            cleanup.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
            cleanup.commit()
        except Exception:
            pass
        finally:
            if cleanup is not None:
                cleanup.close()


if __name__ == "__main__":
    raise SystemExit(main())
