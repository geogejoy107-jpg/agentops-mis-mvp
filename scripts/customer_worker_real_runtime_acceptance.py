#!/usr/bin/env python3
"""Manual-live customer worker acceptance for Hermes/OpenClaw.

This is intentionally not part of deterministic CI. It is the product-level
dogfood check to run when local Hermes/OpenClaw are authorized and available.
Mock is not supported here; use mock-only smokes only as offline fallback.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


TOKEN_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"\bagtok_[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bagtsess_[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bntn_[A-Za-z0-9_-]{16,}"),
]


def token_leaked(text: str) -> bool:
    return any(pattern.search(text or "") for pattern in TOKEN_PATTERNS)


def http_json(
    method: str,
    base_url: str,
    path: str,
    payload: dict | None,
    timeout: int,
    *,
    opener=None,
    headers: dict | None = None,
) -> tuple[int, dict]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = Request(
        base_url.rstrip("/") + path,
        data=data,
        headers={"Content-Type": "application/json", **(headers or {})},
        method=method,
    )
    try:
        with (opener.open(req, timeout=timeout) if opener else urlopen(req, timeout=timeout)) as res:
            raw = res.read().decode("utf-8")
            return res.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw}
    except URLError as exc:
        raise RuntimeError(f"Cannot reach {base_url}{path}: {exc.reason}") from exc


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def authenticate_human_session(args: argparse.Namespace):
    password = os.environ.get(args.password_env, "")
    if not password:
        raise RuntimeError(f"Private Host human auth requires password env: {args.password_env}")
    opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    status, auth_status = http_json("GET", args.base_url, "/api/human-auth/status", None, args.request_timeout, opener=opener)
    if status != 200 or auth_status.get("required") is not True:
        raise RuntimeError("Private Host did not report required human authentication")
    origin = args.origin or args.base_url.rstrip("/")
    if auth_status.get("bootstrap_required"):
        setup_code = os.environ.get(args.setup_code_env, "")
        if not setup_code:
            raise RuntimeError(f"Owner bootstrap requires setup-code env: {args.setup_code_env}")
        path = "/api/human-auth/bootstrap"
        body = {
            "setup_code": setup_code,
            "username": args.username,
            "display_name": "Private Host Acceptance Owner",
            "password": password,
        }
        expected = 201
    else:
        path = "/api/human-auth/login"
        body = {"username": args.username, "password": password}
        expected = 200
    status, authenticated = http_json(
        "POST",
        args.base_url,
        path,
        body,
        args.request_timeout,
        opener=opener,
        headers={"Origin": origin},
    )
    csrf_token = str(authenticated.get("csrf_token") or "")
    if status != expected or not csrf_token or (authenticated.get("user") or {}).get("role") != "owner":
        raise RuntimeError("Private Host Owner authentication failed")
    return opener, csrf_token, origin


def run_adapter(args: argparse.Namespace, adapter: str, opener=None, csrf_token: str = "", origin: str = "") -> dict:
    stamp = time.strftime("%Y%m%d%H%M%S")
    title = f"真实 {adapter} Worker 产品级闭环验收 {stamp}"
    payload = {
        "adapter": adapter,
        "confirm_run": True,
        "title": title,
        "description": (
            "以客户任务视角审视 AgentOps MIS 工作台，输出三条可执行改进建议。"
            "不要写文件，不要调用外部服务，只通过本地 runtime 返回摘要并写入 MIS 账本。"
        ),
        "acceptance_criteria": (
            "必须返回可读中文摘要，并写入 run/tool/evaluation/runtime/audit/artifact/"
            "memory/approval/plan-evidence 证据。"
        ),
        "priority": "high",
        "risk_level": "low",
        "hermes_timeout": args.hermes_timeout,
        "hermes_max_tokens": args.hermes_max_tokens,
    }
    headers = {"Origin": origin, "X-AgentOps-CSRF": csrf_token} if opener else None
    status, result = http_json(
        "POST",
        args.base_url,
        "/api/workflows/customer-worker-task",
        payload,
        args.request_timeout,
        opener=opener,
        headers=headers,
    )
    evidence = result.get("evidence") or {}
    worker_state = ((result.get("worker_result") or {}).get("state") or {})
    failures: list[str] = []
    require(status == 201, f"{adapter}: expected HTTP 201, got {status}: {result}", failures)
    require(result.get("provider") == "agentops-worker", f"{adapter}: wrong provider: {result}", failures)
    require(result.get("workflow") == "customer_worker_task", f"{adapter}: wrong workflow: {result}", failures)
    require(result.get("adapter") == adapter, f"{adapter}: adapter mismatch: {result}", failures)
    require(result.get("dry_run") is False, f"{adapter}: live acceptance must not be dry-run: {result}", failures)
    require(result.get("ok") is True, f"{adapter}: live worker task did not complete: {result}", failures)
    require(bool(result.get("task_id")), f"{adapter}: missing task_id: {result}", failures)
    require(bool(result.get("run_id")), f"{adapter}: missing run_id: {result}", failures)
    require(bool(result.get("artifact_id")), f"{adapter}: missing artifact_id: {result}", failures)
    require(worker_state.get("base_url") == args.base_url.rstrip("/"), f"{adapter}: worker used wrong base_url: {worker_state}", failures)
    for key in ["tool_calls", "evaluations", "runtime_events", "audit_logs", "artifacts", "memories", "approvals", "plan_evidence_manifests"]:
        require(evidence.get(key, 0) >= 1, f"{adapter}: missing {key} evidence: {evidence}", failures)
    require(result.get("plan_evidence_pass") is True, f"{adapter}: plan evidence did not pass: {result}", failures)
    serialized = json.dumps(result, ensure_ascii=False)
    require(not token_leaked(serialized), f"{adapter}: output leaked token-like material", failures)
    return {
        "adapter": adapter,
        "ok": not failures,
        "status": status,
        "task_id": result.get("task_id"),
        "run_id": result.get("run_id"),
        "artifact_id": result.get("artifact_id"),
        "approval_id": result.get("approval_id"),
        "plan_id": result.get("plan_id"),
        "plan_evidence_manifest_id": result.get("plan_evidence_manifest_id"),
        "worker_base_url": worker_state.get("base_url"),
        "evidence": evidence,
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run manual-live Hermes/OpenClaw customer worker acceptance.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--adapter", action="append", choices=["hermes", "openclaw"], default=None)
    parser.add_argument("--request-timeout", type=int, default=720)
    parser.add_argument("--hermes-timeout", type=int, default=420)
    parser.add_argument("--hermes-max-tokens", type=int, default=int(os.environ.get("HERMES_MAX_TOKENS", "512")))
    parser.add_argument("--confirm-live", action="store_true", help="Required: this calls real local Hermes/OpenClaw runtimes.")
    parser.add_argument("--human-auth", action="store_true", help="Authenticate through the Private Host human Session/CSRF boundary.")
    parser.add_argument("--origin", default=os.environ.get("AGENTOPS_ACCEPTANCE_ORIGIN", ""))
    parser.add_argument("--username", default=os.environ.get("AGENTOPS_ACCEPTANCE_USERNAME", "owner"))
    parser.add_argument("--password-env", default="AGENTOPS_ACCEPTANCE_PASSWORD")
    parser.add_argument("--setup-code-env", default="AGENTOPS_OWNER_SETUP_CODE")
    args = parser.parse_args()
    adapters = args.adapter or ["hermes", "openclaw"]
    if not args.confirm_live:
        print(json.dumps({
            "ok": False,
            "error": "confirm_live_required",
            "message": "Pass --confirm-live to run real Hermes/OpenClaw product acceptance. Mock is not supported by this script.",
            "adapters": adapters,
            "token_omitted": True,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 2
    opener = None
    csrf_token = ""
    origin = ""
    if args.human_auth:
        try:
            opener, csrf_token, origin = authenticate_human_session(args)
        except RuntimeError as exc:
            print(json.dumps({
                "ok": False,
                "operation": "customer_worker_real_runtime_acceptance",
                "error": "human_authentication_failed",
                "message": str(exc),
                "credential_values_omitted": True,
                "token_omitted": True,
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 2
    results = [run_adapter(args, adapter, opener=opener, csrf_token=csrf_token, origin=origin) for adapter in adapters]
    failures = [failure for result in results for failure in result.get("failures", [])]
    output = {
        "ok": not failures,
        "operation": "customer_worker_real_runtime_acceptance",
        "base_url": args.base_url.rstrip("/"),
        "adapters": adapters,
        "results": results,
        "failures": failures,
        "mock_supported": False,
        "human_session_used": bool(args.human_auth),
        "credential_values_omitted": True,
        "token_omitted": True,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
