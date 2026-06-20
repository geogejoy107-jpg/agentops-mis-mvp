#!/usr/bin/env python3
"""Verify read-only worker service-check commands without installing services."""
from __future__ import annotations

import json
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
    with tempfile.TemporaryDirectory(prefix="agentops_service_check_") as tmp:
        tmp_path = Path(tmp)
        service_path = tmp_path / "local.agentops.worker.agt_service_check.plist"
        template = run([
            sys.executable,
            "-m",
            "agentops_mis_cli.worker",
            "service-template",
            "--manager",
            "launchd",
            "--agent-id",
            "agt_service_check",
            "--adapter",
            "mock",
        ])
        require(template.returncode == 0, f"service-template failed: {template.stderr}", failures)
        service_path.write_text(template.stdout, encoding="utf-8")

        direct = run([
            sys.executable,
            "-m",
            "agentops_mis_cli.worker",
            "service-check",
            "--manager",
            "launchd",
            "--agent-id",
            "agt_service_check",
            "--adapter",
            "mock",
            "--service-path",
            str(service_path),
        ])
        direct_payload = parse_json(direct)
        require(direct.returncode == 0, f"agentops-worker service-check failed: {direct_payload}", failures)
        require(direct_payload.get("ok") is True, f"service-check should be ok for generated template: {direct_payload}", failures)
        require(direct_payload.get("service_file", {}).get("raw_content_omitted") is True, f"raw content should be omitted: {direct_payload}", failures)
        require(direct_payload.get("service_file", {}).get("token_like_detected") is False, f"token-like value detected unexpectedly: {direct_payload}", failures)

        cli = run([
            str(ROOT / "scripts" / "agentops"),
            "worker",
            "service-check",
            "--manager",
            "launchd",
            "--agent-id",
            "agt_service_check",
            "--adapter",
            "mock",
            "--service-path",
            str(service_path),
        ])
        cli_payload = parse_json(cli)
        require(cli.returncode == 0, f"agentops worker service-check failed: {cli_payload}", failures)
        require(cli_payload.get("command") == "agentops worker service-check", f"wrong wrapper command: {cli_payload}", failures)
        require(cli_payload.get("token_omitted") is True, f"token omitted flag missing: {cli_payload}", failures)

        unsafe_path = tmp_path / "unsafe.plist"
        unsafe_path.write_text(template.stdout + "\n<!-- agtok_fake_should_not_be_printed -->\n", encoding="utf-8")
        unsafe = run([
            sys.executable,
            "-m",
            "agentops_mis_cli.worker",
            "service-check",
            "--manager",
            "launchd",
            "--agent-id",
            "agt_service_check",
            "--adapter",
            "mock",
            "--service-path",
            str(unsafe_path),
        ])
        unsafe_payload = parse_json(unsafe)
        require(unsafe.returncode == 1, f"unsafe service-check should fail: {unsafe_payload}", failures)
        require(unsafe_payload.get("service_file", {}).get("token_like_detected") is True, f"unsafe token-like value was not detected: {unsafe_payload}", failures)

        serialized = json.dumps({"direct": direct_payload, "cli": cli_payload, "unsafe": unsafe_payload}, ensure_ascii=False)
        require("agtok_fake_should_not_be_printed" not in serialized, "service-check leaked raw token-like content", failures)
        require("sk-" not in serialized and "ntn_" not in serialized, "service-check leaked secret-like content", failures)

    print(json.dumps({
        "ok": not failures,
        "direct_ok": not failures and direct_payload.get("ok"),
        "cli_ok": not failures and cli_payload.get("ok"),
        "unsafe_detected": unsafe_payload.get("service_file", {}).get("token_like_detected"),
        "failures": failures,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
