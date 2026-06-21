#!/usr/bin/env python3
"""Non-live v1.5 product acceptance for the local AgentOps MIS loop.

This runner is intentionally read-only: it calls status/readiness endpoints and
matching CLI readback commands only. It does not create tasks/runs, start
workers, dispatch work, or invoke live Hermes/OpenClaw execution.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"

KNOWN_LOCAL_STATUSES = {"ready", "attention", "blocked"}
KNOWN_WORKER_STATUSES = {"ready", "running", "attention", "blocked", "degraded"}
KNOWN_FLEET_STATUSES = {"ready", "attention", "blocked"}
KNOWN_ADAPTER_STATUSES = {"ready", "degraded", "blocked"}
KNOWN_ADAPTER_READINESS = {"ready", "review_required", "blocked", "unavailable"}
KNOWN_GATE_STATUSES = {"pass", "warn", "fail", "info", "ready", "attention", "blocked", "degraded", "unknown", "needs_seed_or_run", "needs_demo_run", "missing_docs"}
KNOWN_GATEWAY_STATUSES = {"ready", "attention", "blocked", "degraded"}
KNOWN_ADAPTERS = {"mock", "hermes", "openclaw"}
LEDGER_COUNT_KEYS = {
    "tasks",
    "completed_tasks",
    "runs",
    "completed_runs",
    "tool_calls",
    "evaluations",
    "audit_logs",
    "artifacts",
    "memories",
    "approvals",
    "workflow_jobs",
    "closed_loop_runs",
}
SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bagtok_[A-Za-z0-9_]+"),
    re.compile(r"\bagtsess_[A-Za-z0-9_]+"),
    re.compile(r"\bsk-[A-Za-z0-9]{8,}"),
    re.compile(r"\bntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_API_KEY", re.IGNORECASE),
]


class Acceptance:
    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def add(self, name: str, ok: bool, detail: Any = None) -> None:
        item: dict[str, Any] = {"name": name, "ok": bool(ok)}
        if detail is not None:
            item["detail"] = detail
        self.checks.append(item)

    def require(self, condition: bool, name: str, detail: Any = None) -> None:
        self.add(name, condition, detail)

    @property
    def ok(self) -> bool:
        return all(item.get("ok") for item in self.checks)

    @property
    def failures(self) -> list[dict[str, Any]]:
        return [item for item in self.checks if not item.get("ok")]


def http_json(base_url: str, path: str, timeout: int = 30) -> tuple[int, dict[str, Any], str]:
    req = urllib.request.Request(
        base_url.rstrip("/") + path,
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return resp.status, json.loads(raw) if raw else {}, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"error": raw or str(exc.reason)}
        return exc.code, body, raw


def run_cli(base_url: str, args: list[str], config_path: Path) -> tuple[subprocess.CompletedProcess[str], dict[str, Any] | None]:
    env = os.environ.copy()
    env["AGENTOPS_CONFIG"] = str(config_path)
    env["AGENTOPS_BASE_URL"] = base_url
    env["AGENTOPS_WORKSPACE_ID"] = "local-demo"
    env.pop("AGENTOPS_API_KEY", None)
    proc = subprocess.run(
        [str(CLI), "--base-url", base_url, *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )
    try:
        return proc, json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        return proc, None


def secret_leaked(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in SECRET_PATTERNS)


def walk_json(value: Any, path: str = "$"):
    if isinstance(value, dict):
        yield path, value
        for key, child in value.items():
            yield from walk_json(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from walk_json(child, f"{path}[{index}]")


def validate_token_omission(acc: Acceptance, label: str, payload: Any) -> None:
    found = []
    bad = []
    for path, item in walk_json(payload):
        if isinstance(item, dict) and "token_omitted" in item:
            found.append(path)
            if item.get("token_omitted") is not True:
                bad.append({"path": path, "value": item.get("token_omitted")})
    acc.require(not bad, f"{label}: token_omitted true where present", bad)
    acc.require(bool(found), f"{label}: token_omitted marker present", {"paths": found[:8]})


def validate_no_live_execution(acc: Acceptance, label: str, payload: Any) -> None:
    bad = []
    found = []
    for path, item in walk_json(payload):
        if isinstance(item, dict) and "live_execution_performed" in item:
            found.append(path)
            if item.get("live_execution_performed") is not False:
                bad.append({"path": path, "value": item.get("live_execution_performed")})
    acc.require(bool(found), f"{label}: live_execution_performed marker present", None)
    acc.require(not bad, f"{label}: live_execution_performed false", bad)


def validate_local_readiness(acc: Acceptance, label: str, payload: dict[str, Any]) -> None:
    acc.require(payload.get("provider") == "agentops-local", f"{label}: provider", payload.get("provider"))
    acc.require(payload.get("operation") == "local_readiness", f"{label}: operation", payload.get("operation"))
    acc.require(payload.get("status") in KNOWN_LOCAL_STATUSES, f"{label}: known status", payload.get("status"))
    validate_token_omission(acc, label, payload)
    validate_no_live_execution(acc, label, payload)

    gates = payload.get("gates")
    acc.require(isinstance(gates, list) and bool(gates), f"{label}: gates present", len(gates or []))
    gate_ids = {gate.get("id") for gate in gates or [] if isinstance(gate, dict)}
    for gate_id in {"agent_gateway", "worker_fleet", "production_security", "adapter_route", "runbook"}:
        acc.require(gate_id in gate_ids, f"{label}: gate {gate_id} present", sorted(gate_ids))
    gate_statuses = [gate.get("status") for gate in gates or [] if isinstance(gate, dict)]
    acc.require(all(status in KNOWN_GATE_STATUSES for status in gate_statuses), f"{label}: gate statuses known", gate_statuses)
    actions = payload.get("next_actions")
    acc.require(isinstance(actions, list) and bool(actions), f"{label}: next_actions present", actions)

    evidence = payload.get("evidence") or {}
    for key in LEDGER_COUNT_KEYS:
        if key in evidence:
            acc.require(isinstance(evidence.get(key), int), f"{label}: evidence {key} integer", evidence.get(key))
    acc.require((payload.get("adapter_readiness") or {}).get("recommended_adapter") in KNOWN_ADAPTERS, f"{label}: recommended adapter known", payload.get("adapter_readiness"))
    security = payload.get("security_production_readiness") or {}
    acc.require(security.get("operation") == "production_readiness", f"{label}: security readiness operation", security)
    validate_token_omission(acc, f"{label}: security readiness", security)
    validate_no_live_execution(acc, f"{label}: security readiness", security)


def validate_worker_status(acc: Acceptance, label: str, payload: dict[str, Any]) -> None:
    acc.require(payload.get("provider") == "agentops-worker", f"{label}: provider", payload.get("provider"))
    acc.require(payload.get("status") in KNOWN_WORKER_STATUSES, f"{label}: known status", payload.get("status"))
    validate_token_omission(acc, label, payload)

    fleet = payload.get("fleet_health") or {}
    acc.require(fleet.get("overall") in KNOWN_FLEET_STATUSES, f"{label}: fleet overall known", fleet.get("overall"))
    acc.require(isinstance(fleet.get("gates"), list) and bool(fleet.get("gates")), f"{label}: fleet gates present", fleet.get("gates"))
    acc.require(isinstance(fleet.get("recommended_actions"), list) and bool(fleet.get("recommended_actions")), f"{label}: fleet actions present", fleet.get("recommended_actions"))
    gate_statuses = [gate.get("status") for gate in fleet.get("gates") or [] if isinstance(gate, dict)]
    acc.require(all(status in KNOWN_GATE_STATUSES for status in gate_statuses), f"{label}: fleet gate statuses known", gate_statuses)
    acc.require((payload.get("adapter_readiness") or {}).get("recommended_adapter") in KNOWN_ADAPTERS, f"{label}: recommended adapter known", payload.get("adapter_readiness"))
    for key in ("worker_count", "running_workers", "pending_worker_tasks", "stuck_worker_tasks", "remote_worker_count"):
        acc.require(isinstance(payload.get(key), int), f"{label}: {key} integer", payload.get(key))


def validate_adapter_readiness(acc: Acceptance, label: str, payload: dict[str, Any]) -> None:
    acc.require(payload.get("provider") == "agentops-worker", f"{label}: provider", payload.get("provider"))
    acc.require(payload.get("status") in KNOWN_ADAPTER_STATUSES, f"{label}: known status", payload.get("status"))
    validate_token_omission(acc, label, payload)
    validate_no_live_execution(acc, label, payload)

    summary = payload.get("summary") or {}
    acc.require(summary.get("recommended_adapter") in KNOWN_ADAPTERS, f"{label}: recommended adapter known", summary)
    adapters = payload.get("adapters") or {}
    for adapter in ("mock", "hermes", "openclaw"):
        item = adapters.get(adapter) or {}
        acc.require(item.get("adapter") == adapter, f"{label}: {adapter} present", item)
        acc.require(item.get("readiness") in KNOWN_ADAPTER_READINESS, f"{label}: {adapter} readiness known", item.get("readiness"))
        acc.require(isinstance(item.get("recommended_action"), str) and bool(item.get("recommended_action")), f"{label}: {adapter} action present", item.get("recommended_action"))
        acc.require((item.get("checks") or {}).get("live_execution_performed") is False, f"{label}: {adapter} check is non-live", item.get("checks"))


def validate_gateway_status(acc: Acceptance, label: str, payload: dict[str, Any]) -> None:
    acc.require(payload.get("provider") == "agent_gateway", f"{label}: provider", payload.get("provider"))
    acc.require(payload.get("status") in KNOWN_GATEWAY_STATUSES, f"{label}: known status", payload.get("status"))
    validate_token_omission(acc, label, payload)
    acc.require(isinstance(payload.get("valid_scopes"), list) and bool(payload.get("valid_scopes")), f"{label}: scopes present", payload.get("valid_scopes"))
    auth = payload.get("auth") or {}
    acc.require(isinstance(auth, dict) and bool(auth.get("mode")), f"{label}: auth metadata present", auth)


def ledger_counts(payload: dict[str, Any]) -> dict[str, int]:
    evidence = payload.get("evidence") or {}
    return {key: int(evidence[key]) for key in LEDGER_COUNT_KEYS if isinstance(evidence.get(key), int)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run v1.5 local product acceptance without live sync/execution.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--verbose", action="store_true", help="Include every individual check in the JSON output.")
    args = parser.parse_args()

    acc = Acceptance()
    endpoints = {
        "/api/local/readiness": None,
        "/api/workers/status": None,
        "/api/workers/adapter-readiness": None,
        "/api/agent-gateway/status": None,
    }
    cli_results: list[dict[str, Any]] = []
    limitation = None
    before_counts: dict[str, int] = {}
    after_counts: dict[str, int] = {}
    ledger_stability: dict[str, Any] = {}

    try:
        status, payload, raw = http_json(args.base_url, "/api/local/readiness")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        limitation = f"server unavailable at {args.base_url}: {exc}"
        acc.add("server available", False, limitation)
        summary = {
            "ok": False,
            "base_url": args.base_url,
            "scope": "v1.5 local product acceptance, non-live",
            "limitation": limitation,
            "failure_count": len(acc.failures),
            "failures": acc.failures,
        }
        if args.verbose:
            summary["checks"] = acc.checks
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return 1

    endpoints["/api/local/readiness"] = payload
    acc.require(status == 200, "GET /api/local/readiness HTTP 200", status)
    acc.require(not secret_leaked(raw), "GET /api/local/readiness no token-like strings", None)
    if status != 200:
        limitation = f"expected v1.5 local readiness endpoint unavailable at {args.base_url}: HTTP {status}"
    if status == 200:
        validate_local_readiness(acc, "GET /api/local/readiness", payload)
        before_counts = ledger_counts(payload)

    validators = {
        "/api/workers/status": validate_worker_status,
        "/api/workers/adapter-readiness": validate_adapter_readiness,
        "/api/agent-gateway/status": validate_gateway_status,
    }
    for path, validator in validators.items():
        try:
            status, payload, raw = http_json(args.base_url, path)
            endpoints[path] = payload
            acc.require(status == 200, f"GET {path} HTTP 200", status)
            acc.require(not secret_leaked(raw), f"GET {path} no token-like strings", None)
            if status == 200:
                validator(acc, f"GET {path}", payload)
        except Exception as exc:
            acc.add(f"GET {path}", False, str(exc))

    with tempfile.TemporaryDirectory(prefix="agentops-v15-acceptance-") as tmp:
        config_path = Path(tmp) / "config.json"
        commands = [
            ("local readiness", ["local", "readiness"], validate_local_readiness),
            ("worker status", ["worker", "status"], validate_worker_status),
            ("worker readiness", ["worker", "readiness"], validate_adapter_readiness),
        ]
        acc.require(CLI.exists(), "repo CLI exists", str(CLI))
        for name, command, validator in commands:
            try:
                proc, payload = run_cli(args.base_url, command, config_path)
                text = (proc.stdout or "") + (proc.stderr or "")
                cli_results.append({
                    "name": name,
                    "returncode": proc.returncode,
                    "json": isinstance(payload, dict),
                    "stdout_bytes": len(proc.stdout or ""),
                    "stderr_bytes": len(proc.stderr or ""),
                })
                acc.require(proc.returncode == 0, f"CLI {name} exit 0", {"returncode": proc.returncode, "stderr": (proc.stderr or "")[-240:]})
                acc.require(not secret_leaked(text), f"CLI {name} no token-like strings", None)
                acc.require(isinstance(payload, dict), f"CLI {name} emitted JSON", (proc.stdout or "")[:240])
                if isinstance(payload, dict):
                    validator(acc, f"CLI {name}", payload)
            except Exception as exc:
                acc.add(f"CLI {name}", False, str(exc))

    try:
        status, payload, raw = http_json(args.base_url, "/api/local/readiness")
        acc.require(status == 200, "post-check GET /api/local/readiness HTTP 200", status)
        acc.require(not secret_leaked(raw), "post-check local readiness no token-like strings", None)
        if status == 200:
            after_counts = ledger_counts(payload)
            changed = {
                key: {"before": before_counts.get(key), "after": after_counts.get(key)}
                for key in sorted(set(before_counts) | set(after_counts))
                if before_counts.get(key) != after_counts.get(key)
            }
            worker_status_payload = endpoints.get("/api/workers/status") or {}
            active_workers = int(worker_status_payload.get("running_workers") or 0)
            active_sessions = int(worker_status_payload.get("active_remote_sessions") or 0)
            drift_explained = bool(changed and (active_workers > 0 or active_sessions > 0))
            ledger_stability = {
                "changed": changed,
                "active_workers": active_workers,
                "active_remote_sessions": active_sessions,
                "drift_explained_by_active_workers": drift_explained,
            }
            acc.require(
                not changed or drift_explained,
                "ledger counts unchanged by acceptance runner or explained by active workers",
                ledger_stability,
            )
    except Exception as exc:
        acc.add("post-check local readiness", False, str(exc))

    summary = {
        "ok": acc.ok,
        "base_url": args.base_url,
        "scope": "v1.5 local product acceptance, non-live",
        "live_execution_performed": False,
        "mutating_actions_performed": False,
        "checked_endpoints": sorted(path for path, payload in endpoints.items() if payload is not None),
        "checked_cli": cli_results,
        "ledger_counts_before": before_counts,
        "ledger_counts_after": after_counts,
        "ledger_stability": ledger_stability,
        "passed_count": len(acc.checks) - len(acc.failures),
        "check_count": len(acc.checks),
        "failure_count": len(acc.failures),
        "failures": acc.failures,
    }
    if limitation:
        summary["limitation"] = limitation
    if args.verbose:
        summary["checks"] = acc.checks
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 0 if acc.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
