#!/usr/bin/env python3
"""Verify the read-only customer delivery board API and CLI."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def http_json(method: str, base_url: str, path: str, payload: dict | None = None):
    data = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if payload is not None else None
    req = Request(base_url.rstrip("/") + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urlopen(req, timeout=60) as res:
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


def token_like_leaked(text: str) -> bool:
    return any(marker in text for marker in ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify customer delivery board.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--skip-cli", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []

    status, project = http_json("POST", args.base_url, "/api/workflows/customer-task-templates/run", {
        "template_id": "tpl_customer_kb_qa_bot",
    })
    require(status == 201 and project.get("ok") is True, f"template fixture failed: {status} {project}", failures)
    fixture_artifact_id = project.get("artifact_id")
    require(bool(fixture_artifact_id), f"template fixture missing artifact id: {project}", failures)

    status, board = http_json("GET", args.base_url, "/api/workflows/customer-delivery-board?limit=10")
    require(status == 200, f"board status mismatch: {status} {board}", failures)
    require(board.get("provider") == "agentops-customer", f"wrong provider: {board}", failures)
    require(board.get("operation") == "customer_delivery_board", f"wrong operation: {board}", failures)
    require(board.get("status") in {"ready", "attention", "empty"}, f"wrong status: {board}", failures)
    safety = board.get("safety") or {}
    require(safety.get("read_only") is True, f"board must be read-only: {safety}", failures)
    require(safety.get("ledger_mutated") is False, f"board must not mutate ledger: {safety}", failures)
    require(safety.get("live_execution_performed") is False, f"board must not run live work: {safety}", failures)
    require(safety.get("token_omitted") is True, f"token omission missing: {safety}", failures)
    require(isinstance(board.get("deliveries"), list), f"deliveries missing: {board}", failures)
    require(isinstance(board.get("gates"), list) and board.get("gates"), f"gates missing: {board}", failures)
    for delivery in board.get("deliveries") or []:
        require(bool(delivery.get("delivery_id")), f"delivery id missing: {delivery}", failures)
        require(delivery.get("status") in {"ready", "waiting_approval", "in_progress", "needs_attention"}, f"bad delivery status: {delivery}", failures)
        require(isinstance(delivery.get("evidence"), dict), f"delivery evidence missing: {delivery}", failures)
    fixture_delivery = next((item for item in board.get("deliveries") or [] if item.get("artifact_id") == fixture_artifact_id), None)
    require(fixture_delivery is not None, f"fixture delivery artifact missing from board: {fixture_artifact_id}", failures)
    if fixture_delivery:
        evidence = fixture_delivery.get("evidence") or {}
        evaluation_summary = fixture_delivery.get("evaluation_summary") or {}
        require(bool(fixture_delivery.get("task_id")), f"fixture delivery missing task link: {fixture_delivery}", failures)
        require(bool(fixture_delivery.get("run_id")), f"fixture delivery missing run link: {fixture_delivery}", failures)
        require(fixture_delivery.get("artifact_id") == fixture_artifact_id, f"fixture delivery artifact mismatch: {fixture_delivery}", failures)
        require(bool(fixture_delivery.get("task_url") and fixture_delivery.get("run_url")), f"fixture delivery missing UI/API links: {fixture_delivery}", failures)
        require(bool(fixture_delivery.get("artifact_url") or (fixture_delivery.get("artifact_link") or {}).get("api_url")), f"fixture delivery missing artifact link: {fixture_delivery}", failures)
        require(len(fixture_delivery.get("approval_ids") or []) >= 1, f"fixture delivery missing approval id: {fixture_delivery}", failures)
        require(len(fixture_delivery.get("approval_links") or []) >= 1, f"fixture delivery missing approval link: {fixture_delivery}", failures)
        require(
            {row.get("approval_id") for row in fixture_delivery.get("approval_links") or []}.issuperset(set(fixture_delivery.get("approval_ids") or [])),
            f"fixture delivery approval links do not cover approval ids: {fixture_delivery}",
            failures,
        )
        require(len(fixture_delivery.get("evaluation_ids") or []) >= 1, f"fixture delivery missing evaluation ids: {fixture_delivery}", failures)
        require(len(fixture_delivery.get("evaluation_links") or []) >= 1, f"fixture delivery missing evaluation links: {fixture_delivery}", failures)
        require(len(fixture_delivery.get("audit_ids") or []) >= 1, f"fixture delivery missing audit ids: {fixture_delivery}", failures)
        require(len(fixture_delivery.get("audit_links") or []) >= 1, f"fixture delivery missing audit links: {fixture_delivery}", failures)
        require(len(fixture_delivery.get("tool_call_ids") or []) >= 1, f"fixture delivery missing tool-call ids: {fixture_delivery}", failures)
        require(len(fixture_delivery.get("tool_call_links") or []) >= 1, f"fixture delivery missing tool-call links: {fixture_delivery}", failures)
        require(int(evaluation_summary.get("count") or 0) >= 1, f"fixture delivery missing evaluation summary: {fixture_delivery}", failures)
        require(int(evidence.get("tool_calls") or 0) >= 1, f"fixture delivery missing tool-call evidence: {fixture_delivery}", failures)
        require(int(evidence.get("evaluations") or 0) >= 1, f"fixture delivery missing evaluation evidence: {fixture_delivery}", failures)
        require(int(evidence.get("artifacts") or 0) >= 1, f"fixture delivery missing artifact evidence: {fixture_delivery}", failures)
        require(int(evidence.get("audit_logs") or 0) >= 1, f"fixture delivery missing audit evidence: {fixture_delivery}", failures)
        require("delivery_approval_gate" in fixture_delivery, f"fixture delivery missing approval gate: {fixture_delivery}", failures)

    cli_stdout = ""
    cli_stderr = ""
    if not args.skip_cli:
        env = os.environ.copy()
        env["AGENTOPS_BASE_URL"] = args.base_url
        env.pop("AGENTOPS_API_KEY", None)
        proc = subprocess.run(
            ["./scripts/agentops", "workflow", "delivery-board", "--limit", "5"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        cli_stdout = proc.stdout
        cli_stderr = proc.stderr
        cli_payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
        require(proc.returncode == 0, f"CLI failed: {proc.stderr or proc.stdout}", failures)
        require(cli_payload.get("operation") == "customer_delivery_board", f"CLI payload mismatch: {cli_payload}", failures)
        require((cli_payload.get("safety") or {}).get("read_only") is True, f"CLI safety mismatch: {cli_payload}", failures)

    serialized = "\n".join([json.dumps(board, ensure_ascii=False), cli_stdout, cli_stderr])
    require(not token_like_leaked(serialized), "delivery board leaked token-like material", failures)

    print(json.dumps({
        "ok": not failures,
        "status": board.get("status"),
        "summary": board.get("summary"),
        "delivery_count": len(board.get("deliveries") or []),
        "fixture_artifact_id": fixture_artifact_id,
        "cli_checked": not args.skip_cli,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
