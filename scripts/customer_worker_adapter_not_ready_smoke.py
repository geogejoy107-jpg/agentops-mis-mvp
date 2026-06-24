#!/usr/bin/env python3
"""Verify confirmed live customer work is blocked before execution when an adapter is unavailable."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def leaked_secret(text: str) -> bool:
    patterns = [
        re.compile(r"AGENTOPS_API_KEY", re.IGNORECASE),
        re.compile(r"Authorization:", re.IGNORECASE),
        re.compile(r"Bearer\s+(?!\[REDACTED\])[A-Za-z0-9._~+/=-]+", re.IGNORECASE),
        re.compile(r"agtok_[A-Za-z0-9_-]{16,}"),
        re.compile(r"agtsess_[A-Za-z0-9_-]{16,}"),
        re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
        re.compile(r"ntn_[A-Za-z0-9_-]{8,}"),
    ]
    return any(pattern.search(text) for pattern in patterns)


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
            payload, status = server.run_customer_worker_task_workflow(conn, {
                "adapter": "openclaw",
                "confirm_run": True,
                "title": "Adapter not ready smoke",
                "description": "This must stop before live OpenClaw execution because the binary is unavailable.",
                "acceptance_criteria": "Return adapter_not_ready and write blocked task evidence.",
            })
            task = conn.execute("SELECT * FROM tasks WHERE task_id=?", (payload.get("task_id"),)).fetchone()
            audit_count = conn.execute(
                "SELECT COUNT(*) c FROM audit_logs WHERE entity_id=? AND action='workflow.customer_worker_task.adapter_not_ready'",
                (payload.get("task_id"),),
            ).fetchone()["c"]
        require(status == 409, f"expected 409, got {status}: {payload}")
        require(payload.get("reason") == "adapter_not_ready", f"wrong reason: {payload}")
        require(payload.get("readiness") == "unavailable", f"wrong readiness: {payload}")
        require(payload.get("dry_run") is True, f"adapter-not-ready path must be dry-run: {payload}")
        require(payload.get("ok") is False, f"adapter-not-ready path must not be ok: {payload}")
        require(bool(payload.get("recommended_action")), f"missing recovery action: {payload}")
        require(task is not None and task["status"] == "blocked", f"blocked task missing: {payload}")
        require(audit_count >= 1, f"audit evidence missing for {payload.get('task_id')}")
        serialized = json.dumps(payload, ensure_ascii=False)
        require(not leaked_secret(serialized), "adapter-not-ready payload leaked token-like material")
        print(json.dumps({
            "ok": True,
            "status": status,
            "task_id": payload.get("task_id"),
            "reason": payload.get("reason"),
            "readiness": payload.get("readiness"),
            "recommended_action": payload.get("recommended_action"),
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
