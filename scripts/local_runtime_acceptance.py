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
import tempfile
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
AGENTOPS = ROOT / "scripts" / "agentops"


def stamp() -> str:
    return f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%d%H%M%S%f')}_{uuid.uuid4().hex[:8]}"


def env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError:
        return None


def request_json(method: str, base_url: str, path: str, payload=None, query=None, timeout: int = 240):
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urlencode(query, doseq=True)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as res:
            raw = res.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: {exc.code} {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {url}: {exc.reason}") from exc


def run_prepared_hermes_task(base_url: str, hermes_timeout: int | None = None, request_timeout: int = 240) -> dict:
    return run_prepared_runtime_probe(base_url, "/api/integrations/hermes/run-task", hermes_timeout=hermes_timeout, request_timeout=request_timeout)


def prepared_runtime_status(payload: dict) -> str | None:
    return payload.get("prepared_action_status") or (payload.get("prepared_action") or {}).get("status")


def prepared_runtime_run_id(payload: dict) -> str | None:
    return payload.get("run_id") or (payload.get("prepared_action") or {}).get("run_id")


def prepared_runtime_completed(payload: dict) -> bool:
    probe = payload.get("probe") or {}
    action = payload.get("prepared_action") or {}
    ok = payload.get("ok") is True or probe.get("ok") is True
    created = payload.get("created") is True or payload.get("live_probe_performed") is True or ok
    provider_called = (
        payload.get("provider_call_performed") is True
        or payload.get("live_probe_performed") is True
        or bool(action.get("provider_side_effect_id"))
    )
    return bool(ok and created and payload.get("dry_run") is False and provider_called and prepared_runtime_run_id(payload))


def prepared_runtime_attempted(payload: dict) -> bool:
    action = payload.get("prepared_action") or {}
    return bool(
        payload.get("dry_run") is False
        and prepared_runtime_run_id(payload)
        and (
            payload.get("provider_call_performed") is True
            or payload.get("live_probe_performed") is True
            or bool(action.get("provider_side_effect_id"))
        )
    )


def prepared_runtime_prepare_payload(path: str, openclaw_timeout: int | None = None, hermes_timeout: int | None = None) -> dict:
    prefix = path.strip("/").replace("/", "_").replace("-", "_") or "runtime_probe"
    run_stamp = stamp()
    payload = {
        "confirm_run": True,
        "task_id": f"tsk_{prefix}_{run_stamp}",
        "run_id": f"run_{prefix}_{run_stamp}",
        "tool_call_id": f"tc_{prefix}_{run_stamp}",
        "approval_id": f"ap_{prefix}_{run_stamp}",
    }
    if "openclaw" in path and openclaw_timeout is not None:
        payload["openclaw_timeout"] = int(openclaw_timeout)
    if "hermes" in path and hermes_timeout is not None:
        payload["hermes_timeout"] = int(hermes_timeout)
    return payload


def run_prepared_runtime_probe(
    base_url: str,
    path: str,
    openclaw_timeout: int | None = None,
    hermes_timeout: int | None = None,
    request_timeout: int = 240,
) -> dict:
    prepare = request_json(
        "POST",
        base_url,
        path,
        prepared_runtime_prepare_payload(path, openclaw_timeout=openclaw_timeout, hermes_timeout=hermes_timeout),
        timeout=request_timeout,
    )
    prepared_action_id = prepare.get("prepared_action_id")
    approval_id = prepare.get("approval_id")
    if not prepared_action_id:
        if prepared_runtime_completed(prepare):
            return with_prepared_runtime_readback(base_url, prepare)
        raise RuntimeError(f"Prepared runtime probe did not prepare or complete a real run: {prepare}")
    if not approval_id:
        raise RuntimeError(f"Prepared runtime probe missing approval_id: {prepare}")
    approval = request_json("POST", base_url, f"/api/approvals/{approval_id}/approve", {}, timeout=request_timeout)
    approval_decision = approval.get("decision") or (approval.get("approval") or {}).get("decision")
    if approval_decision != "approved":
        raise RuntimeError(f"Prepared runtime probe approval failed: {approval}")
    resume = request_json(
        "POST",
        base_url,
        path,
        {
            "confirm_run": True,
            "prepared_action_id": prepared_action_id,
            "prompt_hash": prepare.get("prompt_hash"),
        },
        timeout=request_timeout,
    )
    if prepared_runtime_status(resume) != "consumed":
        resume = with_prepared_runtime_readback(base_url, resume, require_completed=False)
        if prepared_runtime_attempted(resume):
            return {
                **resume,
                "prepared_action_id": prepared_action_id,
                "approval_id": approval_id,
                "prepare_provider_call_performed": prepare.get("provider_call_performed"),
                "request_timeout": request_timeout,
                "acceptance_failure": "prepared_action_not_consumed",
                "runtime_failure_evidence": True,
            }
        raise RuntimeError(f"Prepared runtime probe did not consume the prepared action: {resume}")
    if not prepared_runtime_completed(resume):
        resume = with_prepared_runtime_readback(base_url, resume, require_completed=False)
        if prepared_runtime_attempted(resume):
            return {
                **resume,
                "prepared_action_id": prepared_action_id,
                "approval_id": approval_id,
                "prepare_provider_call_performed": prepare.get("provider_call_performed"),
                "request_timeout": request_timeout,
                "acceptance_failure": "runtime_not_completed",
                "runtime_failure_evidence": True,
            }
        raise RuntimeError(f"Prepared runtime probe did not complete as a real run: {resume}")
    resume = with_prepared_runtime_readback(base_url, resume)
    return {
        **resume,
        "prepared_action_id": prepared_action_id,
        "approval_id": approval_id,
        "prepare_provider_call_performed": prepare.get("provider_call_performed"),
        "request_timeout": request_timeout,
    }


def with_prepared_runtime_readback(base_url: str, payload: dict, require_completed: bool = True) -> dict:
    run_id = prepared_runtime_run_id(payload)
    if not run_id:
        raise RuntimeError(f"Prepared runtime probe missing run_id: {payload}")
    run_detail = request_json("GET", base_url, f"/api/runs/{run_id}")
    run = run_detail.get("run") or {}
    completed = run.get("status") == "completed" and run.get("approval_required") in (False, 0, "0")
    if require_completed and not completed:
        raise RuntimeError(f"Prepared runtime probe run readback is not completed: {run_detail}")
    provider_called = payload.get("provider_call_performed") is True or payload.get("live_probe_performed") is True
    return {
        **payload,
        "run_id": run_id,
        "ok": True if completed else bool(payload.get("ok") is True),
        "created": True if completed else bool(payload.get("created") is True),
        "dry_run": False,
        "provider_call_performed": True if completed else provider_called,
        "prepared_action_status": prepared_runtime_status(payload),
        "run_readback": {
            "status": run.get("status"),
            "approval_required": run.get("approval_required"),
            "error_type": run.get("error_type"),
            "error_message": run.get("error_message"),
            "duration_ms": run.get("duration_ms"),
        },
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
    outputs = {}
    with tempfile.TemporaryDirectory(prefix="agentops-cli-acceptance-") as tmp:
        env = os.environ.copy()
        env.pop("AGENTOPS_API_KEY", None)
        env.update({
            "AGENTOPS_BASE_URL": base_url,
            "AGENTOPS_WORKSPACE_ID": "local-demo",
            "AGENTOPS_AGENT_ID": agent_id,
            "AGENTOPS_CONFIG": str(Path(tmp) / "config.json"),
        })

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
        outputs["agent_plan"] = run_cli([
            "agent-plan",
            "create",
            "--agent-id",
            agent_id,
            "--task-id",
            task_id,
            "--task-understanding",
            "Verify Agent Gateway CLI runtime acceptance with a plan-bound run and safe ledger evidence.",
            "--referenced-specs",
            "PROJECT_SPEC.md,AGENT_WORKFLOW.md,BASE_INDEX.md",
            "--referenced-memories",
            "knowledge/shared/common_failures.md",
            "--referenced-bases",
            "base_local_tasks,base_local_memory",
            "--proposed-files-to-change",
            "scripts/local_runtime_acceptance.py",
            "--risk",
            "low",
            "--execution-steps",
            "READ,PLAN,RETRIEVE,COMPARE,EXECUTE,VERIFY,RECORD",
            "--verification-plan",
            "Run local_runtime_acceptance.py against the local MIS API.",
            "--rollback-plan",
            "Revert the local_runtime_acceptance.py acceptance-script change.",
        ], env)
        agent_plan_id = (outputs["agent_plan"].get("agent_plan") or {}).get("plan_id")
        if not agent_plan_id:
            raise RuntimeError(f"Agent Plan create did not return a plan_id: {outputs['agent_plan']}")
        outputs["agent_plan_verify"] = run_cli(["agent-plan", "verify", "--plan-id", str(agent_plan_id)], env)
        if (outputs["agent_plan_verify"].get("verification") or {}).get("pass") is not True:
            raise RuntimeError(f"Agent Plan verification did not pass: {outputs['agent_plan_verify']}")
        outputs["run_start"] = run_cli(["run", "start", "--task-id", task_id, "--agent-id", agent_id, "--runtime", "mock", "--input-summary", "Acceptance CLI run started"], env)
        mis_run_id = outputs["run_start"]["run"]["run_id"]
        outputs["toolcall"] = run_cli(["toolcall", "record", "--run-id", mis_run_id, "--agent-id", agent_id, "--tool", "agentops.acceptance.cli", "--category", "custom", "--risk", "low", "--summary", "CLI acceptance toolcall recorded."], env)
        tool_call_id = (outputs["toolcall"].get("tool_call") or {}).get("tool_call_id") or outputs["toolcall"].get("tool_call_id")
        if not tool_call_id:
            raise RuntimeError(f"Tool call record did not return a tool_call_id: {outputs['toolcall']}")
        outputs["run_done"] = run_cli(["run", "heartbeat", "--run-id", mis_run_id, "--status", "completed", "--summary", "Acceptance CLI run completed", "--duration-ms", "777"], env)
        outputs["eval"] = run_cli(["eval", "submit", "--run-id", mis_run_id, "--task-id", task_id, "--agent-id", agent_id, "--gate", "local_runtime_acceptance", "--score", "1", "--pass", "--notes", "Agent Gateway CLI acceptance passed."], env)
        evaluation_id = (outputs["eval"].get("evaluation") or {}).get("evaluation_id") or outputs["eval"].get("evaluation_id")
        if not evaluation_id:
            raise RuntimeError(f"Evaluation submit did not return an evaluation_id: {outputs['eval']}")
        outputs["artifact"] = run_cli([
            "artifact",
            "record",
            "--run-id",
            mis_run_id,
            "--task-id",
            task_id,
            "--agent-id",
            agent_id,
            "--type",
            "local_runtime_acceptance",
            "--title",
            "Local runtime acceptance CLI evidence",
            "--summary",
            "Safe Agent Gateway CLI acceptance evidence summary.",
            "--uri",
            f"run://{mis_run_id}",
        ], env)
        artifact_id = (outputs["artifact"].get("artifact") or {}).get("artifact_id") or outputs["artifact"].get("artifact_id")
        if not artifact_id:
            raise RuntimeError(f"Artifact record did not return an artifact_id: {outputs['artifact']}")
        outputs["memory"] = run_cli(["memory", "propose", "--task-id", task_id, "--run-id", mis_run_id, "--agent-id", agent_id, "--type", "artifact_summary", "--text", "Local runtime acceptance verified Agent Gateway CLI evidence writes."], env)
        outputs["audit"] = run_cli(["audit", "emit", "--agent-id", agent_id, "--action", "local_runtime_acceptance.cli_completed", "--entity-type", "runs", "--entity-id", mis_run_id, "--task-id", task_id, "--run-id", mis_run_id], env)
        outputs["plan_evidence"] = run_cli([
            "plan-evidence",
            "create",
            "--plan-id",
            str(agent_plan_id),
            "--run-id",
            mis_run_id,
            "--mismatch-policy",
            "block",
            "--tool-call-ids",
            str(tool_call_id),
            "--evaluation-ids",
            str(evaluation_id),
            "--artifact-ids",
            str(artifact_id),
        ], env)
        manifest_id = (outputs["plan_evidence"].get("manifest") or {}).get("manifest_id")
        manifest_verification = outputs["plan_evidence"].get("verification") or {}
        if not manifest_id or manifest_verification.get("pass") is not True:
            raise RuntimeError(f"Plan evidence manifest did not verify: {outputs['plan_evidence']}")
    return {
        "agent_id": agent_id,
        "task_id": task_id,
        "run_id": mis_run_id,
        "agent_plan_id": agent_plan_id,
        "plan_evidence_manifest_id": manifest_id,
        "outputs": outputs,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local runtime acceptance excluding Dify and Notion.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--live-openclaw", action="store_true", help="Run the OpenClaw live fixed probe.")
    parser.add_argument("--live-agnesfallback", action="store_true", help="Run the Agnesfallback CLI live fixed probe. Requires server HERMES_ALLOW_REAL_RUN=true.")
    parser.add_argument("--live-hermes", action="store_true", help="Run the Hermes default gateway fixed probe through MIS. Requires server HERMES_ALLOW_REAL_RUN=true.")
    parser.add_argument("--live-agnesfallback-api", action="store_true", help="Run the Agnesfallback OpenAI-compatible fixed probe through MIS. Requires server HERMES_ALLOW_REAL_RUN=true and AGNESFALLBACK_GATEWAY_URL to be listening.")
    parser.add_argument("--openclaw-timeout", "--openclaw-timeout-sec", dest="openclaw_timeout", type=int, default=env_int("OPENCLAW_TIMEOUT"), help="OpenClaw live probe timeout in seconds. Defaults to the server setting.")
    parser.add_argument("--hermes-timeout", "--hermes-timeout-sec", dest="hermes_timeout", type=int, default=env_int("HERMES_TIMEOUT"), help="Hermes live probe timeout in seconds. Defaults to the server setting.")
    parser.add_argument("--request-timeout", "--request-timeout-sec", dest="request_timeout", type=int, default=env_int("AGENTOPS_RUNTIME_ACCEPTANCE_REQUEST_TIMEOUT"), help="HTTP request timeout for live prepared-action resume calls.")
    parser.add_argument("--require-hermes-api", action="store_true", help="Fail unless Hermes default OpenAI-compatible API is listening and reports models.")
    parser.add_argument("--require-agnesfallback-api", action="store_true", help="Fail unless Agnesfallback OpenAI-compatible API is listening and reports models.")
    args = parser.parse_args()
    live_timeouts = [240]
    if args.live_openclaw and args.openclaw_timeout is not None:
        live_timeouts.append(max(1, int(args.openclaw_timeout)) + 90)
    if (args.live_hermes or args.live_agnesfallback or args.live_agnesfallback_api) and args.hermes_timeout is not None:
        live_timeouts.append(max(1, int(args.hermes_timeout)) + 90)
    request_timeout = max(1, int(args.request_timeout)) if args.request_timeout is not None else max(live_timeouts)

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
        capture("POST /api/integrations/openclaw/probe live", lambda: run_prepared_runtime_probe(args.base_url, "/api/integrations/openclaw/probe", openclaw_timeout=args.openclaw_timeout, request_timeout=request_timeout))
    capture("GET /api/integrations/hermes/status", lambda: request_json("GET", args.base_url, "/api/integrations/hermes/status"))
    if args.require_hermes_api:
        capture("Hermes default API models", lambda: assert_hermes_api_available(evidence["GET /api/integrations/hermes/status"]))
    if args.require_agnesfallback_api:
        capture("Agnesfallback OpenAI-compatible API models", lambda: assert_agnesfallback_api_available(evidence["GET /api/integrations/hermes/status"]))
    capture("POST /api/integrations/hermes/probe", lambda: request_json("POST", args.base_url, "/api/integrations/hermes/probe", {}))
    if args.live_hermes:
        capture("POST /api/integrations/hermes/run-task live", lambda: run_prepared_hermes_task(args.base_url, hermes_timeout=args.hermes_timeout, request_timeout=request_timeout))
    if args.live_agnesfallback:
        capture("POST /api/integrations/hermes/cli-probe live", lambda: run_prepared_runtime_probe(args.base_url, "/api/integrations/hermes/cli-probe", hermes_timeout=args.hermes_timeout, request_timeout=request_timeout))
    if args.live_agnesfallback_api:
        capture("POST /api/integrations/hermes/chat-completion-probe live", lambda: run_prepared_runtime_probe(args.base_url, "/api/integrations/hermes/chat-completion-probe", hermes_timeout=args.hermes_timeout, request_timeout=request_timeout))

    if args.live_openclaw:
        probe = evidence.get("POST /api/integrations/openclaw/probe live", {})
        if not (probe.get("ok") and probe.get("dry_run") is False):
            ok = False
            checks.append(fail("OpenClaw live probe did not complete as a prepared real run."))
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
        "openclaw_timeout": args.openclaw_timeout,
        "hermes_timeout": args.hermes_timeout,
        "request_timeout": request_timeout,
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
