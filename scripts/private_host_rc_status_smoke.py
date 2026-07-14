#!/usr/bin/env python3
"""Verify the current Private Host prerelease and open physical gates stay explicit."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RC = ROOT / "docs" / "PRIVATE_HOST_RC_ACCEPTANCE.md"
SECOND_DEVICE = ROOT / "docs" / "PRIVATE_HOST_SECOND_DEVICE_ACCEPTANCE.md"
LAUNCHER = ROOT / "docs" / "PRIVATE_HOST_MACOS_LAUNCHER_ACCEPTANCE.md"
BACKGROUND_SERVICE = ROOT / "docs" / "PRIVATE_HOST_BACKGROUND_SERVICE_ACCEPTANCE.md"

VERSION = "1.6.0-private-host-preview.20"
TAG = f"v{VERSION}"
COMMIT = "3b6518f3870c0e299e74f757da41623e8c14f526"
RELEASE_URL = f"https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/{TAG}"
CHECKSUMS = {
    "manifest": "b8c0c4f38d4764705185469cd5c96da045658779cc79dd90f0b44b17e8470e23",
    "tar": "8ca2e218f178756d1c2773a722d15086078f9158a47a513ea8d15425a81cfe8e",
    "zip": "ab961783542137cb6b7940a2ce1dac2ea575bbe29ff0da2faad6af5bda542a19",
    "bootstrap": "6f78549bdb4c1da6ff3128907d8b82067a3ae06741cf823b34e1acdaaf03a44f",
}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def main() -> int:
    failures: list[str] = []
    rc = RC.read_text(encoding="utf-8")
    second = SECOND_DEVICE.read_text(encoding="utf-8")
    launcher = LAUNCHER.read_text(encoding="utf-8")
    service = BACKGROUND_SERVICE.read_text(encoding="utf-8")
    rc_headings = [line for line in rc.splitlines() if line.startswith("## Current Preview ")]
    normalized_second = " ".join(second.split())
    normalized_launcher = " ".join(launcher.split())

    require(len(rc_headings) == 1, "RC document must name exactly one Current Preview", failures)
    require("## Current Preview 20" in rc, "preview.20 must be the current RC prerelease", failures)
    require("## Superseded Preview 19" in rc, "preview.19 must be preserved as superseded history", failures)
    require("## Superseded Preview 12" in rc, "preview.12 must be marked superseded", failures)
    require(TAG in rc and VERSION in rc, "current version/tag missing from RC document", failures)
    require(COMMIT in rc and COMMIT in second, "exact release commit missing from acceptance documents", failures)
    require(RELEASE_URL in rc, "public prerelease URL missing from RC document", failures)
    for label, checksum in CHECKSUMS.items():
        require(checksum in rc, f"{label} checksum missing from RC document", failures)

    open_gate_markers = (
        "Owner creation",
        "current-package approved Runtime completion",
        "physical second-device",
        "another-Mac clean install",
    )
    for marker in open_gate_markers:
        require(marker in rc, f"open external gate is no longer explicit: {marker}", failures)
    require(
        "Status: execution protocol; physical second-device evidence pending" in second,
        "second-device protocol must remain pending until physical evidence exists",
        failures,
    )
    require("Automated browser runtimes outside the Host tailnet are not accepted as a substitute." in normalized_second,
            "physical evidence anti-substitution boundary missing", failures)
    require("not the final RC" in rc, "prerelease must not claim final RC", failures)
    require("## Installed App Launch Receipt" in launcher, "installed app launch receipt missing", failures)
    require("Host PID remained unchanged" in normalized_launcher, "launcher receipt must preserve Host PID", failures)
    require("Worker PIDs both remained unchanged" in normalized_launcher, "launcher receipt must preserve Worker PIDs", failures)
    require("A separate clean Mac still must" in launcher, "another-Mac launcher gate must remain open", failures)
    require("## Local Service Staging Receipt" in service, "local service staging receipt missing", failures)
    require("launchd has not loaded the service" in service, "service receipt must remain unloaded", failures)
    require("staging alone is not logout/reboot proof" in service, "service receipt must not claim reboot proof", failures)

    output = {
        "operation": "private_host_rc_status_smoke",
        "ok": not failures,
        "version": VERSION,
        "tag": TAG,
        "exact_commit": COMMIT,
        "checksums_recorded": len(CHECKSUMS),
        "local_receipts": ["installed_app_launch", "host_service_staged_unloaded"],
        "external_gates_open": list(open_gate_markers),
        "failures": failures,
        "safety": {
            "network_used": False,
            "physical_evidence_synthesized": False,
            "raw_content_omitted": True,
            "token_omitted": True,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
