#!/usr/bin/env python3
"""Verify deployment readiness API and CLI output."""
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


def http_json(base_url: str) -> tuple[int, dict]:
    req = urllib.request.Request(base_url.rstrip("/") + "/api/deployment/readiness", headers={"Accept": "application/json"}, method="GET")
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
    with tempfile.TemporaryDirectory(prefix="agentops-deployment-readiness-") as tmp:
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env.pop("AGENTOPS_API_KEY", None)
        return subprocess.run(
            [str(CLI), "--base-url", base_url, "deployment", "readiness"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )


def validate(payload: dict, label: str) -> None:
    require(payload.get("provider") == "agentops-deployment", f"{label} wrong provider: {payload}")
    require(payload.get("operation") == "deployment_readiness", f"{label} wrong operation: {payload}")
    require(payload.get("contract_id") == "deployment_readiness_v1", f"{label} contract missing: {payload}")
    require(isinstance(payload.get("generated_at"), str) and payload.get("generated_at"), f"{label} generated_at missing")
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"{label} bad status: {payload.get('status')}")
    require(payload.get("deployment_ready") is (payload.get("status") == "ready"), f"{label} deployment_ready mismatch: {payload}")
    require(payload.get("token_omitted") is True, f"{label} token omission proof missing")
    require(payload.get("live_execution_performed") is False, f"{label} must not execute live work")
    gates = payload.get("gates") or []
    gate_ids = {gate.get("id") for gate in gates if isinstance(gate, dict)}
    for gate_id in {
        "local_readiness",
        "production_security",
        "storage_backend",
        "backup_restore",
        "signed_audit_export",
        "retention_policy",
        "sso_connector_policy",
        "omission_contract",
    }:
        require(gate_id in gate_ids, f"{label} missing gate {gate_id}: {payload}")
    require((payload.get("backup_restore") or {}).get("restore_requires_cli_confirmation") is True, f"{label} restore confirmation missing")
    require((payload.get("backup_restore") or {}).get("browser_restore_write_exposed") is False, f"{label} browser restore must remain closed")
    signed = payload.get("signed_audit_export") or {}
    require(signed.get("utility_ready") is True and signed.get("contract_ready") is True, f"{label} signed audit export proof missing: {signed}")
    require(signed.get("customer_key_required") is True, f"{label} signed export key gate missing: {signed}")
    require(signed.get("tamper_detection") is True, f"{label} tamper detection missing: {signed}")
    require(signed.get("raw_metadata_omitted") is True, f"{label} raw metadata omission missing: {signed}")
    retention = payload.get("retention") or {}
    require(retention.get("status") in {"ready", "attention", "gated"}, f"{label} retention status must be explicit: {retention}")
    require(retention.get("contract_id") == "audit_retention_policy_v1", f"{label} retention contract missing: {retention}")
    require(retention.get("dry_run_only") is True, f"{label} retention must stay dry-run: {retention}")
    require(retention.get("cleanup_execution_enabled") is False, f"{label} retention cleanup must stay disabled: {retention}")
    require(retention.get("delete_performed") is False, f"{label} retention delete proof missing: {retention}")
    require(retention.get("rows_deleted") == 0, f"{label} retention rows_deleted must stay zero: {retention}")
    require(retention.get("raw_rows_omitted") is True, f"{label} retention raw rows must stay omitted: {retention}")
    require(isinstance(retention.get("expired_candidates"), int), f"{label} retention expired count missing: {retention}")
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety.read_only missing")
    require(safety.get("browser_restore_write_exposed") is False, f"{label} browser restore safety missing")
    require(safety.get("token_omitted") is True, f"{label} safety.token_omitted missing")
    require(safety.get("raw_metadata_omitted") is True, f"{label} safety.raw_metadata_omitted missing")
    require(safety.get("signing_key_omitted") is True, f"{label} signing key omission missing")
    require(safety.get("delete_performed") is False, f"{label} retention delete safety missing")
    require("deployment_readiness_v1" in set(payload.get("contracts") or []), f"{label} contract list missing")
    require("audit_retention_policy_v1" in set(payload.get("contracts") or []), f"{label} retention contract list missing")
    require(isinstance(payload.get("next_actions"), list) and payload.get("next_actions"), f"{label} next_actions missing")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify deployment readiness API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--db-path", default=os.environ.get("AGENTOPS_DB_PATH"), help="Optional SQLite DB path used to assert read-only behavior.")
    args = parser.parse_args()
    outputs: list[str] = []
    try:
        before_hash = db_dump_hash(args.db_path)
        status, api_payload = http_json(args.base_url)
        outputs.append(json.dumps(api_payload, ensure_ascii=False, sort_keys=True))
        require(status == 200, f"deployment readiness API failed: {status} {api_payload}")
        validate(api_payload, "api")

        proc = run_cli(args.base_url)
        outputs.extend([proc.stdout, proc.stderr])
        require(proc.returncode == 0, f"deployment readiness CLI failed: {proc.stderr or proc.stdout}")
        cli_payload = json.loads(proc.stdout)
        validate(cli_payload, "cli")
        after_hash = db_dump_hash(args.db_path)
        if before_hash and after_hash:
            require(before_hash == after_hash, "deployment readiness mutated the SQLite ledger")

        require(not leaked_secret("\n".join(outputs)), "deployment readiness leaked token-like material")
        print(json.dumps({
            "ok": True,
            "api_status": api_payload.get("status"),
            "cli_status": cli_payload.get("status"),
            "gate_count": len(api_payload.get("gates") or []),
            "signed_export_status": (api_payload.get("signed_audit_export") or {}).get("status"),
            "retention_status": (api_payload.get("retention") or {}).get("status"),
            "read_only_hash_checked": bool(before_hash and after_hash),
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
