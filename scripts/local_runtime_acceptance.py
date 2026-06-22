#!/usr/bin/env python3
"""
Acceptance runner for local AgentOps MIS runtime paths excluding Dify and Notion.

It verifies:
- Core MIS API is reachable.
- Agent Gateway CLI can register/heartbeat/pull/claim/run/tool/eval/memory/audit.
- OpenClaw status/import work, with optional live probe.
- Hermes/Agnesfallback status works, with optional Agnesfallback live CLI probe.

It intentionally does not call Dify or Notion endpoints.
"""
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
AGENTOPS = ROOT / "scripts" / "agentops"


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")


def request_json(method: str, base_url: str, path: str, payload=None, query=None):
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urlencode(query, doseq=True)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=240) as res:
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc


def run_prepared_hermes_task(base_url: str) -> dict:
    return run_prepared_runtime_probe(base_url, "/api/integrations/hermes/run-task")


def run_prepared_runtime_probe(base_url: str, path: str) -> dict:
    prepare = request_json("POST", base_url, path, {"confirm_run": True})
    prepared_action_id = prepare.get("prepared_action_id")
    approval_id = prepare.get("approval_id")
    if not prepared_action_id:
        return prepare
    if not approval_id:
        raise RuntimeError(f"Prepared runtime probe missing approval_id: {prepare}")
    approval = request_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {})
    if approval.get("decision") != "approved":
        raise RuntimeError(f"Prepared runtime probe approval failed: {approval}")
    resume = request_json("POST", base_url, path, {
        "confirm_run": True,
        "prepared_action_id": prepared_action_id,
        "prompt_hash": prepare.get("prompt_hash"),
    })
    return {
        **resume,
        "prepared_action_id": prepared_action_id,
        "approval_id": approval_id,
        "prepare_provider_call_performed": prepare.get("provider_call_performed"),
    }


