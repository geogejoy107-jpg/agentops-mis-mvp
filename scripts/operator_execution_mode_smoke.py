#!/usr/bin/env python3
"""Verify the read-only operator execution-mode API and CLI contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
CONTRACT_ID = "operator_execution_mode_v1"


def http_json(base_url: str, path: str, query: dict[str, str] | None = None) -> tuple[int, dict[str, Any]]:
    url = base_url.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return int(exc.code), json.loads(raw)
        except json.JSONDecodeError:
            return int(exc.code), {"raw": raw}


def run_cli(base_url: str, adapter: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("AGENTOPS_API_KEY", None)
    return subprocess.run(
        [str(CLI), "--base-url", base_url, "operator", "execution-mode", "--adapter", adapter],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def db_hash(path: str | None) -> str | None:
    if not path or not Path(path).exists():
        return None
    with sqlite3.connect(path) as conn:
        return hashlib.sha256("\n".join(conn.iterdump()).encode("utf-8")).hexdigest()


def leaked_secret(text: str) -> bool:
    markers = ["AGENTOPS_API_KEY", "Authorization:", "Bearer ", "agtok_", "agtsess_", "session_token", "token_hash", "session_hash", "sk-", "ntn_"]
    return any(marker in text for marker in markers)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate(payload: dict[str, Any], adapter: str | None = None) -> None:
    require(payload.get("provider") == "agentops-operator", f"wrong provider: {payload}")
    require(payload.get("operation") == "execution_mode", f"wrong operation: {payload}")
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"bad status: {payload}")
    if adapter:
        require(payload.get("selected_adapter") == adapter, f"wrong selected adapter for {adapter}: {payload}")
    route = payload.get("adapter_route") or {}
    safety = payload.get("safety") or {}
    require(route.get("token_omitted") is True, f"route token omission missing: {payload}")
    require(safety.get("read_only") is True, f"read_only missing: {payload}")
    require(safety.get("ledger_mutated") is False, f"ledger mutation reported: {payload}")
    require(safety.get("daemon_started") is False, f"daemon start reported: {payload}")
    require(safety.get("adapter_executed") is False, f"adapter execution reported: {payload}")
    require(safety.get("live_execution_performed") is False, f"live execution reported: {payload}")
    require(safety.get("token_omitted") is True and payload.get("token_omitted") is True, f"token omission missing: {payload}")
    require((route.get("confirm_run_wall") or {}).get("server_executes_live_without_confirm") is False, f"confirm wall unsafe: {payload}")
    require((route.get("prepared_action_wall") or {}).get("server_executes_prepared_action_without_approval") is False, f"prepared-action wall unsafe: {payload}")
    require(isinstance(payload.get("gates"), list) and payload.get("gates"), f"execution-mode gates missing: {payload}")
    require("/operator/execution-mode" in json.dumps(payload, ensure_ascii=False) or "agentops operator execution-mode" in json.dumps(payload, ensure_ascii=False), f"operator command proof missing: {payload}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify operator execution-mode read-only API and CLI.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    args = parser.parse_args(argv)
    try:
        before_hash = db_hash(os.environ.get("AGENTOPS_DB_PATH"))

        status, default_payload = http_json(args.base_url, "/api/operator/execution-mode")
        require(status == 200, f"default API failed: {status} {default_payload}")
        validate(default_payload)

        status, hermes_payload = http_json(args.base_url, "/api/operator/execution-mode", {"adapter": "hermes"})
        require(status == 200, f"Hermes API failed: {status} {hermes_payload}")
        validate(hermes_payload, "hermes")
        require((hermes_payload.get("adapter_route") or {}).get("requires_confirm_run") is True, f"Hermes confirm wall missing: {hermes_payload}")

        cli_proc = run_cli(args.base_url, "openclaw")
        require(cli_proc.returncode == 0, f"CLI failed: {cli_proc.stderr or cli_proc.stdout}")
        require(not leaked_secret(cli_proc.stdout + cli_proc.stderr), "CLI leaked token-like material")
        cli_payload = json.loads(cli_proc.stdout)
        validate(cli_payload, "openclaw")

        after_hash = db_hash(os.environ.get("AGENTOPS_DB_PATH"))
        require(before_hash == after_hash, "operator execution-mode mutated the SQLite ledger")

        transcript = json.dumps([default_payload, hermes_payload, cli_payload], ensure_ascii=False, sort_keys=True)
        require(not leaked_secret(transcript), "operator execution-mode output leaked token-like material")
        print(json.dumps({
            "ok": True,
            "contract": CONTRACT_ID,
            "base_url": args.base_url,
            "default_adapter": default_payload.get("selected_adapter"),
            "hermes_confirm_required": (hermes_payload.get("adapter_route") or {}).get("requires_confirm_run"),
            "cli_adapter": cli_payload.get("selected_adapter"),
            "db_hash_unchanged": before_hash == after_hash,
            "secret_leaked": False,
            "token_omitted": True,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "contract": CONTRACT_ID, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
