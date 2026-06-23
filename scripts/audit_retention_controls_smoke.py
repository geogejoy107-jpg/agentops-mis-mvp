#!/usr/bin/env python3
"""Verify the read-only audit retention controls API and CLI contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_MARKERS = ["AGENTOPS_API_KEY=", "Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    return any(marker in text for marker in SECRET_MARKERS)


def db_dump_hash(path: str | None) -> str | None:
    if not path:
        return None
    db_path = Path(path).expanduser().resolve()
    if not db_path.exists():
        return None
    uri = f"file:{db_path}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        dumped = "\n".join(conn.iterdump())
    return hashlib.sha256(dumped.encode("utf-8")).hexdigest()


def http_json(base_url: str, query: str = "") -> tuple[int, dict]:
    suffix = "/api/audit/retention-controls"
    if query:
        suffix += "?" + query.lstrip("?")
    req = urllib.request.Request(base_url.rstrip("/") + suffix, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"error": exc.reason}
        return exc.code, body


def run_cli(base_url: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="agentops-audit-retention-controls-") as tmp:
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env.pop("AGENTOPS_API_KEY", None)
        return subprocess.run(
            [str(CLI), "--base-url", base_url, "audit", "retention-controls"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )


def validate(payload: dict, label: str) -> None:
    require(payload.get("provider") == "agentops-retention", f"{label} wrong provider: {payload}")
    require(payload.get("operation") == "audit_retention_controls", f"{label} wrong operation: {payload}")
    require(payload.get("contract_id") == "audit_retention_controls_v1", f"{label} contract missing: {payload}")
    require(payload.get("status") in {"ready", "attention", "gated", "blocked"}, f"{label} bad status: {payload.get('status')}")
    if label != "dangerous-param":
        require(payload.get("ok") is True, f"{label} retention controls must not be blocked: {payload}")
    require(payload.get("live_execution_performed") is False, f"{label} must not execute live work")
    require(payload.get("billing_call_performed") is False, f"{label} must not call billing")
    require(payload.get("delete_supported") is False, f"{label} must not support delete")
    require(payload.get("delete_performed") is False, f"{label} must not delete rows")
    require(payload.get("rows_deleted") == 0, f"{label} rows_deleted must stay zero")
    require(payload.get("token_omitted") is True, f"{label} token omission proof missing")

    controls = payload.get("controls") or {}
    require(controls.get("cleanup_approval_required") is True, f"{label} cleanup approval must be required: {controls}")
    require(controls.get("legal_hold_required_before_cleanup") is True, f"{label} legal-hold check must be required: {controls}")
    require(controls.get("cleanup_execution_enabled") is False, f"{label} cleanup execution must stay disabled: {controls}")
    require(controls.get("cleanup_endpoint_exposed") is False, f"{label} cleanup endpoint must stay closed: {controls}")
    require(controls.get("destructive_cleanup_supported") is False, f"{label} destructive cleanup must stay unsupported: {controls}")
    require(controls.get("delete_supported") is False, f"{label} delete_supported must stay false: {controls}")
    require(controls.get("rows_deleted") == 0, f"{label} control rows_deleted must stay zero: {controls}")

    holds = payload.get("legal_hold_summary") or {}
    registry_configured = controls.get("legal_hold_registry_configured") is True
    if registry_configured:
        require(isinstance(holds.get("total_holds"), int), f"{label} hold count missing: {holds}")
        require(isinstance(holds.get("active_holds"), int), f"{label} active hold count missing: {holds}")
        require(holds.get("cannot_assert_no_holds") is False, f"{label} configured registry should allow hold assertion: {holds}")
    else:
        require(holds.get("total_holds") is None, f"{label} unconfigured registry must not claim total holds: {holds}")
        require(holds.get("active_holds") is None, f"{label} unconfigured registry must not claim active holds: {holds}")
        require(holds.get("cannot_assert_no_holds") is True, f"{label} unconfigured registry must preserve uncertainty: {holds}")
    require(holds.get("raw_hold_details_omitted") is True, f"{label} raw hold detail omission missing: {holds}")
    require(holds.get("raw_reason_omitted") is True, f"{label} raw reason omission missing: {holds}")
    require(holds.get("raw_subject_omitted") is True, f"{label} raw subject omission missing: {holds}")

    gate_ids = {gate.get("id") for gate in payload.get("gates") or [] if isinstance(gate, dict)}
    for gate_id in {
        "cleanup_approval_required",
        "legal_hold_check_required",
        "destructive_cleanup_closed",
        "legal_hold_registry",
        "entitlement_gate",
        "raw_hold_details_omitted",
    }:
        require(gate_id in gate_ids, f"{label} missing gate {gate_id}: {payload}")

    config = payload.get("config") or {}
    require("retention-controls.example.json" in str(config.get("example_path")), f"{label} example config path missing: {config}")
    windows = payload.get("retention_windows") or {}
    require(windows.get("free_local_days") == 30, f"{label} free local window drifted: {windows}")
    require(windows.get("pro_workspace_days") == 365, f"{label} pro window drifted: {windows}")
    require(windows.get("max_retention_days") == 3650, f"{label} max window drifted: {windows}")

    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety.read_only missing")
    require(safety.get("live_execution_performed") is False, f"{label} safety live execution missing")
    require(safety.get("billing_call_performed") is False, f"{label} safety billing omission missing")
    require(safety.get("cleanup_endpoint_exposed") is False, f"{label} safety cleanup endpoint must stay closed")
    require(safety.get("delete_supported") is False, f"{label} safety delete_supported must stay false")
    require(safety.get("delete_performed") is False, f"{label} safety delete proof missing")
    require(safety.get("rows_deleted") == 0, f"{label} safety rows_deleted must stay zero")
    require(safety.get("raw_hold_details_omitted") is True, f"{label} safety raw hold omission missing")
    require(safety.get("raw_metadata_omitted") is True, f"{label} safety raw metadata omission missing")
    require(safety.get("token_omitted") is True, f"{label} safety token omission missing")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify read-only audit retention controls API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--db-path", default=os.environ.get("AGENTOPS_DB_PATH"), help="Optional SQLite DB path used to assert read-only behavior.")
    args = parser.parse_args()
    outputs: list[str] = []
    try:
        require((ROOT / "config" / "retention-controls.example.json").exists(), "retention controls example config missing")
        before_hash = db_dump_hash(args.db_path)
        status, api_payload = http_json(args.base_url)
        outputs.append(json.dumps(api_payload, ensure_ascii=False, sort_keys=True))
        require(status == 200, f"audit retention controls API failed: {status} {api_payload}")
        validate(api_payload, "api")

        dangerous_status, dangerous_payload = http_json(args.base_url, "cleanup=true")
        outputs.append(json.dumps(dangerous_payload, ensure_ascii=False, sort_keys=True))
        require(dangerous_status == 200, f"audit retention controls dangerous probe failed: {dangerous_status} {dangerous_payload}")
        validate(dangerous_payload, "dangerous-param")
        require(dangerous_payload.get("status") == "blocked", f"cleanup parameter must fail closed: {dangerous_payload}")
        require("dangerous_cleanup_parameter_rejected" in (dangerous_payload.get("blocked_reasons") or []), f"dangerous rejection reason missing: {dangerous_payload}")

        proc = run_cli(args.base_url)
        outputs.extend([proc.stdout, proc.stderr])
        require(proc.returncode == 0, f"audit retention controls CLI failed: {proc.stderr or proc.stdout}")
        cli_payload = json.loads(proc.stdout)
        validate(cli_payload, "cli")

        after_hash = db_dump_hash(args.db_path)
        if before_hash and after_hash:
            require(before_hash == after_hash, "audit retention controls mutated the SQLite ledger")

        require(not leaked_secret("\n".join(outputs)), "audit retention controls leaked token-like material")
        print(json.dumps({
            "ok": True,
            "api_status": api_payload.get("status"),
            "cli_status": cli_payload.get("status"),
            "contract_id": api_payload.get("contract_id"),
            "cleanup_endpoint_exposed": (api_payload.get("controls") or {}).get("cleanup_endpoint_exposed"),
            "active_holds": (api_payload.get("legal_hold_summary") or {}).get("active_holds"),
            "rows_deleted": api_payload.get("rows_deleted"),
            "read_only_hash_checked": bool(before_hash and after_hash),
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