def run_cli(args: list[str], env: dict) -> dict:
    proc = subprocess.run([str(AGENTOPS), *args], cwd=ROOT, env=env, text=True, capture_output=True, timeout=60)
    if proc.returncode != 0:
        raise RuntimeError(f"agentops {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return json.loads(proc.stdout)


def check(condition: bool, name: str, detail=None):
    return {"name": name, "ok": bool(condition), "detail": detail}


def fail(message: str):
    return {"name": message, "ok": False, "detail": message}


def assert_hermes_api_available(status: dict) -> dict:
    if not status.get("api_listening"):
        raise RuntimeError(f"Hermes API is not listening: {status.get('default_gateway', {}).get('last_error')}")
    gateway_url = status.get("gateway_url") or "http://127.0.0.1:8642"
    models = request_absolute_json("GET", gateway_url.rstrip("/") + "/v1/models")
    return {"gateway_url": gateway_url, "models": models.get("data", models)}


def assert_agnesfallback_api_available(status: dict) -> dict:
    agnes = status.get("agnesfallback") or {}
    if not agnes.get("api_server_listening"):
        raise RuntimeError(f"Agnesfallback OpenAI-compatible API is not listening at {agnes.get('gateway_url')}")
    gateway_url = agnes.get("gateway_url") or "http://127.0.0.1:8643"
    models = request_absolute_json("GET", gateway_url.rstrip("/") + "/v1/models")
    return {"gateway_url": gateway_url, "models": models.get("data", models)}


def assert_connector_available(connectors: list[dict], connector_id: str) -> dict:
    for connector in connectors:
        if connector.get("runtime_connector_id") == connector_id:
            if connector.get("status") != "available":
                raise RuntimeError(f"{connector_id} status is {connector.get('status')}: {connector.get('last_error')}")
            return connector
    raise RuntimeError(f"{connector_id} not found in runtime connectors")


def request_absolute_json(method: str, url: str, payload=None):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=60) as res:
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed: {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc


def run_agent_gateway_cli_smoke(base_url: str) -> dict:
    run_id = stamp()
    agent_id = f"agt_accept_cli_{run_id}"
    task_id = f"tsk_accept_cli_{run_id}"
    env = os.environ.copy()
    env.update({
        "AGENTOPS_BASE_URL": base_url,
        "AGENTOPS_WORKSPACE_ID": "local-demo",
        "AGENTOPS_AGENT_ID": agent_id,
    })

    outputs = {}
    outputs["login"] = run_cli(["login", "--base-url", base_url, "--workspace-id", "local-demo", "--agent-id", agent_id], env)
    outputs["register"] = run_cli(["agent", "register", "--id", agent_id, "--name", "Acceptance CLI Worker", "--role", "Runtime Acceptance Worker", "--runtime", "mock"], env)
    outputs["heartbeat"] = run_cli(["agent", "heartbeat", "--status", "idle", "--summary", "Acceptance CLI ready."], env)

    task = request_json("POST", base_url, "/api/tasks", {
        "task_id": task_id,
        "title": "Local runtime acceptance CLI task",
        "description": "Verify Agent Gateway CLI writes task/run/tool/eval/memory/audit evidence.",
        "owner_agent_id": agent_id,
        "status": "planned",
        "priority": "medium",
        "risk_level": "low",
        "acceptance_criteria": "CLI path records evidence in MIS.",
    })
    outputs["task"] = task
    outputs["pull"] = run_cli(["task", "pull", "--agent-id", agent_id, "--limit", "5"], env)
    outputs["claim"] = run_cli(["task", "claim", "--task-id", task_id, "--agent-id", agent_id], env)
    outputs["run_start"] = run_cli(["run", "start", "--task-id", task_id, "--agent-id", agent_id, "--input-summary", "Acceptance CLI run started"], env)
    mis_run_id = outputs["run_start"]["run"]["run_id"]
    outputs["toolcall"] = run_cli(["toolcall", "record", "--run-id", mis_run_id, "--agent-id", agent_id, "--tool", "agentops.acceptance.cli", "--category", "custom", "--risk", "low", "--summary", "CLI acceptance toolcall recorded."], env)
    outputs["run_done"] = run_cli(["run", "heartbeat", "--run-id", mis_run_id, "--status", "completed", "--summary", "Acceptance CLI run completed", "--duration-ms", "777"], env)
    outputs["eval"] = run_cli(["eval", "submit", "--run-id", mis_run_id, "--task-id", task_id, "--agent-id", agent_id, "--gate", "local_runtime_acceptance", "--score", "1", "--pass", "--notes", "Agent Gateway CLI acceptance passed."], env)
    outputs["memory"] = run_cli(["memory", "propose", "--task-id", task_id, "--run-id", mis_run_id, "--agent-id", agent_id, "--type", "artifact_summary", "--text", "Local runtime acceptance verified Agent Gateway CLI evidence writes."], env)
    outputs["audit"] = run_cli(["audit", "emit", "--agent-id", agent_id, "--action", "local_runtime_acceptance.cli_completed", "--entity-type", "runs", "--entity-id", mis_run_id, "--task-id", task_id, "--run-id", mis_run_id], env)
    return {"agent_id": agent_id, "task_id": task_id, "run_id": mis_run_id, "outputs": outputs}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local runtime acceptance excluding Dify and Notion.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--live-openclaw", action="store_true", help="Run the OpenClaw live fixed probe.")
    parser.add_argument("--live-agnesfallback", action="store_true", help="Run the Agnesfallback CLI live fixed probe. Requires server HERMES_ALLOW_REAL_RUN=true.")
    parser.add_argument("--live-hermes", action="store_true", help="Run the Hermes default gateway fixed probe through MIS. Requires server HERMES_ALLOW_REAL_RUN=true.")
    parser.add_argument("--live-agnesfallback-api", action="store_true", help="Run the Agnesfallback OpenAI-compatible fixed probe through MIS. Requires server HERMES_ALLOW_REAL_RUN=true and AGNESFALLBACK_GATEWAY_URL to be listening.")
    parser.add_argument("--require-hermes-api", action="store_true", help="Fail unless Hermes default OpenAI-compatible API is listening and reports models.")
    parser.add_argument("--require-agnesfallback-api", action="store_true", help="Fail unless Agnesfallback OpenAI-compatible API is listening and reports models.")
    args = parser.parse_args()

    checks = []
    evidence = {}
    ok = True

    def capture(name, fn):
        nonlocal ok
        try:
            result = fn()
            evidence[name] = result
            checks.append(check(True, name, summarize(result)))
        except Exception as exc:
            ok = False
            checks.append(fail(f"{name}: {exc}"))

    capture("GET /api/dashboard/metrics", lambda: request_json("GET", args.base_url, "/api/dashboard/metrics"))
    capture("GET /api/runtime-connectors", lambda: request_json("GET", args.base_url, "/api/runtime-connectors"))
    capture("Agent Gateway runtime connector", lambda: assert_connector_available(evidence["GET /api/runtime-connectors"], "rtc_agent_gateway_local"))
    capture("OpenClaw runtime connector", lambda: assert_connector_available(evidence["GET /api/runtime-connectors"], "rtc_openclaw_local"))
    capture("Agent Gateway CLI smoke", lambda: run_agent_gateway_cli_smoke(args.base_url))
    capture("GET /api/integrations/openclaw/status", lambda: request_json("GET", args.base_url, "/api/integrations/openclaw/status"))
    capture("POST /api/integrations/openclaw/import", lambda: request_json("POST", args.base_url, "/api/integrations/openclaw/import", {}))
    if args.live_openclaw:
        capture("POST /api/integrations/openclaw/probe live", lambda: request_json("POST", args.base_url, "/api/integrations/openclaw/probe", {}))
    capture("GET /api/integrations/hermes/status", lambda: request_json("GET", args.base_url, "/api/integrations/hermes/status"))
    if args.require_hermes_api:
        capture("Hermes default API models", lambda: assert_hermes_api_available(evidence["GET /api/integrations/hermes/status"]))
    if args.require_agnesfallback_api:
        capture("Agnesfallback OpenAI-compatible API models", lambda: assert_agnesfallback_api_available(evidence["GET /api/integrations/hermes/status"]))
    capture("POST /api/integrations/hermes/probe", lambda: request_json("POST", args.base_url, "/api/integrations/hermes/probe", {}))
    if args.live_hermes:
        capture("POST /api/integrations/hermes/run-task live", lambda: run_prepared_hermes_task(args.base_url))
    if args.live_agnesfallback:
        capture("POST /api/integrations/hermes/cli-probe live", lambda: run_prepared_runtime_probe(args.base_url, "/api/integrations/hermes/cli-probe"))
    if args.live_agnesfallback_api:
        capture("POST /api/integrations/hermes/chat-completion-probe live", lambda: run_prepared_runtime_probe(args.base_url, "/api/integrations/hermes/chat-completion-probe"))

    if args.live_openclaw:
        probe = evidence.get("POST /api/integrations/openclaw/probe live", {})
        if not probe.get("probe", {}).get("ok"):
            ok = False
            checks.append(fail("OpenClaw live probe did not return ok=true."))
    if args.live_agnesfallback:
        probe = evidence.get("POST /api/integrations/hermes/cli-probe live", {})
        if not (probe.get("ok") and probe.get("dry_run") is False):
            ok = False
            checks.append(fail("Agnesfallback live CLI probe did not complete as a real run."))
    if args.live_hermes:
        probe = evidence.get("POST /api/integrations/hermes/run-task live", {})
        if not (probe.get("ok") and probe.get("dry_run") is False):
            ok = False
            checks.append(fail("Hermes default gateway live run-task did not complete as a real run."))
    if args.live_agnesfallback_api:
        probe = evidence.get("POST /api/integrations/hermes/chat-completion-probe live", {})
        if not (probe.get("ok") and probe.get("dry_run") is False):
            ok = False
            checks.append(fail("Agnesfallback OpenAI-compatible live probe did not complete as a real run."))

    output = {
        "ok": ok,
        "scope": "local runtime acceptance excluding Dify and Notion",
        "base_url": args.base_url,
        "live_openclaw": args.live_openclaw,
        "live_agnesfallback": args.live_agnesfallback,
        "live_hermes": args.live_hermes,
        "live_agnesfallback_api": args.live_agnesfallback_api,
        "require_hermes_api": args.require_hermes_api,
        "require_agnesfallback_api": args.require_agnesfallback_api,
        "checks": checks,
        "evidence_keys": sorted(evidence.keys()),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0 if ok else 1


def summarize(value):
    if isinstance(value, dict):
        if "run_id" in value:
            return {"run_id": value.get("run_id"), "ok": value.get("ok"), "dry_run": value.get("dry_run")}
        if "gateway_url" in value and "models" in value:
            models = value.get("models") or []
            model_ids = [item.get("id") for item in models if isinstance(item, dict)]
            return {"gateway_url": value.get("gateway_url"), "model_ids": model_ids[:5]}
        if "provider" in value:
            return {key: value.get(key) for key in ["provider", "status", "configured", "api_listening", "agents_count", "cron_jobs_count"] if key in value}
        if "agent_id" in value and "run_id" in value:
            return {"agent_id": value["agent_id"], "task_id": value["task_id"], "run_id": value["run_id"]}
        return {"keys": sorted(value.keys())[:12]}
    if isinstance(value, list):
        return {"items": len(value)}
    return value


if __name__ == "__main__":
    raise SystemExit(main())
