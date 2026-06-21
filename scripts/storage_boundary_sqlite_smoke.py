#!/usr/bin/env python3
"""Verify the first SQLite storage-boundary helpers preserve workspace behavior."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def ids(rows, key: str) -> set[str]:
    return {str(row[key]) for row in rows if row[key]}


def main() -> int:
    owned_db = "AGENTOPS_DB_PATH" not in os.environ
    db_path = ""
    if owned_db:
        handle = tempfile.NamedTemporaryFile(prefix="agentops-storage-boundary-", delete=False)
        db_path = handle.name
        handle.close()
        os.environ["AGENTOPS_DB_PATH"] = db_path

    import server  # noqa: PLC0415

    workspace_a = "ws_storage_a"
    workspace_b = "ws_storage_b"
    agent_a = "agt_storage_a"
    agent_b = "agt_storage_b"
    task_a = "tsk_storage_a"
    task_b = "tsk_storage_b"

    try:
        server.init_schema()
        with server.db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users(user_id,name,email,role,created_at) VALUES(?,?,?,?,?)",
                ("usr_founder", "Founder", "founder@example.local", "founder", server.now_iso()),
            )
            server.ensure_gateway_agent(conn, agent_a, runtime_type="mock")
            server.ensure_gateway_agent(conn, agent_b, runtime_type="mock")
            for workspace_id, agent_id, task_id in [
                (workspace_a, agent_a, task_a),
                (workspace_b, agent_b, task_b),
            ]:
                payload, status = server.create_task_api(conn, {
                    "workspace_id": workspace_id,
                    "task_id": task_id,
                    "title": f"Storage boundary {workspace_id}",
                    "description": "Storage boundary helper smoke task.",
                    "requester_id": "usr_founder",
                    "owner_agent_id": agent_id,
                    "status": "planned",
                    "priority": "medium",
                    "risk_level": "low",
                })
                require(status == 201, f"task create failed: {status} {payload}")
            run_a = server.start_mock_run(conn, {"task_id": task_a, "agent_id": agent_a})["run_id"]
            run_b = server.start_mock_run(conn, {"task_id": task_b, "agent_id": agent_b})["run_id"]
            memory_a, status = server.agent_gateway_memory_propose(conn, {
                "workspace_id": workspace_a,
                "agent_id": agent_a,
                "task_id": task_a,
                "scope": "task",
                "memory_type": "artifact_summary",
                "canonical_text": "Storage boundary memory A.",
            })
            require(status == 201, f"memory A propose failed: {status} {memory_a}")
            memory_b, status = server.agent_gateway_memory_propose(conn, {
                "workspace_id": workspace_b,
                "agent_id": agent_b,
                "task_id": task_b,
                "scope": "task",
                "memory_type": "artifact_summary",
                "canonical_text": "Storage boundary memory B.",
            })
            require(status == 201, f"memory B propose failed: {status} {memory_b}")
            org_memory_a, status = server.agent_gateway_memory_propose(conn, {
                "workspace_id": workspace_a,
                "agent_id": agent_a,
                "scope": "org",
                "memory_type": "policy",
                "canonical_text": "Storage boundary org memory A.",
            })
            require(status == 201, f"org memory propose failed: {status} {org_memory_a}")
            conn.commit()

            task_ids = ids(server.repo_list_workspace_tasks(conn, workspace_a), "task_id")
            require(task_a in task_ids and task_b not in task_ids, f"task helper leaked workspace rows: {task_ids}")
            require(server.repo_get_workspace_task(conn, workspace_a, task_a), "task helper missed workspace A task")
            require(not server.repo_get_workspace_task(conn, workspace_a, task_b), "task helper exposed workspace B task")

            run_ids = ids(server.repo_list_workspace_runs(conn, workspace_a), "run_id")
            require(run_a in run_ids and run_b not in run_ids, f"run helper leaked workspace rows: {run_ids}")
            require(ids(server.repo_list_workspace_runs(conn, workspace_a, task_id=task_a), "run_id") == {run_a}, "run helper task filter failed")
            require(ids(server.repo_list_workspace_runs(conn, workspace_a, agent_id=agent_a), "run_id") == {run_a}, "run helper agent filter failed")
            require(server.repo_get_workspace_run(conn, workspace_a, run_a), "run helper missed workspace A run")
            require(not server.repo_get_workspace_run(conn, workspace_a, run_b), "run helper exposed workspace B run")

            memory_id_a = memory_a["memory"]["memory_id"]
            memory_id_b = memory_b["memory"]["memory_id"]
            org_memory_id_a = org_memory_a["memory"]["memory_id"]
            memory_ids = ids(server.repo_list_workspace_memories(conn, workspace_a), "memory_id")
            require(memory_id_a in memory_ids and org_memory_id_a in memory_ids, f"memory helper missed workspace A rows: {memory_ids}")
            require(memory_id_b not in memory_ids, f"memory helper leaked workspace B rows: {memory_ids}")
            require(server.repo_get_workspace_memory(conn, workspace_a, memory_id_a), "memory helper missed workspace A memory")
            require(not server.repo_get_workspace_memory(conn, workspace_a, memory_id_b), "memory helper exposed workspace B memory")

        print(json.dumps({
            "ok": True,
            "db_path": "isolated_tmp" if owned_db else os.environ.get("AGENTOPS_DB_PATH"),
            "helpers": [
                "repo_list_workspace_tasks",
                "repo_get_workspace_task",
                "repo_list_workspace_runs",
                "repo_get_workspace_run",
                "repo_list_workspace_memories",
                "repo_get_workspace_memory",
            ],
            "workspace_a": workspace_a,
            "workspace_b": workspace_b,
            "run_a": run_a,
            "run_b": run_b,
            "token_omitted": True,
            "raw_prompt_omitted": True,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    finally:
        if owned_db and db_path:
            try:
                os.unlink(db_path)
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
