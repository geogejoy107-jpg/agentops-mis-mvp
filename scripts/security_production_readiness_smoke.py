#!/usr/bin/env python3
"""Smoke-test read-only production security readiness API and CLI."""
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
SECRET_MARKERS = ["Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_", "AGENTOPS_API_KEY="]
RAW_PRODUCTION_MARKERS = ["prod-api-key-fixture", "prod-admin-key-fixture"]


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


def prepare_minimal_sqlite_db(path: Path) -> None:
    sys.path.insert(0, str(ROOT))
    import server  # noqa: PLC0415

    with sqlite3.connect(path) as conn:
        conn.executescript(server.SCHEMA_SQL)
        conn.commit()


def validate_workspace_admin_key_config_contract() -> None:
    sys.path.insert(0, str(ROOT))
    import server  # noqa: PLC0415

    env_name = "AGENTOPS_WORKSPACE_ADMIN_KEYS_JSON"
    original = os.environ.get(env_name)
    original_deployment_mode = os.environ.get("AGENTOPS_DEPLOYMENT_MODE")
    original_global_admin_key = os.environ.get("AGENTOPS_ADMIN_KEY")
    shared_key = "workspace-admin-shared-fixture-key"
    fixtures = [
        {},
        {"workspace-a": shared_key, "workspace-b": shared_key},
        {"workspace-a": "short"},
        {"workspace-a": {"not": "a string"}},
        {"workspace a": "workspace-admin-a-fixture-key", "workspace_a": "workspace-admin-b-fixture-key"},
    ]
    try:
        for fixture in fixtures:
            os.environ[env_name] = json.dumps(fixture, sort_keys=True)
            keys, error = server.configured_workspace_admin_keys()
            require(not keys and bool(error), f"invalid workspace admin key map passed: {fixture.keys()}")
        os.environ[env_name] = json.dumps({
            "workspace-a": "workspace-admin-a-valid-fixture-key",
            "workspace-b": "workspace-admin-b-valid-fixture-key",
        }, sort_keys=True)
        keys, error = server.configured_workspace_admin_keys()
        require(error is None and set(keys) == {"workspace-a", "workspace-b"}, "valid workspace admin key map failed")

        os.environ.pop(env_name, None)
        os.environ["AGENTOPS_DEPLOYMENT_MODE"] = "production"
        os.environ["AGENTOPS_ADMIN_KEY"] = "global-admin-local-compatibility-key"
        context, auth_error = server.agent_gateway_admin_auth_context(
            {"X-AgentOps-Admin-Key": "global-admin-local-compatibility-key"},
            "workspace-a",
        )
        require(context is None and (auth_error or {}).get("error") == "unauthorized", "production global-only admin key did not fail closed")
    finally:
        if original is None:
            os.environ.pop(env_name, None)
        else:
            os.environ[env_name] = original
        if original_deployment_mode is None:
            os.environ.pop("AGENTOPS_DEPLOYMENT_MODE", None)
        else:
            os.environ["AGENTOPS_DEPLOYMENT_MODE"] = original_deployment_mode
        if original_global_admin_key is None:
            os.environ.pop("AGENTOPS_ADMIN_KEY", None)
        else:
            os.environ["AGENTOPS_ADMIN_KEY"] = original_global_admin_key


