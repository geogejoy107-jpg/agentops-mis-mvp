#!/usr/bin/env python3
"""Verify local worker daemon log rotation without starting a daemon."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    original_runtime_dir = server.WORKER_RUNTIME_DIR
    old_max = os.environ.get("AGENTOPS_WORKER_LOG_MAX_BYTES")
    old_backups = os.environ.get("AGENTOPS_WORKER_LOG_BACKUPS")
    try:
        with tempfile.TemporaryDirectory(prefix="agentops_worker_log_rotation_") as tmp:
            runtime_dir = Path(tmp)
            server.WORKER_RUNTIME_DIR = runtime_dir
            os.environ["AGENTOPS_WORKER_LOG_MAX_BYTES"] = "64"
            os.environ["AGENTOPS_WORKER_LOG_BACKUPS"] = "2"

            log_path = server.worker_runtime_path("mock", "log")
            log_path.write_text("first\n" + ("x" * 100), encoding="utf-8")
            first = server.rotate_worker_log_if_needed("mock")
            require(first.get("rotated") is True, f"first rotation did not happen: {first}", failures)
            require(Path(str(log_path) + ".1").exists(), f"first backup missing: {first}", failures)
            require(not log_path.exists(), "active log should be absent until daemon reopens it", failures)

            log_path.write_text("second\n" + ("y" * 100), encoding="utf-8")
            second = server.rotate_worker_log_if_needed("mock")
            require(second.get("rotated") is True, f"second rotation did not happen: {second}", failures)
            require(Path(str(log_path) + ".1").read_text(encoding="utf-8").startswith("second"), "newest backup should be .1", failures)
            require(Path(str(log_path) + ".2").read_text(encoding="utf-8").startswith("first"), "previous backup should shift to .2", failures)

            log_path.write_text("short\n", encoding="utf-8")
            below = server.rotate_worker_log_if_needed("mock")
            require(below.get("rotated") is False and below.get("reason") == "below_threshold", f"below-threshold log rotated: {below}", failures)

            os.environ["AGENTOPS_WORKER_LOG_MAX_BYTES"] = "0"
            disabled = server.rotate_worker_log_if_needed("mock")
            require(disabled.get("enabled") is False and disabled.get("reason") == "disabled", f"disabled rotation failed: {disabled}", failures)

            serialized = json.dumps({"first": first, "second": second, "below": below, "disabled": disabled}, ensure_ascii=False)
            require("Authorization:" not in serialized and "Bearer " not in serialized, "rotation output leaked auth marker", failures)
            require("agtok_" not in serialized and "agtsess_" not in serialized, "rotation output leaked token marker", failures)

        print(json.dumps({
            "ok": not failures,
            "operation": "worker_log_rotation_smoke",
            "rotated": True,
            "backups": 2,
            "disabled_supported": True,
            "failures": failures,
            "safety": {
                "read_only": True,
                "ledger_mutated": False,
                "live_execution_performed": False,
                "token_omitted": True,
            },
        }, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if not failures else 1
    finally:
        server.WORKER_RUNTIME_DIR = original_runtime_dir
        if old_max is None:
            os.environ.pop("AGENTOPS_WORKER_LOG_MAX_BYTES", None)
        else:
            os.environ["AGENTOPS_WORKER_LOG_MAX_BYTES"] = old_max
        if old_backups is None:
            os.environ.pop("AGENTOPS_WORKER_LOG_BACKUPS", None)
        else:
            os.environ["AGENTOPS_WORKER_LOG_BACKUPS"] = old_backups


if __name__ == "__main__":
    raise SystemExit(main())
