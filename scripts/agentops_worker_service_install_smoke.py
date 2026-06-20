#!/usr/bin/env python3
"""Verify safe worker service-install behavior without loading services."""
from __future__ import annotations

import json
import stat
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=60, check=False)


def parse_json(proc: subprocess.CompletedProcess[str]) -> dict:
    try:
        return json.loads(proc.stdout)
    except Exception:
        return {"parse_error": proc.stdout, "stderr": proc.stderr, "returncode": proc.returncode}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops_service_install_") as tmp:
        tmp_path = Path(tmp)
        service_path = tmp_path / "local.agentops.worker.agt_service_install.plist"
        wrapper_path = tmp_path / "local.agentops.worker.agt_service_install_wrapper.plist"

        dry = run([
            sys.executable,
            "-m",
            "agentops_mis_cli.worker",
            "service-install",
            "--manager",
            "launchd",
            "--agent-id",
            "agt_service_install",
            "--adapter",
            "mock",
            "--service-path",
            str(service_path),
        ])
        dry_payload = parse_json(dry)
        require(dry.returncode == 0, f"dry-run install failed: {dry_payload}", failures)
        require(dry_payload.get("dry_run") is True, f"dry-run flag missing: {dry_payload}", failures)
        require(dry_payload.get("wrote") is False and not service_path.exists(), f"dry-run wrote file: {dry_payload}", failures)

        install = run([
            sys.executable,
            "-m",
            "agentops_mis_cli.worker",
            "service-install",
            "--manager",
            "launchd",
            "--agent-id",
            "agt_service_install",
            "--adapter",
            "mock",
            "--service-path",
            str(service_path),
            "--confirm-install",
        ])
        install_payload = parse_json(install)
        require(install.returncode == 0, f"confirmed install failed: {install_payload}", failures)
        require(install_payload.get("wrote") is True and service_path.exists(), f"confirmed install did not write file: {install_payload}", failures)
        require(install_payload.get("service_check", {}).get("ok") is True, f"installed file failed service check: {install_payload}", failures)
        mode = stat.S_IMODE(service_path.stat().st_mode)
        require(mode == 0o600, f"service file mode should be 0600, got {oct(mode)}", failures)

        duplicate = run([
            sys.executable,
            "-m",
            "agentops_mis_cli.worker",
            "service-install",
            "--manager",
            "launchd",
            "--agent-id",
            "agt_service_install",
            "--adapter",
            "mock",
            "--service-path",
            str(service_path),
            "--confirm-install",
        ])
        duplicate_payload = parse_json(duplicate)
        require(duplicate.returncode == 1, f"duplicate install without overwrite should fail: {duplicate_payload}", failures)
        require(duplicate_payload.get("exists_before") is True and duplicate_payload.get("wrote") is False, f"duplicate install wrote file: {duplicate_payload}", failures)

        wrapper = run([
            str(ROOT / "scripts" / "agentops"),
            "worker",
            "service-install",
            "--manager",
            "launchd",
            "--agent-id",
            "agt_service_install_wrapper",
            "--adapter",
            "mock",
            "--service-path",
            str(wrapper_path),
            "--confirm-install",
        ])
        wrapper_payload = parse_json(wrapper)
        require(wrapper.returncode == 0, f"wrapper service-install failed: {wrapper_payload}", failures)
        require(wrapper_payload.get("command") == "agentops worker service-install", f"wrong wrapper command: {wrapper_payload}", failures)
        require(wrapper_payload.get("wrote") is True and wrapper_path.exists(), f"wrapper did not write file: {wrapper_payload}", failures)

        unsafe = run([
            sys.executable,
            "-m",
            "agentops_mis_cli.worker",
            "service-install",
            "--manager",
            "launchd",
            "--agent-id",
            "agt_service_install_unsafe",
            "--adapter",
            "mock",
            "--service-path",
            str(tmp_path / "unsafe.plist"),
            "--api-key-placeholder",
            "agtok_fake_should_not_be_written",
            "--confirm-install",
        ])
        unsafe_payload = parse_json(unsafe)
        require(unsafe.returncode == 1, f"unsafe install should fail: {unsafe_payload}", failures)
        require(unsafe_payload.get("wrote") is False, f"unsafe install wrote file: {unsafe_payload}", failures)

        serialized = json.dumps({
            "dry": dry_payload,
            "install": install_payload,
            "duplicate": duplicate_payload,
            "wrapper": wrapper_payload,
            "unsafe": unsafe_payload,
        }, ensure_ascii=False)
        require("agtok_fake_should_not_be_written" not in serialized, "service-install leaked raw token-like content", failures)
        require("sk-" not in serialized and "ntn_" not in serialized, "service-install leaked secret-like content", failures)

    print(json.dumps({
        "ok": not failures,
        "dry_run_ok": not failures and dry_payload.get("dry_run"),
        "install_wrote": install_payload.get("wrote"),
        "wrapper_wrote": wrapper_payload.get("wrote"),
        "unsafe_blocked": unsafe_payload.get("ok") is False,
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
