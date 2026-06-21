#!/usr/bin/env python3
"""Verify async live customer-worker submit is rejected before queueing when an adapter is unavailable."""
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    markers = ["AGENTOPS_API_KEY", "Authorization:", "Bearer ", "agtok_", "agtsess_", "sk-", "ntn_"]
    return any(marker in text for marker in markers)


def main() -> int:
    original_openclaw_bin = server.OPENCLAW_BIN
    missing_openclaw_bin = ROOT / ".agentops_runtime" / "smoke-missing-openclaw-bin"
    if missing_openclaw_bin.exists():
        missing_openclaw_bin.unlink()
    try:
        server.OPENCLAW_BIN = missing_openclaw_bin
        with server.db() as conn:
            server.refresh_runtime_connectors(conn)
            conn.execute(
                "UPDATE runtime_connectors SET trust_status='trusted', trust_note=NULL WHERE runtime_connector_id='rtc_openclaw_local'"
            )
            payload, status = server.submit_customer_worker_task_job(conn, {
                "adapter": "openclaw",
                "confirm_run": True,
                "title": "Async adapter not ready smoke",
                "description": "This async submit must reject before queueing because OpenClaw is unavailable.",
                "acceptance_criteria": "Return adapter_not_ready, failed job evidence, and blocked task evidence.",
            })
            job = conn.execute("SELECT * FROM workflow_jobs WHERE job_id=?", (payload.get("job_id"),)).fetchone()
            task_id = ((payload.get("result") or {}).get("task_id"))
            task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone() if task_id else None
            rejected_events = conn.execute(
                "SELECT COUNT(*) c FROM runtime_events WHERE event_type='workflow_job.rejected' AND output_summary IS NOT NULL"
            ).fetchone()["c"]
        require(status == 409, f"expected 409, got {status}: {payload}")
        require(payload.get("ok") is False, f"async reject should not be ok: {payload}")
        require(payload.get("reason") == "adapter_not_ready", f"wrong reason: {payload}")
        require(payload.get("readiness") == "unavailable", f"wrong readiness: {payload}")
        require(job is not None and job["status"] == "failed", f"failed workflow job missing: {payload}")
        require(task is not None and task["status"] == "blocked", f"blocked task missing: {payload}")
        require((payload.get("job") or {}).get("result", {}).get("reason") == "adapter_not_ready", f"job result missing reason: {payload}")
        require(rejected_events >= 1, "workflow_job.rejected runtime event missing")
        serialized = json.dumps(payload, ensure_ascii=False)
        require(not leaked_secret(serialized), "async adapter-not-ready payload leaked token-like material")
        print(json.dumps({
            "ok": True,
            "status": status,
            "job_id": payload.get("job_id"),
            "job_status": job["status"] if job else None,
            "task_id": task_id,
            "reason": payload.get("reason"),
            "readiness": payload.get("readiness"),
            "secret_leaked": False,
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        server.OPENCLAW_BIN = original_openclaw_bin
        try:
            with server.db() as conn:
                server.refresh_runtime_connectors(conn)
                conn.commit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
