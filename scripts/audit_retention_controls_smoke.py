#!/usr/bin/env python3
"""Verify the read-only audit retention controls API and CLI contract."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "scripts" / "agentops"
SECRET_MARKERS = ["AGENTOPS_API_KEY=", "Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"]
RAW_HOLD_MARKERS = ["Highly confidential subject", "Raw legal hold reason"]


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


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout_sec: int = 25) -> None:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate(timeout=1)
            raise RuntimeError(f"server exited early: rc={proc.returncode} stdout={out} stderr={err}")
        try:
            status, payload = http_json(base_url)
            if status == 200 and payload.get("contract_id") == "audit_retention_controls_v1":
                return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def prepare_minimal_sqlite_db(path: Path) -> None:
    sys.path.insert(0, str(ROOT))
    import server  # noqa: PLC0415

    with sqlite3.connect(path) as conn:
        conn.executescript(server.SCHEMA_SQL)
        now = "2026-06-23T00:00:00+00:00"
        conn.execute(
            "INSERT INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
            ("usr_retention_controls", "Retention Controls", "retention-controls@example.local", "admin", now),
        )
        conn.execute(
            """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "agt_retention_controls",
                "Retention Controls Agent",
                "Auditor",
                "Prevents server seed/export drift during retention controls smoke.",
                "mock",
                "mock",
                "mock-model",
                "idle",
                "standard",
                "[]",
                0,
                "usr_retention_controls",
                now,
                now,
            ),
        )
        conn.commit()


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


def start_configured_server(controls_path: Path, db_path: Path, port: int) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_RETENTION_CONTROLS_PATH"] = str(controls_path)
    env["AGENTOPS_EDITION"] = "pro_workspace"
    env.pop("AGENTOPS_ENTITLEMENTS_PATH", None)
    return subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
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


def validate_configured_registry(payload: dict, label: str) -> None:
    validate(payload, label)
    require(payload.get("status") == "ready", f"{label} configured pro registry should be ready: {payload}")
    controls = payload.get("controls") or {}
    require(controls.get("legal_hold_registry_configured") is True, f"{label} registry should be configured: {controls}")
    holds = payload.get("legal_hold_summary") or {}
    require(holds.get("total_holds") == 2, f"{label} total hold count mismatch: {holds}")
    require(holds.get("active_holds") == 1, f"{label} active hold count mismatch: {holds}")
    require(holds.get("cannot_assert_no_holds") is False, f"{label} configured registry should allow hold count assertion: {holds}")
    summaries = holds.get("holds") or []
    require(len(summaries) == 2, f"{label} hold summaries missing: {holds}")
    for summary in summaries:
        require(summary.get("raw_reason_omitted") is True, f"{label} raw reason proof missing: {summary}")
        require(summary.get("raw_subject_omitted") is True, f"{label} raw subject proof missing: {summary}")
        require("raw_reason" not in summary and "subject" not in summary, f"{label} raw hold detail leaked: {summary}")


