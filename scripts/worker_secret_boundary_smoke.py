#!/usr/bin/env python3
"""Verify worker credentials stay in the trusted client boundary, not prompts/output."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentops_mis_cli.worker import WORKER_SECRET_BOUNDARY_VERSION, build_task_prompt


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S%f")


def http_json(method: str, base_url: str, path: str, payload: dict | None = None, token: str | None = None, query: dict | None = None) -> tuple[int, dict | list]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urlencode({k: v for k, v in query.items() if v is not None}, doseq=True)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=90) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def parse_json_field(value) -> dict:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value or "{}")
    except Exception:
        return {}


def contains_any(text: str, needles: list[str]) -> list[str]:
    return [needle for needle in needles if needle and needle in text]


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify worker secret-boundary evidence.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    args = parser.parse_args()
    suffix = stamp()
    workspace_id = f"ws_secret_boundary_{suffix}"
    agent_id = f"agt_secret_boundary_{suffix}"
    task_secret = "sk-workerboundary-task-secret-1234567890"
    env_secret = "sk-workerboundary-env-secret-1234567890"
    url_secret = "sk-workerboundary-url-secret-1234567890"
    failures: list[str] = []

    prompt = build_task_prompt({
        "title": f"Secret boundary prompt smoke {task_secret}",
        "description": f"Do not echo Authorization: Bearer {task_secret} or api_key={url_secret}.",
        "acceptance_criteria": f"Output must not include password: {task_secret}.",
        "risk_level": "medium",
    })
    for secret in [task_secret, env_secret, url_secret]:
        require(secret not in prompt, f"prompt leaked secret {secret}: {prompt}", failures)

    token_id = None
    token = ""
    try:
        status, enrollment = http_json("POST", args.base_url, "/api/agent-gateway/enrollment/create", {
            "workspace_id": workspace_id,
            "agent_id": agent_id,
            "name": "Worker Secret Boundary Smoke",
            "runtime_type": "mock",
            "scopes": [
                "agents:write",
                "agents:heartbeat",
                "agent_plans:read",
                "agent_plans:write",
                "plan_evidence:read",
                "plan_evidence:write",
                "tasks:create",
                "tasks:read",
                "tasks:claim",
                "runs:write",
                "runtime_events:write",
                "toolcalls:write",
                "artifacts:write",
                "memories:propose",
                "evaluations:submit",
                "audit:write",
            ],
        })
        require(status == 201 and isinstance(enrollment, dict), f"enrollment failed: {status} {enrollment}", failures)
        token = enrollment.get("token") if isinstance(enrollment, dict) else ""
        token_id = enrollment.get("token_id") if isinstance(enrollment, dict) else None
        require(bool(token), f"enrollment token missing: {enrollment}", failures)

        status, task = http_json("POST", args.base_url, "/api/agent-gateway/tasks", {
            "workspace_id": workspace_id,
            "title": f"Worker secret boundary task {suffix}",
            "description": f"The worker must not reveal Authorization: Bearer {task_secret} to model output.",
            "acceptance_criteria": f"Ledger must show {WORKER_SECRET_BOUNDARY_VERSION} and omit {task_secret}.",
            "risk_level": "medium",
        }, token=token)
        task_id = task.get("task_id") if isinstance(task, dict) else None
        require(status == 201 and bool(task_id), f"task create failed: {status} {task}", failures)

        env = os.environ.copy()
        env.update({
            "AGENTOPS_BASE_URL": args.base_url,
            "AGENTOPS_WORKSPACE_ID": workspace_id,
            "AGENTOPS_AGENT_ID": agent_id,
            "AGENTOPS_API_KEY": token,
            "OPENAI_API_KEY": env_secret,
            "HERMES_GATEWAY_URL": f"http://127.0.0.1:8642/v1?api_key={url_secret}",
        })
        proc = subprocess.run(
            [
                sys.executable,
                "scripts/agent_worker.py",
                "--once",
                "--no-enforce-intake",
                "--adapter",
                "mock",
                "--task-id",
                task_id or "",
            ],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        require(proc.returncode == 0, f"worker failed: {proc.returncode} {proc.stderr or proc.stdout}", failures)
        worker_payload = json.loads(proc.stdout or "{}")
        result = (worker_payload.get("results") or [{}])[0]
        run_id = result.get("run_id")
        require(bool(run_id), f"worker result missing run_id: {worker_payload}", failures)
        require((result.get("secret_boundary") or {}).get("secret_boundary") == WORKER_SECRET_BOUNDARY_VERSION, f"worker output missing boundary: {result}", failures)

        status, run_detail = http_json("GET", args.base_url, f"/api/runs/{run_id}")
        require(status == 200 and isinstance(run_detail, dict), f"run detail failed: {status} {run_detail}", failures)
        tool = next((item for item in (run_detail.get("tool_calls") or []) if item.get("tool_name") == "agent_worker.mock"), {})
        tool_args = parse_json_field(tool.get("normalized_args_json"))
        eval_row = (run_detail.get("evaluations") or [{}])[0]
        rubric = parse_json_field(eval_row.get("rubric_json") or eval_row.get("rubric"))
        require(tool_args.get("secret_boundary") == WORKER_SECRET_BOUNDARY_VERSION, f"tool args missing boundary: {tool_args}", failures)
        require(tool_args.get("model_visible_credentials") is False, f"tool args model_visible_credentials wrong: {tool_args}", failures)
        require(tool_args.get("credential_transport") == "trusted_worker_client_only", f"tool args credential transport wrong: {tool_args}", failures)
        require(rubric.get("secret_boundary") == WORKER_SECRET_BOUNDARY_VERSION, f"evaluation rubric missing boundary: {rubric}", failures)

        status, audit_page = http_json("GET", args.base_url, "/api/audit", query={"limit": 120})
        require(status == 200, f"audit list failed: {status} {audit_page}", failures)
        audit_rows = audit_page if isinstance(audit_page, list) else audit_page.get("audit_logs") or audit_page.get("items") or []
        audit_match = next((item for item in audit_rows if item.get("action") == "agent_worker.task_processed" and item.get("entity_id") == run_id), {})
        audit_meta = parse_json_field(audit_match.get("metadata_json"))
        require(audit_meta.get("secret_boundary") == WORKER_SECRET_BOUNDARY_VERSION, f"audit metadata missing boundary: {audit_meta}", failures)

        scoped_text = "\n".join([
            proc.stdout,
            proc.stderr,
            json.dumps(result, ensure_ascii=False),
            json.dumps(run_detail, ensure_ascii=False),
            json.dumps(audit_match, ensure_ascii=False),
        ])
        leaked = contains_any(scoped_text, [task_secret, env_secret, url_secret])
        token_leaked = bool(token and token in scoped_text)
        require(not leaked and not token_leaked, f"secret-boundary smoke leaked raw values: {leaked + (['gateway_token'] if token_leaked else [])}", failures)
    finally:
        if token_id:
            http_json("POST", args.base_url, "/api/agent-gateway/enrollment/revoke", {"token_id": token_id})

    print(json.dumps({
        "ok": not failures,
        "agent_id": agent_id,
        "workspace_id": workspace_id,
        "secret_boundary": WORKER_SECRET_BOUNDARY_VERSION,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
