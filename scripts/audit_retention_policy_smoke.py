#!/usr/bin/env python3
"""Verify the read-only audit retention policy API and CLI contract."""
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
    suffix = "/api/audit/retention-policy"
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
    with tempfile.TemporaryDirectory(prefix="agentops-audit-retention-") as tmp:
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env.pop("AGENTOPS_API_KEY", None)
        return subprocess.run(
            [str(CLI), "--base-url", base_url, "audit", "retention-policy"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )


def validate(payload: dict, label: str) -> None:
    require(payload.get("provider") == "agentops-retention", f"{label} wrong provider: {payload}")
    require(payload.get("operation") == "audit_retention_policy", f"{label} wrong operation: {payload}")
    require(payload.get("contract_id") == "audit_retention_policy_v1", f"{label} contract missing: {payload}")
    require(payload.get("status") in {"ready", "attention", "gated", "blocked"}, f"{label} bad status: {payload.get('status')}")
    if label not in {"dangerous-param", "invalid-days"}:
        require(payload.get("ok") is True, f"{label} retention preview must not be blocked: {payload}")
    require(payload.get("live_execution_performed") is False, f"{label} must not execute live work")
    require(payload.get("billing_call_performed") is False, f"{label} must not call billing")
    require(payload.get("delete_supported") is False, f"{label} must not support delete: {payload}")
    require(payload.get("delete_performed") is False, f"{label} must not delete rows")
    require(payload.get("rows_deleted") == 0, f"{label} rows_deleted must stay zero")
    require(payload.get("token_omitted") is True, f"{label} token omission proof missing")

    policy = payload.get("policy") or {}
    require(policy.get("retention_days") in {30, 365}, f"{label} unexpected retention days: {policy}")
    require(policy.get("dry_run_only") is True, f"{label} dry-run proof missing: {policy}")
    require(policy.get("cleanup_execution_enabled") is False, f"{label} cleanup must stay disabled: {policy}")
    require(policy.get("delete_performed") is False, f"{label} policy delete_performed must stay false: {policy}")
    require(policy.get("rows_deleted") == 0, f"{label} policy rows_deleted must stay zero: {policy}")
    require(policy.get("raw_rows_omitted") is True, f"{label} raw row omission missing: {policy}")
    require(policy.get("raw_metadata_omitted") is True, f"{label} raw metadata omission missing: {policy}")
    require(policy.get("token_omitted") is True, f"{label} policy token omission missing: {policy}")
    require(isinstance(policy.get("cutoff_at"), str) and policy.get("cutoff_at"), f"{label} cutoff missing: {policy}")

    counts = payload.get("counts") or {}
    total = counts.get("total_audit_logs")
    expired = counts.get("expired_candidates")
    retained = counts.get("retained_count")
    require(isinstance(total, int) and total >= 0, f"{label} total count invalid: {counts}")
    require(isinstance(expired, int) and expired >= 0, f"{label} expired count invalid: {counts}")
    require(isinstance(retained, int) and retained >= 0, f"{label} retained count invalid: {counts}")
    require(total == expired + retained, f"{label} count arithmetic mismatch: {counts}")
    require(isinstance(counts.get("unparseable_created_at"), int), f"{label} unparseable count missing: {counts}")

    gate_ids = {gate.get("id") for gate in payload.get("gates") or [] if isinstance(gate, dict)}
    for gate_id in {
        "retention_policy_configured",
        "retention_dry_run",
        "destructive_cleanup_disabled",
        "raw_audit_rows_omitted",
        "entitlement_gate",
    }:
        require(gate_id in gate_ids, f"{label} missing gate {gate_id}: {payload}")

    entitlement = payload.get("entitlement") or {}
    require(entitlement.get("capability") == "longer_audit_retention", f"{label} entitlement capability missing: {entitlement}")
    require(entitlement.get("required_edition") == "pro_workspace", f"{label} required edition drifted: {entitlement}")
    require(entitlement.get("enforcement") == "read_only_preview", f"{label} enforcement must be preview-only: {entitlement}")

    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety.read_only missing")
    require(safety.get("dry_run") is True, f"{label} safety dry-run missing")
    require(safety.get("live_execution_performed") is False, f"{label} safety live execution missing")
    require(safety.get("billing_call_performed") is False, f"{label} safety billing omission missing")
    require(safety.get("delete_performed") is False, f"{label} safety delete proof missing")
    require(safety.get("rows_deleted") == 0, f"{label} safety rows_deleted must stay zero")
    require(safety.get("raw_rows_omitted") is True, f"{label} safety raw row omission missing")
    require(safety.get("raw_metadata_omitted") is True, f"{label} safety raw metadata omission missing")
    require(safety.get("token_omitted") is True, f"{label} safety token omission missing")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify read-only audit retention policy API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--db-path", default=os.environ.get("AGENTOPS_DB_PATH"), help="Optional SQLite DB path used to assert read-only behavior.")
    args = parser.parse_args()
    outputs: list[str] = []
    try:
        before_hash = db_dump_hash(args.db_path)
        status, api_payload = http_json(args.base_url)
        outputs.append(json.dumps(api_payload, ensure_ascii=False, sort_keys=True))
        require(status == 200, f"audit retention policy API failed: {status} {api_payload}")
        validate(api_payload, "api")

        gated_status, gated_payload = http_json(args.base_url, "retention_days=365")
        outputs.append(json.dumps(gated_payload, ensure_ascii=False, sort_keys=True))
        require(gated_status == 200, f"audit retention longer policy probe failed: {gated_status} {gated_payload}")
        validate(gated_payload, "longer-retention")
        require(gated_payload.get("status") == "gated", f"free local longer retention must be gated: {gated_payload}")

        dangerous_status, dangerous_payload = http_json(args.base_url, "delete=true")
        outputs.append(json.dumps(dangerous_payload, ensure_ascii=False, sort_keys=True))
        require(dangerous_status == 200, f"audit retention dangerous probe failed: {dangerous_status} {dangerous_payload}")
        validate(dangerous_payload, "dangerous-param")
        require(dangerous_payload.get("status") == "blocked", f"delete parameter must fail closed: {dangerous_payload}")
        require("dangerous_cleanup_parameter_rejected" in (dangerous_payload.get("blocked_reasons") or []), f"dangerous rejection reason missing: {dangerous_payload}")

        proc = run_cli(args.base_url)
        outputs.extend([proc.stdout, proc.stderr])
        require(proc.returncode == 0, f"audit retention policy CLI failed: {proc.stderr or proc.stdout}")
        cli_payload = json.loads(proc.stdout)
        validate(cli_payload, "cli")

        after_hash = db_dump_hash(args.db_path)
        if before_hash and after_hash:
            require(before_hash == after_hash, "audit retention policy mutated the SQLite ledger")

        require(not leaked_secret("\n".join(outputs)), "audit retention policy leaked token-like material")
        print(json.dumps({
            "ok": True,
            "api_status": api_payload.get("status"),
            "cli_status": cli_payload.get("status"),
            "contract_id": api_payload.get("contract_id"),
            "retention_days": (api_payload.get("policy") or {}).get("retention_days"),
            "expired_candidates": (api_payload.get("counts") or {}).get("expired_candidates"),
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
