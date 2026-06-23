#!/usr/bin/env python3
"""Verify deployment readiness API and CLI output."""
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
RAW_ENTERPRISE_MARKERS = ["raw-sso-client-secret", "PRIVATE KEY", "raw-private-connector-token", "internal-admin-endpoint.local"]


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
            if status == 200 and payload.get("contract_id") == "deployment_readiness_v1":
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
            ("usr_deployment_retention", "Deployment Retention", "deployment-retention@example.local", "admin", now),
        )
        conn.execute(
            """INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                "agt_deployment_retention",
                "Deployment Retention Agent",
                "Auditor",
                "Prevents server seed/export drift during deployment readiness retention fixture smoke.",
                "mock",
                "mock",
                "mock-model",
                "idle",
                "standard",
                "[]",
                0,
                "usr_deployment_retention",
                now,
                now,
            ),
        )
        conn.commit()


def http_json(base_url: str, path: str = "/api/deployment/readiness") -> tuple[int, dict]:
    req = urllib.request.Request(base_url.rstrip("/") + path, headers={"Accept": "application/json"}, method="GET")
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


def run_cli_enterprise_controls(base_url: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="agentops-deployment-enterprise-controls-") as tmp:
        env = os.environ.copy()
        env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
        env.pop("AGENTOPS_API_KEY", None)
        return subprocess.run(
            [str(CLI), "--base-url", base_url, "deployment", "enterprise-controls"],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=45,
            check=False,
        )


def write_enterprise_controls_fixture(path: Path) -> None:
    path.write_text(
        json.dumps({
            "sso": {
                "configured": True,
                "provider_type": "oidc",
                "issuer_url": "https://idp.example.local/oidc",
                "redirect_uri": "https://agentops.example.local/auth/callback",
                "client_id": "agentops-mis",
                "client_secret": "raw-sso-client-secret sk-enterprise-sso",
                "certificate_pem": "-----BEGIN PRIVATE KEY-----\nnot-real\n-----END PRIVATE KEY-----",
            },
            "private_connector_policy": {
                "registry_configured": True,
                "trust_policy_configured": True,
                "connectors": [
                    {
                        "connector_id": "conn_private_dify",
                        "provider": "dify",
                        "status": "active",
                        "base_url": "https://internal-admin-endpoint.local/dify",
                        "client_secret": "raw-private-connector-token sk-private-connector",
                    },
                    {
                        "connector_id": "conn_internal_kb",
                        "provider": "custom",
                        "status": "inactive",
                        "base_url": "https://internal-admin-endpoint.local/kb",
                        "client_secret": "raw-private-connector-token sk-private-kb",
                    },
                ],
            },
        }, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def start_configured_server(controls_path: Path | None, db_path: Path, port: int, edition: str, enterprise_controls_path: Path | None = None) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    if controls_path:
        env["AGENTOPS_RETENTION_CONTROLS_PATH"] = str(controls_path)
    else:
        env.pop("AGENTOPS_RETENTION_CONTROLS_PATH", None)
    if enterprise_controls_path:
        env["AGENTOPS_ENTERPRISE_CONTROLS_PATH"] = str(enterprise_controls_path)
    else:
        env.pop("AGENTOPS_ENTERPRISE_CONTROLS_PATH", None)
    env["AGENTOPS_EDITION"] = edition
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
        "retention_controls",
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
    require(retention.get("controls_contract_id") == "audit_retention_controls_v1", f"{label} retention controls contract missing: {retention}")
    require(retention.get("cleanup_approval_required") is True, f"{label} cleanup approval proof missing: {retention}")
    require(retention.get("legal_hold_required_before_cleanup") is True, f"{label} legal-hold check proof missing: {retention}")
    require(retention.get("cleanup_endpoint_exposed") is False, f"{label} cleanup endpoint must stay closed: {retention}")
    require(retention.get("destructive_cleanup_supported") is False, f"{label} destructive cleanup must stay unsupported: {retention}")
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety.read_only missing")
    require(safety.get("browser_restore_write_exposed") is False, f"{label} browser restore safety missing")
    require(safety.get("token_omitted") is True, f"{label} safety.token_omitted missing")
    require(safety.get("raw_metadata_omitted") is True, f"{label} safety.raw_metadata_omitted missing")
    require(safety.get("signing_key_omitted") is True, f"{label} signing key omission missing")
    require(safety.get("delete_performed") is False, f"{label} retention delete safety missing")
    require("deployment_readiness_v1" in set(payload.get("contracts") or []), f"{label} contract list missing")
    require("audit_retention_policy_v1" in set(payload.get("contracts") or []), f"{label} retention contract list missing")
    require("audit_retention_controls_v1" in set(payload.get("contracts") or []), f"{label} retention controls contract list missing")
    require(isinstance(payload.get("next_actions"), list) and payload.get("next_actions"), f"{label} next_actions missing")


def validate_configured_retention(payload: dict, label: str) -> None:
    validate(payload, label)
    retention = payload.get("retention") or {}
    gates = {
        gate.get("id"): gate
        for gate in (payload.get("gates") or [])
        if isinstance(gate, dict) and gate.get("id")
    }
    require(retention.get("status") == "ready", f"{label} configured retention policy should be ready: {retention}")
    require(retention.get("controls_status") == "ready", f"{label} configured retention controls should be ready: {retention}")
    require(retention.get("capability_enabled") is True, f"{label} pro retention capability should be enabled: {retention}")
    require(retention.get("legal_hold_registry_configured") is True, f"{label} registry should be configured: {retention}")
    require(retention.get("active_legal_holds") == 1, f"{label} active hold count mismatch: {retention}")
    require((gates.get("retention_policy") or {}).get("status") == "ready", f"{label} retention policy gate should be ready: {gates}")
    require((gates.get("retention_controls") or {}).get("status") == "ready", f"{label} retention controls gate should be ready: {gates}")
    require(retention.get("cleanup_endpoint_exposed") is False, f"{label} cleanup endpoint must remain closed: {retention}")
    require(retention.get("destructive_cleanup_supported") is False, f"{label} destructive cleanup must remain unsupported: {retention}")
    require(retention.get("delete_performed") is False, f"{label} delete_performed must remain false: {retention}")
    require(retention.get("rows_deleted") == 0, f"{label} rows_deleted must remain zero: {retention}")
    require("audit_retention_controls_v1" in set(payload.get("contracts") or []), f"{label} controls contract missing")


def validate_configured_enterprise(payload: dict, label: str) -> None:
    validate(payload, label)
    require(payload.get("edition") == "enterprise_byoc", f"{label} should use enterprise_byoc edition: {payload}")
    enterprise = payload.get("enterprise_byoc") or {}
    for capability in {"postgres_adapter", "sso_hooks", "signed_audit_exports", "custom_connector_sdk"}:
        require(enterprise.get(capability) is True, f"{label} enterprise capability {capability} should be enabled: {enterprise}")
    gates = {
        gate.get("id"): gate
        for gate in (payload.get("gates") or [])
        if isinstance(gate, dict) and gate.get("id")
    }
    sso_gate = gates.get("sso_connector_policy") or {}
    require(sso_gate.get("status") == "ready", f"{label} SSO/private connector gate should be ready: {sso_gate}")
    require(sso_gate.get("ok") is True, f"{label} SSO/private connector gate should be ok: {sso_gate}")
    require("enterprise deployment policy review" in str(sso_gate.get("next_action")), f"{label} SSO next action should be enterprise review, not enablement: {sso_gate}")
    signed = payload.get("signed_audit_export") or {}
    require(signed.get("status") == "ready", f"{label} signed audit export should be ready under enterprise: {signed}")
    require(signed.get("capability_enabled") is True, f"{label} signed audit capability should be enabled: {signed}")
    require(signed.get("required_edition") == "enterprise_byoc", f"{label} signed audit required edition mismatch: {signed}")
    require(signed.get("customer_key_required") is True, f"{label} signed audit customer-key gate missing: {signed}")
    require(signed.get("tamper_detection") is True, f"{label} signed audit tamper proof missing: {signed}")
    require(signed.get("raw_metadata_omitted") is True, f"{label} signed audit raw metadata omission missing: {signed}")
    storage = payload.get("storage") or {}
    require(storage.get("selected_backend") == "sqlite", f"{label} enterprise fixture should not silently select Postgres: {storage}")
    require(storage.get("fallback_performed") is False, f"{label} enterprise fixture should not perform storage fallback: {storage}")
    controls = payload.get("enterprise_controls") or {}
    require(controls.get("status") == "ready", f"{label} embedded enterprise controls should be ready: {controls}")
    require(controls.get("contract_id") == "enterprise_byoc_controls_v1", f"{label} enterprise controls contract missing: {controls}")
    require(controls.get("sso_configured") is True, f"{label} embedded SSO configured proof missing: {controls}")
    require(controls.get("issuer_configured") is True, f"{label} embedded issuer proof missing: {controls}")
    require(controls.get("redirect_uri_configured") is True, f"{label} embedded redirect proof missing: {controls}")
    require(controls.get("private_connector_registry_configured") is True, f"{label} private connector registry proof missing: {controls}")
    require(controls.get("private_connector_trust_policy_configured") is True, f"{label} private connector trust proof missing: {controls}")
    require(controls.get("private_connector_total") == 2, f"{label} private connector total mismatch: {controls}")
    require(controls.get("private_connector_active") == 1, f"{label} private connector active mismatch: {controls}")
    require(controls.get("raw_metadata_omitted") is True, f"{label} raw metadata omission missing: {controls}")
    require(controls.get("client_secret_omitted") is True, f"{label} client secret omission missing: {controls}")
    require("enterprise_byoc_controls_v1" in set(payload.get("contracts") or []), f"{label} enterprise controls contract list missing")


def validate_enterprise_controls(payload: dict, label: str) -> None:
    require(payload.get("provider") == "agentops-deployment", f"{label} wrong provider: {payload}")
    require(payload.get("operation") == "enterprise_byoc_controls", f"{label} wrong operation: {payload}")
    require(payload.get("contract_id") == "enterprise_byoc_controls_v1", f"{label} contract missing: {payload}")
    require(payload.get("edition") == "enterprise_byoc", f"{label} edition mismatch: {payload}")
    require(payload.get("status") == "ready", f"{label} controls should be ready: {payload}")
    require(payload.get("entitlement_ready") is True, f"{label} entitlement proof missing: {payload}")
    sso = payload.get("sso") or {}
    require(sso.get("configured") is True, f"{label} SSO configured missing: {sso}")
    require(sso.get("provider_type") == "oidc", f"{label} SSO provider mismatch: {sso}")
    require(sso.get("issuer_configured") is True, f"{label} issuer proof missing: {sso}")
    require(sso.get("redirect_uri_configured") is True, f"{label} redirect proof missing: {sso}")
    require(sso.get("client_id_configured") is True, f"{label} client id proof missing: {sso}")
    require(sso.get("client_secret_omitted") is True, f"{label} client secret omission missing: {sso}")
    require(sso.get("certificate_omitted") is True, f"{label} certificate omission missing: {sso}")
    connector = payload.get("private_connector_policy") or {}
    require(connector.get("registry_configured") is True, f"{label} registry proof missing: {connector}")
    require(connector.get("trust_policy_configured") is True, f"{label} trust policy proof missing: {connector}")
    require(connector.get("total_connectors") == 2, f"{label} connector total mismatch: {connector}")
    require(connector.get("active_connectors") == 1, f"{label} active connector mismatch: {connector}")
    require(connector.get("raw_config_omitted") is True, f"{label} raw config omission missing: {connector}")
    require(connector.get("client_secret_omitted") is True, f"{label} connector secret omission missing: {connector}")
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} read-only proof missing: {safety}")
    require(safety.get("live_execution_performed") is False, f"{label} should not execute live controls: {safety}")
    require(safety.get("token_omitted") is True, f"{label} token omission missing: {safety}")
    require(safety.get("raw_metadata_omitted") is True, f"{label} raw metadata omission missing: {safety}")
    require(safety.get("client_secret_omitted") is True, f"{label} client secret omission missing: {safety}")
    require(payload.get("live_execution_performed") is False, f"{label} live execution top-level proof missing")
    require(payload.get("token_omitted") is True, f"{label} token omission top-level proof missing")


def run_configured_retention_fixture() -> dict:
    proc: subprocess.Popen[str] | None = None
    with tempfile.TemporaryDirectory(prefix="agentops-deployment-retention-configured-") as tmp:
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
                        "hold_id": "hold_deployment_active",
                        "workspace_id": "local-demo",
                        "scope": "workspace",
                        "status": "active",
                        "reason_code": "customer_dispute",
                        "raw_reason": "Raw legal hold reason must not leave deployment readiness. agtok_deploy_hold sk-deploy-hold",
                        "subject": "Highly confidential subject must be omitted.",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "expires_at": None,
                    },
                    {
                        "hold_id": "hold_deployment_released",
                        "workspace_id": "local-demo",
                        "scope": "task",
                        "status": "released",
                        "reason_code": "matter_closed",
                        "raw_reason": "Raw legal hold reason must not leave deployment readiness. agtok_deploy_released sk-deploy-released",
                        "subject": "Highly confidential subject must be omitted.",
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
        proc = start_configured_server(controls_path, db_path, port, "pro_workspace")
        try:
            wait_ready(base_url, proc)
            before_hash = db_dump_hash(str(db_path))
            status, api_payload = http_json(base_url)
            require(status == 200, f"configured deployment readiness API failed: {status} {api_payload}")
            validate_configured_retention(api_payload, "configured-api")
            proc_cli = run_cli(base_url)
            require(proc_cli.returncode == 0, f"configured deployment readiness CLI failed: {proc_cli.stderr or proc_cli.stdout}")
            cli_payload = json.loads(proc_cli.stdout)
            validate_configured_retention(cli_payload, "configured-cli")
            after_hash = db_dump_hash(str(db_path))
            require(before_hash == after_hash, "configured deployment readiness mutated the SQLite ledger")
            output_text = "\n".join([
                json.dumps(api_payload, ensure_ascii=False, sort_keys=True),
                proc_cli.stdout,
                proc_cli.stderr,
            ])
            require(not leaked_secret(output_text), "configured deployment readiness leaked token-like material")
            require(not any(marker in output_text for marker in RAW_HOLD_MARKERS), "configured deployment readiness leaked raw hold detail")
            return {
                "status": api_payload.get("status"),
                "deployment_ready": api_payload.get("deployment_ready"),
                "retention_status": (api_payload.get("retention") or {}).get("status"),
                "controls_status": (api_payload.get("retention") or {}).get("controls_status"),
                "active_legal_holds": (api_payload.get("retention") or {}).get("active_legal_holds"),
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


def run_configured_enterprise_fixture() -> dict:
    proc: subprocess.Popen[str] | None = None
    with tempfile.TemporaryDirectory(prefix="agentops-deployment-enterprise-configured-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops.db"
        enterprise_controls_path = tmp_path / "enterprise-controls.local.json"
        write_enterprise_controls_fixture(enterprise_controls_path)
        prepare_minimal_sqlite_db(db_path)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        proc = start_configured_server(None, db_path, port, "enterprise_byoc", enterprise_controls_path)
        try:
            wait_ready(base_url, proc)
            before_hash = db_dump_hash(str(db_path))
            status, api_payload = http_json(base_url)
            require(status == 200, f"configured enterprise deployment readiness API failed: {status} {api_payload}")
            validate_configured_enterprise(api_payload, "enterprise-api")
            controls_status, controls_payload = http_json(base_url, "/api/deployment/enterprise-controls")
            require(controls_status == 200, f"configured enterprise controls API failed: {controls_status} {controls_payload}")
            validate_enterprise_controls(controls_payload, "enterprise-controls-api")
            proc_cli = run_cli(base_url)
            require(proc_cli.returncode == 0, f"configured enterprise deployment readiness CLI failed: {proc_cli.stderr or proc_cli.stdout}")
            cli_payload = json.loads(proc_cli.stdout)
            validate_configured_enterprise(cli_payload, "enterprise-cli")
            proc_controls_cli = run_cli_enterprise_controls(base_url)
            require(proc_controls_cli.returncode == 0, f"configured enterprise controls CLI failed: {proc_controls_cli.stderr or proc_controls_cli.stdout}")
            cli_controls_payload = json.loads(proc_controls_cli.stdout)
            validate_enterprise_controls(cli_controls_payload, "enterprise-controls-cli")
            after_hash = db_dump_hash(str(db_path))
            require(before_hash == after_hash, "configured enterprise deployment readiness mutated the SQLite ledger")
            output_text = "\n".join([
                json.dumps(api_payload, ensure_ascii=False, sort_keys=True),
                json.dumps(controls_payload, ensure_ascii=False, sort_keys=True),
                proc_cli.stdout,
                proc_cli.stderr,
                proc_controls_cli.stdout,
                proc_controls_cli.stderr,
            ])
            require(not leaked_secret(output_text), "configured enterprise deployment readiness leaked token-like material")
            require(not any(marker in output_text for marker in RAW_ENTERPRISE_MARKERS), "configured enterprise controls leaked raw enterprise metadata")
            return {
                "status": api_payload.get("status"),
                "deployment_ready": api_payload.get("deployment_ready"),
                "edition": api_payload.get("edition"),
                "sso_connector_gate": next(
                    (gate.get("status") for gate in (api_payload.get("gates") or []) if gate.get("id") == "sso_connector_policy"),
                    None,
                ),
                "signed_export_status": (api_payload.get("signed_audit_export") or {}).get("status"),
                "enterprise_controls_status": controls_payload.get("status"),
                "sso_configured": (controls_payload.get("sso") or {}).get("configured"),
                "private_connector_total": (controls_payload.get("private_connector_policy") or {}).get("total_connectors"),
                "private_connector_active": (controls_payload.get("private_connector_policy") or {}).get("active_connectors"),
                "enterprise_byoc": api_payload.get("enterprise_byoc"),
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
    parser = argparse.ArgumentParser(description="Verify deployment readiness API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL"))
    parser.add_argument("--db-path", default=os.environ.get("AGENTOPS_DB_PATH"), help="Optional SQLite DB path used to assert read-only behavior.")
    parser.add_argument("--configured-retention-fixture", action="store_true", help="Also start an isolated pro_workspace server with configured legal-hold retention controls and verify deployment aggregation.")
    parser.add_argument("--configured-enterprise-fixture", action="store_true", help="Also start an isolated enterprise_byoc server and verify SSO/private connector and signed-export gates through API and CLI.")
    args = parser.parse_args()
    outputs: list[str] = []
    try:
        base_url = args.base_url or (None if (args.configured_retention_fixture or args.configured_enterprise_fixture) else "http://127.0.0.1:8787")
        api_payload: dict = {}
        cli_payload: dict = {}
        read_only_hash_checked = False
        if base_url:
            before_hash = db_dump_hash(args.db_path)
            status, api_payload = http_json(base_url)
            outputs.append(json.dumps(api_payload, ensure_ascii=False, sort_keys=True))
            require(status == 200, f"deployment readiness API failed: {status} {api_payload}")
            validate(api_payload, "api")

            proc = run_cli(base_url)
            outputs.extend([proc.stdout, proc.stderr])
            require(proc.returncode == 0, f"deployment readiness CLI failed: {proc.stderr or proc.stdout}")
            cli_payload = json.loads(proc.stdout)
            validate(cli_payload, "cli")
            after_hash = db_dump_hash(args.db_path)
            if before_hash and after_hash:
                require(before_hash == after_hash, "deployment readiness mutated the SQLite ledger")
                read_only_hash_checked = True

        configured = run_configured_retention_fixture() if args.configured_retention_fixture else None
        enterprise = run_configured_enterprise_fixture() if args.configured_enterprise_fixture else None
        require(not leaked_secret("\n".join(outputs)), "deployment readiness leaked token-like material")
        print(json.dumps({
            "ok": True,
            "api_status": api_payload.get("status"),
            "cli_status": cli_payload.get("status"),
            "gate_count": len(api_payload.get("gates") or []),
            "signed_export_status": (api_payload.get("signed_audit_export") or {}).get("status"),
            "retention_status": (api_payload.get("retention") or {}).get("status"),
            "configured_retention_fixture": configured,
            "configured_enterprise_fixture": enterprise,
            "read_only_hash_checked": read_only_hash_checked
            or bool(configured and configured.get("read_only_hash_checked"))
            or bool(enterprise and enterprise.get("read_only_hash_checked")),
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