def http_json(base_url: str, headers: dict[str, str] | None = None, path: str = "/api/security/production-readiness") -> tuple[int, dict]:
    req = urllib.request.Request(base_url.rstrip("/") + path, headers={"Accept": "application/json", **(headers or {})}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except Exception:
            body = {"error": exc.reason}
        return exc.code, body


def run_cli(base_url: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(CLI), "--base-url", base_url, "security", "production-readiness"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=45,
        check=False,
    )


def start_configured_production_server(db_path: Path, port: int, api_key: str, admin_key: str) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["AGENTOPS_DB_PATH"] = str(db_path)
    env["AGENTOPS_DEPLOYMENT_MODE"] = "production"
    env["AGENTOPS_API_KEY"] = api_key
    env.pop("AGENTOPS_ADMIN_KEY", None)
    env["AGENTOPS_WORKSPACE_ADMIN_KEYS_JSON"] = json.dumps({"local-demo": admin_key}, sort_keys=True)
    env.pop("AGENTOPS_REQUIRE_PRODUCTION_SECURITY", None)
    return subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def wait_ready(base_url: str, proc: subprocess.Popen[str], timeout_sec: int = 25) -> None:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate(timeout=1)
            raise RuntimeError(f"server exited early: rc={proc.returncode} stdout={out} stderr={err}")
        try:
            status, payload = http_json(base_url)
            if status == 200 and payload.get("provider") == "agentops-security":
                return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise RuntimeError(f"server did not become ready: {last_error}")


def validate(payload: dict, label: str) -> None:
    require(payload.get("provider") == "agentops-security", f"{label} wrong provider: {payload}")
    require(payload.get("operation") == "production_readiness", f"{label} wrong operation: {payload}")
    require(payload.get("status") in {"ready", "attention", "blocked"}, f"{label} bad status: {payload.get('status')}")
    require(payload.get("token_omitted") is True, f"{label} token omission proof missing")
    require(payload.get("live_execution_performed") is False, f"{label} must not execute live work")
    gates = payload.get("gates") or []
    gate_ids = {gate.get("id") for gate in gates if isinstance(gate, dict)}
    for gate_id in {"agent_gateway_auth", "admin_key", "workspace_admin_scope", "scoped_agent_tokens", "local_dev_boundary"}:
        require(gate_id in gate_ids, f"{label} missing gate {gate_id}: {payload}")
    require(isinstance(payload.get("next_actions"), list) and payload.get("next_actions"), f"{label} next_actions missing")
    safety = payload.get("safety") or {}
    require(safety.get("read_only") is True, f"{label} safety.read_only missing")
    require(safety.get("token_omitted") is True, f"{label} safety.token_omitted missing")
    require(safety.get("raw_prompt_omitted") is True, f"{label} safety.raw_prompt_omitted missing")
    require("local_dev_no_token" in (payload.get("contract") or ""), f"{label} contract should name local_dev_no_token boundary")


def validate_configured_blocked(payload: dict, label: str) -> None:
    validate(payload, label)
    require(payload.get("production_requested") is True, f"{label} should be production requested: {payload}")
    require(payload.get("status") == "blocked", f"{label} should block without API key: {payload}")
    require(payload.get("production_ready") is False, f"{label} production_ready should be false: {payload}")
    require(payload.get("auth_mode") == "unauthorized", f"{label} auth mode should be unauthorized: {payload}")


def validate_configured_ready(payload: dict, label: str) -> None:
    validate(payload, label)
    require(payload.get("production_requested") is True, f"{label} should be production requested: {payload}")
    require(payload.get("status") == "ready", f"{label} should be ready with API/admin keys: {payload}")
    require(payload.get("production_ready") is True, f"{label} production_ready should be true: {payload}")
    require(payload.get("auth_mode") == "global_api_key", f"{label} auth mode should use global API key: {payload}")
    gates = {
        gate.get("id"): gate
        for gate in (payload.get("gates") or [])
        if isinstance(gate, dict) and gate.get("id")
    }
    for gate_id in {"agent_gateway_auth", "admin_key", "workspace_admin_scope", "scoped_agent_tokens", "local_dev_boundary"}:
        gate = gates.get(gate_id) or {}
        require(gate.get("status") == "pass", f"{label} gate {gate_id} should pass: {gates}")
        require(gate.get("ok") is True, f"{label} gate {gate_id} should be ok: {gates}")
    require(payload.get("gateway_status_code") == 200, f"{label} gateway status should be 200: {payload}")


def run_configured_production_fixture() -> dict:
    proc: subprocess.Popen[str] | None = None
    api_key = "prod-api-key-fixture-local-only"
    admin_key = "prod-admin-key-fixture-local-only"
    with tempfile.TemporaryDirectory(prefix="agentops-security-production-configured-") as tmp:
        tmp_path = Path(tmp)
        db_path = tmp_path / "agentops.db"
        prepare_minimal_sqlite_db(db_path)
        port = free_port()
        base_url = f"http://127.0.0.1:{port}"
        proc = start_configured_production_server(db_path, port, api_key, admin_key)
        try:
            wait_ready(base_url, proc)
            before_hash = db_dump_hash(str(db_path))
            status_blocked, payload_blocked = http_json(base_url)
            validate_configured_blocked(payload_blocked, "configured-production-no-auth")
            require(status_blocked == 200, f"configured no-auth readiness failed: {status_blocked} {payload_blocked}")

            auth_headers = {
                "Authorization": f"Bearer {api_key}",
                "X-AgentOps-Api-Key": api_key,
            }
            status_ready, payload_ready = http_json(base_url, auth_headers)
            require(status_ready == 200, f"configured authenticated readiness failed: {status_ready} {payload_ready}")
            validate_configured_ready(payload_ready, "configured-production-api")

            with tempfile.TemporaryDirectory(prefix="agentops-security-production-cli-") as cli_tmp:
                env = os.environ.copy()
                env["AGENTOPS_CONFIG"] = str(Path(cli_tmp) / "config.json")
                env["AGENTOPS_API_KEY"] = api_key
                proc_cli = run_cli(base_url, env)
            require(proc_cli.returncode == 0, f"configured production CLI failed: {proc_cli.stderr or proc_cli.stdout}")
            cli_payload = json.loads(proc_cli.stdout)
            validate_configured_ready(cli_payload, "configured-production-cli")

            admin_status, admin_payload = http_json(
                base_url,
                {"X-AgentOps-Admin-Key": admin_key, "X-AgentOps-Workspace-Id": "local-demo"},
                "/api/agent-gateway/enrollments?workspace_id=local-demo",
            )
            require(admin_status == 200, f"configured admin-key enrollment list failed: {admin_status} {admin_payload}")
            require(admin_payload.get("token_omitted") is True, f"configured admin list should omit tokens: {admin_payload}")
            require(isinstance(admin_payload.get("valid_scopes"), list) and admin_payload.get("valid_scopes"), f"configured admin list should expose valid scopes: {admin_payload}")

            after_hash = db_dump_hash(str(db_path))
            require(before_hash == after_hash, "configured production readiness mutated the SQLite ledger")
            output_text = "\n".join([
                json.dumps(payload_blocked, ensure_ascii=False, sort_keys=True),
                json.dumps(payload_ready, ensure_ascii=False, sort_keys=True),
                proc_cli.stdout,
                proc_cli.stderr,
                json.dumps(admin_payload, ensure_ascii=False, sort_keys=True),
            ])
            require(not leaked_secret(output_text), "configured production readiness leaked token-like material")
            require(not any(marker in output_text for marker in RAW_PRODUCTION_MARKERS), "configured production readiness leaked raw configured keys")
            return {
                "no_auth_status": payload_blocked.get("status"),
                "ready_status": payload_ready.get("status"),
                "auth_mode": payload_ready.get("auth_mode"),
                "admin_key_list_status": admin_status,
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
    parser = argparse.ArgumentParser(description="Verify production security readiness API and CLI.")
    parser.add_argument("--base-url", default=os.environ.get("AGENTOPS_BASE_URL", "http://127.0.0.1:8787"))
    parser.add_argument("--configured-production-fixture", action="store_true", help="Also start an isolated production-mode server with API/admin keys and verify blocked/ready transitions.")
    args = parser.parse_args()
    outputs: list[str] = []
    try:
        validate_workspace_admin_key_config_contract()
        base_url = args.base_url if not args.configured_production_fixture else (os.environ.get("AGENTOPS_BASE_URL") or "")
        payload: dict = {}
        if base_url:
            status, payload = http_json(base_url)
            raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
            outputs.append(raw)
            require(status == 200, f"security readiness API failed: {status} {payload}")
            validate(payload, "api")

            with tempfile.TemporaryDirectory(prefix="agentops-security-readiness-") as tmp:
                env = os.environ.copy()
                env["AGENTOPS_CONFIG"] = str(Path(tmp) / "config.json")
                env.pop("AGENTOPS_API_KEY", None)
                proc = run_cli(base_url, env)
                outputs.extend([proc.stdout, proc.stderr])
                require(proc.returncode == 0, f"security readiness CLI failed: {proc.stderr or proc.stdout}")
                cli_payload = json.loads(proc.stdout)
                validate(cli_payload, "cli")

        configured = run_configured_production_fixture() if args.configured_production_fixture else None
        require(not leaked_secret("\n".join(outputs)), "security readiness leaked token-like material")
        print(json.dumps({
            "ok": True,
            "status": payload.get("status"),
            "auth_mode": payload.get("auth_mode"),
            "production_ready": payload.get("production_ready"),
            "production_requested": payload.get("production_requested"),
            "configured_production_fixture": configured,
            "gate_count": len(payload.get("gates") or []),
            "secret_leaked": False,
            "workspace_admin_config_validation_checked": True,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
