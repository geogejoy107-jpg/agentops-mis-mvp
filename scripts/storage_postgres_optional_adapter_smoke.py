#!/usr/bin/env python3
"""Exercise the optional psycopg Postgres adapter against a real container."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import server  # noqa: E402
import storage_postgres_container_smoke as container_smoke  # noqa: E402
import storage_postgres_contract_smoke as contract  # noqa: E402
from agentops_mis_storage.postgres import PostgresAdapter, PostgresAdapterUnavailable  # noqa: E402


BUNDLED_PYTHON = Path("/Users/wuji/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3")
PSYCOPG_INSTALL_SPEC = os.environ.get("AGENTOPS_PSYCOPG_INSTALL_SPEC", "psycopg[binary]==3.3.4")


def run(args: list[str], *, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def reexec_with_bundled_python_if_needed() -> None:
    if os.environ.get("AGENTOPS_OPTIONAL_PG_REEXEC") == "1":
        return
    if not BUNDLED_PYTHON.exists():
        return
    if Path(sys.executable).resolve() == BUNDLED_PYTHON.resolve():
        return
    try:
        import psycopg  # noqa: F401
        return
    except ModuleNotFoundError:
        os.environ["AGENTOPS_OPTIONAL_PG_REEXEC"] = "1"
        os.execv(str(BUNDLED_PYTHON), [str(BUNDLED_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]])


def ensure_psycopg(temp_root: Path, *, install: bool) -> tuple[bool, str]:
    try:
        import psycopg  # noqa: F401
        return True, "already_available"
    except ModuleNotFoundError:
        if not install:
            return False, "missing"
    target = temp_root / "python-packages"
    target.mkdir(parents=True, exist_ok=True)
    result = run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--disable-pip-version-check",
            "--quiet",
            "--target",
            str(target),
            PSYCOPG_INSTALL_SPEC,
        ],
        timeout=240,
    )
    if result.returncode != 0:
        return False, (result.stderr or result.stdout or "pip install failed").strip()
    sys.path.insert(0, str(target))
    try:
        import psycopg  # noqa: F401
    except ModuleNotFoundError as exc:
        return False, f"installed psycopg target was not importable: {exc}"
    return True, "installed_temp_target"


def unavailable(message: str, *, skip: bool) -> int:
    payload = {
        "ok": bool(skip),
        "skipped": bool(skip),
        "contract": "postgres_optional_psycopg_adapter_v1",
        "reason": message,
        "next_action": "Install optional psycopg support and rerun against a reachable Postgres container.",
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if skip else 1


def mapped_port(container: str) -> str:
    result = run(["docker", "port", container, "5432/tcp"], timeout=30)
    if result.returncode != 0:
        raise RuntimeError((result.stderr or result.stdout).strip())
    raw = result.stdout.strip().splitlines()[0]
    return raw.rsplit(":", 1)[1]


def wait_for_adapter_connect(dsn: str, *, timeout_sec: int = 45) -> PostgresAdapter:
    deadline = time.time() + timeout_sec
    last_error = ""
    while time.time() < deadline:
        try:
            return PostgresAdapter.connect(dsn)
        except PostgresAdapterUnavailable:
            raise
        except Exception as exc:
            last_error = str(exc)
            time.sleep(1)
    raise RuntimeError(f"Postgres adapter connection did not become ready before timeout: {last_error}")


def insert_sql() -> dict[str, str]:
    return {
        "user": """
            INSERT INTO users(user_id,name,email,role,created_at)
            VALUES(:user_id,:name,:email,:role,:created_at)
        """,
        "agent": """
            INSERT INTO agents(agent_id,name,role,description,runtime_type,model_provider,model_name,status,permission_level,allowed_tools,budget_limit_usd,owner_user_id,created_at,updated_at)
            VALUES(:agent_id,:name,:role,:description,:runtime_type,:model_provider,:model_name,:status,:permission_level,:allowed_tools,:budget_limit_usd,:owner_user_id,:created_at,:updated_at)
        """,
        "task": """
            INSERT INTO tasks(task_id,workspace_id,title,description,requester_id,owner_agent_id,collaborator_agent_ids,status,priority,due_date,acceptance_criteria,risk_level,budget_limit_usd,created_at,updated_at)
            VALUES(:task_id,:workspace_id,:title,:description,:requester_id,:owner_agent_id,:collaborator_agent_ids,:status,:priority,:due_date,:acceptance_criteria,:risk_level,:budget_limit_usd,:created_at,:updated_at)
        """,
        "task_update": """
            UPDATE tasks SET title=:title, description=:description, requester_id=:requester_id,
            owner_agent_id=:owner_agent_id, collaborator_agent_ids=:collaborator_agent_ids, status=:status,
            priority=:priority, due_date=:due_date, acceptance_criteria=:acceptance_criteria, risk_level=:risk_level,
            budget_limit_usd=:budget_limit_usd, workspace_id=:workspace_id, updated_at=:updated_at WHERE task_id=:task_id
        """,
    }


def fixture_rows() -> dict[str, dict]:
    now = "2026-06-22T02:00:00+00:00"
    return {
        "user": {
            "user_id": "usr_optional_pg",
            "name": "Optional PG User",
            "email": "optional-pg@example.local",
            "role": "founder",
            "created_at": now,
        },
        "agent": {
            "agent_id": "agt_optional_pg",
            "name": "Optional PG Agent",
            "role": "operator",
            "description": "Optional psycopg adapter smoke.",
            "runtime_type": "mock",
            "model_provider": "mock",
            "model_name": "mock-model",
            "status": "idle",
            "permission_level": "standard",
            "allowed_tools": "[]",
            "budget_limit_usd": 0,
            "owner_user_id": "usr_optional_pg",
            "created_at": now,
            "updated_at": now,
        },
        "task": {
            "task_id": "tsk_optional_pg",
            "workspace_id": "ws_optional_pg",
            "title": "Optional Postgres adapter task",
            "description": "Created through optional psycopg adapter.",
            "requester_id": "usr_optional_pg",
            "owner_agent_id": "agt_optional_pg",
            "collaborator_agent_ids": "[]",
            "status": "planned",
            "priority": "medium",
            "due_date": None,
            "acceptance_criteria": "Adapter preserves row shape and workspace filtering.",
            "risk_level": "low",
            "budget_limit_usd": 0,
            "created_at": now,
            "updated_at": now,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run optional psycopg Postgres adapter smoke.")
    parser.add_argument("--image", default=container_smoke.DEFAULT_IMAGE, help="Postgres Docker image to use.")
    parser.add_argument("--skip-if-unavailable", action="store_true", help="Return success with skipped=true when Docker or psycopg is unavailable.")
    parser.add_argument("--no-install-driver", action="store_true", help="Do not install psycopg into a temporary target when missing.")
    args = parser.parse_args()

    reexec_with_bundled_python_if_needed()

    early = container_smoke.docker_available(args.skip_if_unavailable)
    if early is not None:
        return early
    early = container_smoke.ensure_image(args.image, args.skip_if_unavailable)
    if early is not None:
        return early

    with tempfile.TemporaryDirectory(prefix="agentops-optional-pg-") as temp_dir:
        driver_ok, driver_status = ensure_psycopg(Path(temp_dir), install=not args.no_install_driver)
        if not driver_ok:
            return unavailable(f"Optional psycopg driver unavailable: {driver_status}", skip=args.skip_if_unavailable)

        container = f"agentops-pg-optional-adapter-{container_smoke.secrets.token_hex(6)}"
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
            return unavailable((started.stderr or started.stdout or "docker run failed").strip(), skip=args.skip_if_unavailable)

        adapter: PostgresAdapter | None = None
        try:
            if not container_smoke.wait_for_postgres(container):
                return unavailable("Postgres container did not become ready before timeout.", skip=args.skip_if_unavailable)
            port = mapped_port(container)
            dsn = f"postgresql://agentops:{pg_auth}@127.0.0.1:{port}/agentops"
            adapter = wait_for_adapter_connect(dsn)
            adapter.executescript(contract.postgres_ddl_from_sqlite(server.SCHEMA_SQL))
            rows = fixture_rows()
            sql = insert_sql()
            adapter.execute(sql["user"], rows["user"])
            adapter.execute(sql["agent"], rows["agent"])
            adapter.execute(sql["task"], rows["task"])
            task_update = dict(rows["task"], status="running", updated_at="2026-06-22T02:01:00+00:00")
            adapter.execute(sql["task_update"], task_update)
            task = adapter.fetchone(
                "SELECT * FROM tasks WHERE workspace_id=? AND task_id=?",
                ["ws_optional_pg", "tsk_optional_pg"],
            )
            literal = adapter.fetchone(
                "SELECT '?' AS literal_value, task_id FROM tasks WHERE task_id=?",
                ["tsk_optional_pg"],
            )
            percent_literal = adapter.fetchone(
                "SELECT COUNT(*) AS count FROM tasks WHERE workspace_id=? AND title LIKE '%Optional%'",
                ["ws_optional_pg"],
            )
            cross = adapter.fetchall(
                "SELECT * FROM tasks WHERE workspace_id=? AND task_id=?",
                ["ws_optional_pg", "missing_other_workspace"],
            )
            adapter.commit()
            if not task or task.get("status") != "running":
                raise AssertionError(f"task row shape/status mismatch: {task}")
            if literal.get("literal_value") != "?":
                raise AssertionError(f"literal question mark translation failed: {literal}")
            if int((percent_literal or {}).get("count") or 0) != 1:
                raise AssertionError(f"literal percent LIKE translation failed: {percent_literal}")
            if cross:
                raise AssertionError(f"cross-workspace lookup returned rows: {cross}")
            output = {
                "ok": True,
                "skipped": False,
                "contract": "postgres_optional_psycopg_adapter_v1",
                "driver_status": driver_status,
                "driver_install_spec": PSYCOPG_INSTALL_SPEC,
                "image": args.image,
                "free_local_dependencies": [],
                "row_shape": sorted(task.keys()),
                "workspace_filter_rows": len(cross),
                "literal_question_mark": literal.get("literal_value"),
                "literal_percent_like": int((percent_literal or {}).get("count") or 0),
                "next_proof": "Run the full storage-boundary fixture through this optional adapter.",
            }
            print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        except (AssertionError, PostgresAdapterUnavailable, RuntimeError) as exc:
            if adapter is not None:
                adapter.rollback()
            print(json.dumps({
                "ok": False,
                "skipped": False,
                "contract": "postgres_optional_psycopg_adapter_v1",
                "error": str(exc),
            }, ensure_ascii=False, indent=2, sort_keys=True))
            return 1
        finally:
            if adapter is not None:
                adapter.close()
            container_smoke.run(["docker", "rm", "-f", container], timeout=30)


if __name__ == "__main__":
    raise SystemExit(main())
