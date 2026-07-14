#!/usr/bin/env python3
"""Exercise the preview-first, host-only macOS LaunchAgent lifecycle."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def run(env: dict[str, str], *arguments: str, expected: tuple[int, ...] = (0,)) -> tuple[int, dict, str]:
    process = subprocess.run(
        [sys.executable, "-m", "agentops_mis_cli", "host", *arguments],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    try:
        payload = json.loads(process.stdout)
    except ValueError:
        payload = {}
    if process.returncode not in expected:
        raise RuntimeError(
            f"host {' '.join(arguments)} exited {process.returncode}: "
            f"stdout={process.stdout[-800:]} stderr={process.stderr[-800:]}"
        )
    return process.returncode, payload, process.stdout + process.stderr


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="agentops-host-service-") as temporary:
        temp = Path(temporary)
        host_home = temp / "host"
        service_path = temp / "LaunchAgents" / "dev.agentops.mis.private-host.plist"
        launchctl_state = temp / "launchctl.loaded"
        launchctl_calls = temp / "launchctl.calls"
        fake_launchctl = temp / "launchctl"
        fake_launchctl.write_text(
            "#!/bin/sh\n"
            "set -eu\n"
            f"printf '%s\\n' \"$*\" >> {launchctl_calls}\n"
            "case \"${1:-}\" in\n"
            "  print) [ -f \"$AGENTOPS_TEST_LAUNCHCTL_STATE\" ] ;;\n"
            "  bootstrap) : > \"$AGENTOPS_TEST_LAUNCHCTL_STATE\" ;;\n"
            "  bootout) rm -f \"$AGENTOPS_TEST_LAUNCHCTL_STATE\" ;;\n"
            "  kickstart) [ -f \"$AGENTOPS_TEST_LAUNCHCTL_STATE\" ] ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        fake_launchctl.chmod(0o700)
        env = os.environ.copy()
        env.update(
            {
                "AGENTOPS_HOST_HOME": str(host_home),
                "AGENTOPS_INSTALL_ROOT": str(ROOT),
                "AGENTOPS_LAUNCHCTL_BIN": str(fake_launchctl),
                "AGENTOPS_TEST_LAUNCHCTL_STATE": str(launchctl_state),
            }
        )

        run(env, "init", "--port", "18998")
        _, preview, preview_output = run(env, "service-install", "--service-path", str(service_path))
        require(preview.get("dry_run") is True, "service install must default to dry-run", failures)
        require(preview.get("wrote") is False and not service_path.exists(), "dry-run wrote a service file", failures)
        require(preview.get("workers") == [], "service preview must declare an empty Worker set", failures)
        require(preview.get("live_workers_started") is False, "service preview claimed live Worker execution", failures)
        require("agthost_" not in preview_output and "agtadmin_" not in preview_output, "service preview exposed a Host credential", failures)

        _, installed, installed_output = run(
            env,
            "service-install",
            "--service-path",
            str(service_path),
            "--confirm-install",
        )
        require(installed.get("wrote") is True, "confirmed install did not write the service file", failures)
        require(service_path.exists() and service_path.stat().st_mode & 0o077 == 0, "service file is not mode 0600", failures)
        require("agthost_" not in installed_output and "agtadmin_" not in installed_output, "confirmed install output exposed a Host credential", failures)
        service = service_path.read_text(encoding="utf-8")
        require("<string>start</string>" in service and "<string>--foreground</string>" in service and "<string>--no-workers</string>" in service, "Host command is not host-only", failures)
        require("<string>--worker</string>" not in service and "--confirm-live-workers" not in service, "service command can start live Workers", failures)
        require("<key>RunAtLoad</key>\n  <true/>" in service and "<key>KeepAlive</key>\n  <true/>" in service, "service relaunch policy is missing", failures)
        require(all(f"<key>{key}</key>" in service for key in ("AGENTOPS_HOST_HOME", "AGENTOPS_INSTALL_ROOT", "PYTHONPATH")), "expected service environment is incomplete", failures)
        require("AGENTOPS_API_KEY" not in service and "AGENTOPS_ADMIN_KEY" not in service, "service environment contains credential keys", failures)
        require(not any(prefix in service for prefix in ("agthost_", "agtadmin_", "agtok_", "agtsess_", "ntn_", "sk-")), "service file contains token-like material", failures)

        _, checked, _ = run(env, "service-check", "--service-path", str(service_path))
        require(checked.get("ok") is True, f"installed service check failed: {checked}", failures)
        require(checked.get("service_state", {}).get("loaded") is False, "service unexpectedly loaded during install", failures)

        unavailable_env = {**env, "AGENTOPS_LAUNCHCTL_BIN": str(temp / "missing-launchctl")}
        _, unverified_control, _ = run(
            unavailable_env,
            "service-control",
            "--action",
            "load",
            "--service-path",
            str(service_path),
            "--confirm-control",
            expected=(1,),
        )
        require("launchctl_unavailable" in (unverified_control.get("blockers") or []), "control did not fail closed without launchctl", failures)
        _, unverified_remove, _ = run(
            unavailable_env,
            "service-remove",
            "--service-path",
            str(service_path),
            "--confirm-remove",
            expected=(1,),
        )
        require("launchctl_state_unverified" in (unverified_remove.get("blockers") or []), "remove did not fail closed without launchctl", failures)
        require(service_path.exists(), "unverified removal deleted the service file", failures)

        calls_before = launchctl_calls.read_text(encoding="utf-8").splitlines() if launchctl_calls.exists() else []
        _, load_preview, _ = run(env, "service-control", "--action", "load", "--service-path", str(service_path))
        calls_after = launchctl_calls.read_text(encoding="utf-8").splitlines()
        require(load_preview.get("dry_run") is True and load_preview.get("service_mutated") is False, "load preview mutated service state", failures)
        require(not launchctl_state.exists(), "load preview marked the service loaded", failures)
        require(calls_after == calls_before + [f"print gui/{os.getuid()}/dev.agentops.mis.private-host"], "load preview executed more than read-only status", failures)

        _, loaded, _ = run(
            env,
            "service-control",
            "--action",
            "load",
            "--service-path",
            str(service_path),
            "--confirm-control",
        )
        require(loaded.get("service_mutated") is True and launchctl_state.exists(), f"confirmed load failed: {loaded}", failures)
        _, loaded_again, _ = run(
            env,
            "service-control",
            "--action",
            "load",
            "--service-path",
            str(service_path),
            "--confirm-control",
        )
        require(loaded_again.get("service_control_skipped") is True, "confirmed duplicate load was not idempotent", failures)

        _, remove_blocked, _ = run(
            env,
            "service-remove",
            "--service-path",
            str(service_path),
            "--confirm-remove",
            expected=(1,),
        )
        require("service_still_loaded" in (remove_blocked.get("blockers") or []), "loaded service removal did not fail closed", failures)
        require(service_path.exists(), "loaded service file was removed", failures)

        _, restarted, _ = run(
            env,
            "service-control",
            "--action",
            "restart",
            "--service-path",
            str(service_path),
            "--confirm-control",
        )
        require(restarted.get("service_mutated") is True, f"confirmed restart failed: {restarted}", failures)
        _, unloaded, _ = run(
            env,
            "service-control",
            "--action",
            "unload",
            "--service-path",
            str(service_path),
            "--confirm-control",
        )
        require(unloaded.get("service_mutated") is True and not launchctl_state.exists(), f"confirmed unload failed: {unloaded}", failures)
        _, remove_preview, _ = run(env, "service-remove", "--service-path", str(service_path))
        require(remove_preview.get("dry_run") is True and service_path.exists(), "remove preview deleted the service", failures)
        _, removed, _ = run(env, "service-remove", "--service-path", str(service_path), "--confirm-remove")
        require(removed.get("removed") is True and not service_path.exists(), "confirmed service removal failed", failures)

        service_path.parent.mkdir(parents=True, exist_ok=True)
        service_path.write_text("unmanaged service", encoding="utf-8")
        _, refused, _ = run(
            env,
            "service-install",
            "--service-path",
            str(service_path),
            "--confirm-install",
            "--overwrite",
            expected=(1,),
        )
        require("existing_service_not_owned" in (refused.get("blockers") or []), "unmanaged service overwrite did not fail closed", failures)
        require(service_path.read_text(encoding="utf-8") == "unmanaged service", "unmanaged service file was overwritten", failures)

    result = {
        "ok": not failures,
        "failures": failures,
        "preview_first_install": True,
        "explicit_control_confirmation": True,
        "host_only_no_workers": True,
        "credential_material_omitted": True,
        "unmanaged_file_overwrite_blocked": True,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
