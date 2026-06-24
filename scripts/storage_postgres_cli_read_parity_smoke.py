#!/usr/bin/env python3
"""Run selected AgentOps CLI reads against a Postgres-backed server adapter."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
from agentops_mis_storage.parity_fixture import FIXTURE_VERSION, fixture_operations, snapshot_hash  # noqa: E402
from agentops_mis_storage.postgres import PostgresAdapter, PostgresAdapterUnavailable  # noqa: E402
from storage_postgres_optional_adapter_smoke import BUNDLED_PYTHON, ensure_psycopg, mapped_port, wait_for_adapter_connect  # noqa: E402
from storage_postgres_route_read_model_smoke import JOB_A, RUN_A, TASK_A, TASK_B, WORKSPACE_A  # noqa: E402


CONTRACT_ID = "postgres_cli_read_parity_v1"
VOLATILE_SNAPSHOT_KEYS = {"age_sec"}
AGENT_A = "agt_parity_a"
AGENT_B = "agt_parity_b"
PLAN_A = "plan_cli_parity_a"
PLAN_B = "plan_cli_parity_b"
MANIFEST_A = "pem_cli_parity_a"
MANIFEST_B = "pem_cli_parity_b"
TOOL_CALL_A = "tc_cli_parity_plan_a"


CLI_READS: list[tuple[str, list[str]]] = [
    ("task_list", ["task", "list", "--limit", "10"]),
    ("task_get", ["task", "get", "--task-id", TASK_A]),
    ("run_list", ["run", "list", "--limit", "10"]),
    ("run_get", ["run", "get", "--run-id", RUN_A]),
    ("run_graph", ["run", "graph", "--run-id", RUN_A]),
    ("artifact_list", ["artifact", "list", "--limit", "10"]),
    ("approval_list", ["approval", "list", "--limit", "10"]),
    ("memory_list", ["memory", "list", "--limit", "10"]),
    ("workflow_job_status", ["workflow", "job-status", "--job-id", JOB_A]),
    ("workflow_stuck_jobs", ["workflow", "stuck-jobs", "--threshold-sec", "1", "--limit", "10"]),
    ("agent_plan_list", ["agent-plan", "list", "--task-id", TASK_A, "--limit", "10"]),
    ("agent_plan_get", ["agent-plan", "get", "--plan-id", PLAN_A]),
    ("agent_plan_verify", ["agent-plan", "verify", "--plan-id", PLAN_A]),
    ("plan_evidence_list", ["plan-evidence", "list", "--run-id", RUN_A, "--limit", "10"]),
    ("plan_evidence_get", ["plan-evidence", "get", "--manifest-id", MANIFEST_A]),
    ("plan_evidence_verify", ["plan-evidence", "verify", "--manifest-id", MANIFEST_A]),
]


def dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def reexec_self_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_CLI_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists():
        return
    if Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_CLI_PG_REEXEC"] = "1"
        os.execv(str(BUNDLED_PYTHON), [str(BUNDLED_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


def unavailable(message: str, *, skip: bool) -> int:
    payload = {
        "ok": bool(skip),
        "skipped": bool(skip),
        "contract": CONTRACT_ID,
        "reason": message,
        "next_action": "Run again with Docker and optional psycopg available; skipped mode is diagnostic only.",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if skip else 1


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def redact(value: str, secret: str) -> str:
    return value.replace(secret, "[REDACTED]") if value else value


def request_json(url: str, *, method: str = "GET", body: dict | None = None) -> tuple[int, dict]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=data, method=method, headers=headers)
    try:
        with urlopen(req, timeout=5) as res:
            return int(res.status), json.loads(res.read().decode("utf-8"))
    except HTTPError as exc:
        return int(exc.code), json.loads(exc.read().decode("utf-8"))


def wait_json(url: str, proc: subprocess.Popen[str], *, secret: str, timeout_sec: int = 30) -> tuple[int, dict]:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if proc.poll() is not None:
            out, err = proc.communicate(timeout=1)
            detail = f"server exited early rc={proc.returncode} stdout={out} stderr={err}"
            raise RuntimeError(redact(detail, secret))
        try:
            return request_json(url)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(0.25)
    raise RuntimeError(redact(f"server did not return JSON before timeout: {last_error}", secret))


def start_server(env: dict[str, str], port: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, "server.py", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def run_cli(args: list[str], env: dict[str, str], *, secret: str, expect_ok: bool = True) -> tuple[int, dict | None, str]:
    result = subprocess.run(
        [sys.executable, "-m", "agentops_mis_cli", *args],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    stdout = redact(result.stdout, secret)
    stderr = redact(result.stderr, secret)
    if expect_ok and result.returncode != 0:
        raise RuntimeError(f"CLI failed: args={args} rc={result.returncode} stdout={stdout} stderr={stderr}")
    if not expect_ok and result.returncode == 0:
        raise RuntimeError(f"CLI unexpectedly succeeded: args={args} stdout={stdout}")
    payload = None
    if stdout.strip():
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"CLI returned non-JSON: args={args} stdout={stdout} stderr={stderr}") from exc
    return result.returncode, payload, stderr


def seed_cli_plan_evidence_rows(adapter: PostgresAdapter) -> None:
    now = "2026-06-22T03:02:00+00:00"
    later = "2026-06-22T03:03:00+00:00"
    adapter.execute(
        """INSERT INTO tool_calls(tool_call_id,run_id,agent_id,tool_name,tool_version,tool_category,normalized_args_json,target_resource,risk_level,status,result_summary,side_effect_id,started_at,ended_at,created_at)
        VALUES(:tool_call_id,:run_id,:agent_id,:tool_name,:tool_version,:tool_category,:normalized_args_json,:target_resource,:risk_level,:status,:result_summary,:side_effect_id,:started_at,:ended_at,:created_at)""",
        {
            "tool_call_id": TOOL_CALL_A,
            "run_id": RUN_A,
            "agent_id": AGENT_A,
            "tool_name": "cli_parity_plan_tool",
            "tool_version": "v1",
            "tool_category": "database",
            "normalized_args_json": dumps({"workspace_id": WORKSPACE_A}),
            "target_resource": "postgres://cli-parity",
            "risk_level": "low",
            "status": "completed",
            "result_summary": "Completed tool evidence for CLI plan parity.",
            "side_effect_id": None,
            "started_at": now,
            "ended_at": later,
            "created_at": now,
        },
    )
    for plan_id, workspace_id, task_id, run_id, agent_id in [
        (PLAN_A, WORKSPACE_A, TASK_A, RUN_A, AGENT_A),
        (PLAN_B, "ws_parity_b", TASK_B, "run_parity_b", AGENT_B),
    ]:
        adapter.execute(
            """INSERT INTO agent_plans(plan_id,workspace_id,task_id,run_id,agent_id,task_understanding,referenced_specs_json,referenced_memories_json,referenced_bases_json,proposed_files_to_change_json,risk_level,approval_required,execution_steps_json,verification_plan,rollback_plan,status,created_at,updated_at)
            VALUES(:plan_id,:workspace_id,:task_id,:run_id,:agent_id,:task_understanding,:referenced_specs_json,:referenced_memories_json,:referenced_bases_json,:proposed_files_to_change_json,:risk_level,:approval_required,:execution_steps_json,:verification_plan,:rollback_plan,:status,:created_at,:updated_at)""",
            {
                "plan_id": plan_id,
                "workspace_id": workspace_id,
                "task_id": task_id,
                "run_id": run_id,
                "agent_id": agent_id,
                "task_understanding": "Prove Postgres-backed Agent Gateway CLI plan reads.",
                "referenced_specs_json": dumps(["docs/AGENT_GATEWAY_CLI_SPEC.md", "docs/POSTGRES_PARITY_CONTRACT.md"]),
                "referenced_memories_json": dumps(["mem_parity_a"]),
                "referenced_bases_json": dumps(["base_local_tasks"]),
                "proposed_files_to_change_json": dumps(["scripts/storage_postgres_cli_read_parity_smoke.py"]),
                "risk_level": "low",
                "approval_required": 0,
                "execution_steps_json": dumps(["read", "verify", "record"]),
                "verification_plan": "Run Postgres CLI read parity smoke.",
                "rollback_plan": "Drop temporary Postgres container.",
                "status": "submitted",
                "created_at": now,
                "updated_at": later,
            },
        )
    for manifest_id, plan_id, workspace_id, task_id, run_id, agent_id, status in [
        (MANIFEST_A, PLAN_A, WORKSPACE_A, TASK_A, RUN_A, AGENT_A, "verified"),
        (MANIFEST_B, PLAN_B, "ws_parity_b", TASK_B, "run_parity_b", AGENT_B, "blocked"),
    ]:
        adapter.execute(
            """INSERT INTO plan_evidence_manifests(manifest_id,workspace_id,plan_id,task_id,run_id,agent_id,mismatch_policy,expected_steps_json,tool_call_ids_json,evaluation_ids_json,artifact_ids_json,audit_ids_json,status,verification_json,created_at,updated_at)
            VALUES(:manifest_id,:workspace_id,:plan_id,:task_id,:run_id,:agent_id,:mismatch_policy,:expected_steps_json,:tool_call_ids_json,:evaluation_ids_json,:artifact_ids_json,:audit_ids_json,:status,:verification_json,:created_at,:updated_at)""",
            {
                "manifest_id": manifest_id,
                "workspace_id": workspace_id,
                "plan_id": plan_id,
                "task_id": task_id,
                "run_id": run_id,
                "agent_id": agent_id,
                "mismatch_policy": "block",
                "expected_steps_json": dumps(["read", "verify", "record"]),
                "tool_call_ids_json": dumps([TOOL_CALL_A]) if manifest_id == MANIFEST_A else "[]",
                "evaluation_ids_json": dumps(["eval_parity_a"]) if manifest_id == MANIFEST_A else "[]",
                "artifact_ids_json": dumps(["art_parity_a"]) if manifest_id == MANIFEST_A else "[]",
                "audit_ids_json": "[]",
                "status": status,
                "verification_json": dumps({"cli_parity": manifest_id == MANIFEST_A}),
                "created_at": now,
                "updated_at": later,
            },
        )


def canonical_numeric_payload(value):
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, dict):
        return {
            key: canonical_numeric_payload(item)
            for key, item in value.items()
            if key not in VOLATILE_SNAPSHOT_KEYS
        }
    if isinstance(value, list):
        return [canonical_numeric_payload(item) for item in value]
    return value


def token_like_leaked(payloads: dict, stderr_values: list[str]) -> bool:
    haystack = json.dumps(payloads, ensure_ascii=False, sort_keys=True) + "\n" + "\n".join(stderr_values)
    forbidden = ["agtok_", "agtsess_", "sk-", "ntn_", "BEGIN PRIVATE KEY", "BEGIN OPENSSH PRIVATE KEY"]
    return any(marker in haystack for marker in forbidden)


def ids(rows: list[dict], key: str) -> set[str]:
    return {str(row.get(key)) for row in rows if row.get(key)}


def assert_cli_payloads(payloads: dict) -> list[str]:
    failures: list[str] = []

    task_rows = payloads["task_list"].get("tasks") or []
    if TASK_A not in ids(task_rows, "task_id"):
        failures.append("task_list_missing_workspace_task")
    if TASK_B in ids(task_rows, "task_id"):
        failures.append("task_list_leaked_other_workspace_task")
    task_get = payloads["task_get"]
    if (task_get.get("task") or {}).get("task_id") != TASK_A:
        failures.append("task_get_task_id_mismatch")
    if task_get.get("evidence", {}).get("runs") != 1:
        failures.append("task_get_run_evidence_count_mismatch")

    run_rows = payloads["run_list"].get("runs") or []
    if RUN_A not in ids(run_rows, "run_id"):
        failures.append("run_list_missing_workspace_run")
    if "run_parity_b" in ids(run_rows, "run_id"):
        failures.append("run_list_leaked_other_workspace_run")
    run_get = payloads["run_get"]
    if (run_get.get("run") or {}).get("run_id") != RUN_A:
        failures.append("run_get_run_id_mismatch")
    if run_get.get("evidence", {}).get("tool_calls") != 2:
        failures.append("run_get_tool_call_count_mismatch")
    run_tool_calls = run_get.get("tool_calls") or []
    if TOOL_CALL_A not in ids(run_tool_calls, "tool_call_id"):
        failures.append("run_get_missing_cli_plan_tool_call")
    if (payloads["run_graph"].get("run") or {}).get("run_id") != RUN_A:
        failures.append("run_graph_run_id_mismatch")

    artifact_rows = payloads["artifact_list"].get("artifacts") or []
    if "art_parity_a" not in ids(artifact_rows, "artifact_id"):
        failures.append("artifact_list_missing_artifact")
    approval_rows = payloads["approval_list"].get("approvals") or []
    if "ap_parity_a" not in ids(approval_rows, "approval_id"):
        failures.append("approval_list_missing_approval")
    memory_rows = payloads["memory_list"].get("memories") or []
    if "mem_parity_a" not in ids(memory_rows, "memory_id"):
        failures.append("memory_list_missing_memory")

    job = payloads["workflow_job_status"].get("job") or {}
    if job.get("job_id") != JOB_A:
        failures.append("workflow_job_status_job_id_mismatch")
    stuck_jobs = payloads["workflow_stuck_jobs"].get("stuck_jobs") or []
    if stuck_jobs and JOB_A not in ids(stuck_jobs, "job_id"):
        failures.append("workflow_stuck_jobs_unexpected_rows")

    agent_plan_rows = payloads["agent_plan_list"].get("agent_plans") or []
    if PLAN_A not in ids(agent_plan_rows, "plan_id"):
        failures.append("agent_plan_list_missing_plan")
    if PLAN_B in ids(agent_plan_rows, "plan_id"):
        failures.append("agent_plan_list_leaked_other_workspace_plan")
    agent_plan = payloads["agent_plan_get"].get("agent_plan") or {}
    if agent_plan.get("plan_id") != PLAN_A or agent_plan.get("run_id") != RUN_A:
        failures.append("agent_plan_get_plan_mismatch")
    plan_verification = payloads["agent_plan_verify"].get("verification") or {}
    if plan_verification.get("pass") is not True:
        failures.append("agent_plan_verify_did_not_pass")

    manifest_rows = payloads["plan_evidence_list"].get("manifests") or []
    if MANIFEST_A not in ids(manifest_rows, "manifest_id"):
        failures.append("plan_evidence_list_missing_manifest")
    if MANIFEST_B in ids(manifest_rows, "manifest_id"):
        failures.append("plan_evidence_list_leaked_other_workspace_manifest")
    manifest = payloads["plan_evidence_get"].get("manifest") or {}
    if manifest.get("manifest_id") != MANIFEST_A or manifest.get("plan_id") != PLAN_A:
        failures.append("plan_evidence_get_manifest_mismatch")
    evidence_verification = payloads["plan_evidence_verify"].get("verification") or {}
    if evidence_verification.get("pass") is not True or evidence_verification.get("status") != "verified":
        failures.append("plan_evidence_verify_did_not_pass")
    if (evidence_verification.get("evidence_counts") or {}).get("tool_calls", 0) < 1:
        failures.append("plan_evidence_verify_missing_tool_evidence")

    for name, payload in payloads.items():
        if isinstance(payload, dict) and payload.get("token_omitted") is False:
            failures.append(f"{name}_token_omitted_false")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Postgres-backed server CLI read parity smoke.")
    parser.add_argument("--image", default=container_smoke.DEFAULT_IMAGE, help="Postgres Docker image to use.")
    parser.add_argument("--skip-if-unavailable", action="store_true", help="Return success with skipped=true when Docker or psycopg is unavailable.")
    parser.add_argument("--no-install-driver", action="store_true", help="Do not install psycopg into a temporary target when missing.")
    args = parser.parse_args()

    reexec_self_with_bundled_python_if_needed()

    early = container_smoke.docker_available(args.skip_if_unavailable)
    if early is not None:
        return early
    early = container_smoke.ensure_image(args.image, args.skip_if_unavailable)
    if early is not None:
        return early

    with tempfile.TemporaryDirectory(prefix="agentops-cli-pg-") as temp_dir:
        temp_root = Path(temp_dir)
        driver_ok, driver_status = ensure_psycopg(temp_root, install=not args.no_install_driver)
        if not driver_ok:
            return unavailable(f"Optional psycopg driver unavailable: {driver_status}", skip=args.skip_if_unavailable)

        pythonpath_parts = [str(ROOT)]
        package_target = temp_root / "python-packages"
        if package_target.exists():
            pythonpath_parts.insert(0, str(package_target))
        if os.environ.get("PYTHONPATH"):
            pythonpath_parts.append(os.environ["PYTHONPATH"])

        container = f"agentops-pg-cli-read-{container_smoke.secrets.token_hex(6)}"
        pg_auth = container_smoke.secrets.token_urlsafe(18)
        started = container_smoke.run(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                container,
                "-p",
                "127.0.0.1::5432",
                "-e",
                "POSTGRES_USER=agentops",
                "-e",
                "POSTGRES_DB=agentops",
                "-e",
                f"POSTGRES_PASSWORD={pg_auth}",
                args.image,
            ],
            timeout=60,
        )
        if started.returncode != 0:
            return unavailable(redact((started.stderr or started.stdout or "docker run failed").strip(), pg_auth), skip=args.skip_if_unavailable)

        adapter: PostgresAdapter | None = None
        proc: subprocess.Popen[str] | None = None
        try:
            if not container_smoke.wait_for_postgres(container):
                return unavailable("Postgres container did not become ready before timeout.", skip=args.skip_if_unavailable)
            port = mapped_port(container)
            dsn = f"postgresql://agentops:{pg_auth}@127.0.0.1:{port}/agentops"
            adapter = wait_for_adapter_connect(dsn)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            for operation in fixture_operations():
                adapter.execute(operation.sql, operation.params)
            seed_cli_plan_evidence_rows(adapter)
            adapter.commit()
            adapter.close()
            adapter = None

            http_port = free_port()
            server_env = os.environ.copy()
            server_env.update(
                {
                    "AGENTOPS_STORAGE_BACKEND": "postgres",
                    "AGENTOPS_EDITION": "enterprise_byoc",
                    "AGENTOPS_POSTGRES_DSN": dsn,
                    "AGENTOPS_ENABLE_POSTGRES_STORAGE": "1",
                    "AGENTOPS_POSTGRES_READ_ONLY_HTTP": "1",
                    "PYTHONPATH": os.pathsep.join(pythonpath_parts),
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            server_env.pop("AGENTOPS_DB_PATH", None)
            proc = start_server(server_env, http_port)
            base_url = f"http://127.0.0.1:{http_port}"
            status_code, backend_status = wait_json(f"{base_url}/api/storage/backend-status", proc, secret=pg_auth)

            failures: list[str] = []
            if status_code != 200:
                failures.append(f"backend_status_http_{status_code}")
            if backend_status.get("active_backend") != "postgres" or backend_status.get("mode") != "read_only_http":
                failures.append(f"postgres_backend_status_mismatch:{backend_status}")
            if backend_status.get("fallback_performed") is not False:
                failures.append("postgres_backend_fallback_flag_not_false")

            cli_env = os.environ.copy()
            cli_env.update(
                {
                    "PYTHONPATH": str(ROOT),
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "AGENTOPS_BASE_URL": base_url,
                    "AGENTOPS_WORKSPACE_ID": WORKSPACE_A,
                    "AGENTOPS_CONFIG": str(temp_root / "agentops-cli-config.json"),
                    "AGENTOPS_REQUEST_TIMEOUT": "10",
                }
            )
            for key in ["AGENTOPS_API_KEY", "AGENTOPS_AGENT_ID"]:
                cli_env.pop(key, None)

            payloads: dict[str, dict] = {}
            stderr_values: list[str] = []
            for name, cli_args in CLI_READS:
                _rc, payload, stderr = run_cli(cli_args, cli_env, secret=pg_auth)
                payloads[name] = server.json_safe(payload or {})
                stderr_values.append(stderr)

            failures.extend(assert_cli_payloads(payloads))

            _write_rc, _write_payload, write_stderr = run_cli(
                [
                    "task",
                    "create",
                    "--task-id",
                    "tsk_cli_postgres_write_should_block",
                    "--title",
                    "Should not write",
                    "--description",
                    "Postgres read-only CLI smoke write guard.",
                    "--owner-agent-id",
                    "agt_parity_a",
                ],
                cli_env,
                secret=pg_auth,
                expect_ok=False,
            )
            stderr_values.append(write_stderr)
            if "postgres_read_only_backend" not in write_stderr:
                failures.append("cli_write_block_missing_reason")

            adapter = wait_for_adapter_connect(dsn)
            leaked_write = adapter.fetchone("SELECT task_id FROM tasks WHERE task_id=?", ["tsk_cli_postgres_write_should_block"])
            if leaked_write:
                failures.append("cli_read_only_write_created_task")
            if token_like_leaked(payloads, stderr_values):
                failures.append("token_like_material_leaked")

            payload_hash = snapshot_hash(canonical_numeric_payload(payloads))
            output = {
                "ok": not failures,
                "skipped": False,
                "contract": CONTRACT_ID,
                "fixture_version": FIXTURE_VERSION,
                "image": args.image,
                "driver_status": driver_status,
                "backend_mode": backend_status.get("mode"),
                "cli_command_count": len(CLI_READS),
                "cli_read_command_count": len(CLI_READS),
                "cli_write_block_command_count": 1,
                "cli_commands": [name for name, _args in CLI_READS],
                "cli_read_model_hash": payload_hash,
                "postgres_cli_read_snapshot_hash": payload_hash,
                "volatile_snapshot_fields_omitted": sorted(VOLATILE_SNAPSHOT_KEYS),
                "write_block_checked": True,
                "fallback_performed": False,
                "free_local_dependencies": [],
                "token_omitted": True,
                "failures": failures,
                "next_proof": "Prove Postgres write helpers before enabling write routes.",
            }
            if failures:
                output["payloads"] = payloads
                output["write_stderr"] = write_stderr
            print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
            return 0 if not failures else 1
        except (AssertionError, PostgresAdapterUnavailable, RuntimeError, ValueError, KeyError) as exc:
            if adapter is not None:
                adapter.rollback()
            return unavailable(redact(str(exc), pg_auth), skip=args.skip_if_unavailable)
        finally:
            if proc is not None:
                proc.terminate()
                try:
                    proc.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.communicate(timeout=5)
            if adapter is not None:
                adapter.close()
            container_smoke.run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