def run_configured_fixture() -> dict:
    proc: subprocess.Popen[str] | None = None
    with tempfile.TemporaryDirectory(prefix="agentops-retention-controls-configured-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops.db"
        controls_path = tmp_path / "retention-controls.local.json"
        controls_path.write_text(
            json.dumps({
                "legal_hold_registry_configured": True,
                "retention_windows": {
                    "free_local_days": 30,
                    "pro_workspace_days": 365,
                    "max_retention_days": 3650,
                },
                "cleanup_policy": {
                    "approval_required": True,
                    "legal_hold_required_before_cleanup": True,
                    "cleanup_execution_enabled": False,
                    "cleanup_endpoint_exposed": False,
                },
                "legal_holds": [
                    {
                        "hold_id": "hold_active_configured",
                        "workspace_id": "local-demo",
                        "scope": "workspace",
                        "status": "active",
                        "reason_code": "customer_dispute",
                        "raw_reason": "Raw legal hold reason must not leave the server. agtok_hold_secret sk-hold-secret",
                        "subject": "Highly confidential subject must be omitted.",
                        "case_notes": "Highly confidential subject and sk-hold-secret must stay omitted.",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "expires_at": None,
                    },
                    {
                        "hold_id": "hold_released_configured",
                        "workspace_id": "local-demo",
                        "scope": "task",
                        "status": "released",
                        "reason_code": "matter_closed",
                        "raw_reason": "Raw legal hold reason must not leave the server. agtok_released_secret sk-released-secret",
                        "subject": "Highly confidential subject must be omitted.",
                        "case_notes": "Highly confidential subject and agtok_released_secret must stay omitted.",
                        "created_at": "2026-01-02T00:00:00+00:00",
                        "expires_at": "2026-02-01T00:00:00+00:00",
                    },
                ],
            }, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        prepare_minimal_sqlite_db(db_path)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        proc = start_configured_server(controls_path, db_path, port)
        try:
            wait_ready(base_url, proc)
            before_hash = db_dump_hash(str(db_path))
            status, api_payload = http_json(base_url)
            require(status == 200, f"configured retention controls API failed: {status} {api_payload}")
            validate_configured_registry(api_payload, "configured-api")
            dangerous_status, dangerous_payload = http_json(base_url, "cleanup=true")
            require(dangerous_status == 200, f"configured dangerous probe failed: {dangerous_status} {dangerous_payload}")
            validate(dangerous_payload, "dangerous-param")
            require(dangerous_payload.get("status") == "blocked", f"configured cleanup parameter must fail closed: {dangerous_payload}")
            proc_cli = run_cli(base_url)
            require(proc_cli.returncode == 0, f"configured retention controls CLI failed: {proc_cli.stderr or proc_cli.stdout}")
            cli_payload = json.loads(proc_cli.stdout)
            validate_configured_registry(cli_payload, "configured-cli")
            after_hash = db_dump_hash(str(db_path))
            require(before_hash == after_hash, "configured retention controls mutated the SQLite ledger")
            output_text = "\n".join([
                json.dumps(api_payload, ensure_ascii=False, sort_keys=True),
                json.dumps(dangerous_payload, ensure_ascii=False, sort_keys=True),
                proc_cli.stdout,
                proc_cli.stderr,
            ])
            require(not leaked_secret(output_text), "configured retention controls leaked token-like material")
            require(not any(marker in output_text for marker in RAW_HOLD_MARKERS), "configured retention controls leaked raw hold detail")
            return {
                "status": api_payload.get("status"),
                "active_holds": (api_payload.get("legal_hold_summary") or {}).get("active_holds"),
                "total_holds": (api_payload.get("legal_hold_summary") or {}).get("total_holds"),
                "cleanup_endpoint_exposed": (api_payload.get("controls") or {}).get("cleanup_endpoint_exposed"),
                "rows_deleted": api_payload.get("rows_deleted"),
                "read_only_hash_checked": True,
            }
        finally:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify read-only audit retention controls API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL"))
    parser.add_argument("--db-path", default=os.environ.get("AGENTOPS_DB_PATH"), help="Optional SQLite DB path used to assert read-only behavior.")
    parser.add_argument("--configured-fixture", action="store_true", help="Also start an isolated pro_workspace server with a configured legal-hold registry fixture.")
    args = parser.parse_args()
    outputs: list[str] = []
    try:
        require((ROOT / "config" / "retention-controls.example.json").exists(), "retention controls example config missing")
        base_url = args.base_url or (None if args.configured_fixture else "http://127.0.0.1:8787")
        api_payload: dict = {}
        cli_payload: dict = {}
        read_only_hash_checked = False
        if base_url:
            before_hash = db_dump_hash(args.db_path)
            status, api_payload = http_json(base_url)
            outputs.append(json.dumps(api_payload, ensure_ascii=False, sort_keys=True))
            require(status == 200, f"audit retention controls API failed: {status} {api_payload}")
            validate(api_payload, "api")

            dangerous_status, dangerous_payload = http_json(base_url, "cleanup=true")
            outputs.append(json.dumps(dangerous_payload, ensure_ascii=False, sort_keys=True))
            require(dangerous_status == 200, f"audit retention controls dangerous probe failed: {dangerous_status} {dangerous_payload}")
            validate(dangerous_payload, "dangerous-param")
            require(dangerous_payload.get("status") == "blocked", f"cleanup parameter must fail closed: {dangerous_payload}")
            require("dangerous_cleanup_parameter_rejected" in (dangerous_payload.get("blocked_reasons") or []), f"dangerous rejection reason missing: {dangerous_payload}")

            proc = run_cli(base_url)
            outputs.extend([proc.stdout, proc.stderr])
            require(proc.returncode == 0, f"audit retention controls CLI failed: {proc.stderr or proc.stdout}")
            cli_payload = json.loads(proc.stdout)
            validate(cli_payload, "cli")

            after_hash = db_dump_hash(args.db_path)
            if before_hash and after_hash:
                require(before_hash == after_hash, "audit retention controls mutated the SQLite ledger")
                read_only_hash_checked = True

        configured = run_configured_fixture() if args.configured_fixture else None
        require(not leaked_secret("\n".join(outputs)), "audit retention controls leaked token-like material")
        print(json.dumps({
            "ok": True,
            "api_status": api_payload.get("status"),
            "cli_status": cli_payload.get("status"),
            "contract_id": api_payload.get("contract_id") or "audit_retention_controls_v1",
            "cleanup_endpoint_exposed": (api_payload.get("controls") or {}).get("cleanup_endpoint_exposed"),
            "active_holds": (api_payload.get("legal_hold_summary") or {}).get("active_holds"),
            "rows_deleted": api_payload.get("rows_deleted"),
            "configured_fixture": configured,
            "read_only_hash_checked": read_only_hash_checked or bool(configured and configured.get("read_only_hash_checked")),
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
