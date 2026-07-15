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
BACKUP_RESTORE = ROOT / "docs" / "PRIVATE_HOST_BACKUP_RESTORE_ACCEPTANCE.md"

VERSION = "1.6.0-private-host-preview.29"
TAG = f"v{VERSION}"
COMMIT = "574c735541d95b70180254235a385ff764f8c45c"
RELEASE_URL = f"https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/{TAG}"
CHECKSUMS = {
    "manifest": "937529610b6d724698e64db4847251aa5a49bd26dcda05b2a10669ea00b9939c",
    "tar": "373dabd9e1b9fe94d89db769ac33725b84b1f4110ec280b4b94eab3fa75a1dfb",
    "zip": "cfd07bc0b4e8c235746648242b12e11fedcc10144def075f2b7427933abd14e8",
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
    backup = BACKUP_RESTORE.read_text(encoding="utf-8")
    rc_headings = [line for line in rc.splitlines() if line.startswith("## Current Preview ")]
    normalized_second = " ".join(second.split())
    normalized_launcher = " ".join(launcher.split())
    normalized_service = " ".join(service.split()).lower()
    normalized_backup = " ".join(backup.split()).lower()

    require(len(rc_headings) == 1, "RC document must name exactly one Current Preview", failures)
    require("## Current Preview 29" in rc, "preview.29 must be the current RC prerelease", failures)
    require("## Superseded Preview 28" in rc, "preview.28 must be preserved as superseded history", failures)
    require("## Superseded Preview 27" in rc, "preview.27 must be preserved as superseded history", failures)
    require("## Superseded Preview 26" in rc, "preview.26 must be preserved as superseded history", failures)
    require("## Superseded Preview 25" in rc, "preview.25 must be preserved as superseded history", failures)
    require("## Superseded Preview 24" in rc, "preview.24 must be preserved as superseded history", failures)
    require("## Superseded Preview 23" in rc, "preview.23 must be preserved as superseded history", failures)
    require("## Superseded Preview 22" in rc, "preview.22 must be preserved as superseded history", failures)
    require("## Superseded Preview 21" in rc, "preview.21 must be preserved as superseded history", failures)
    require("## Superseded Preview 20" in rc, "preview.20 must be preserved as superseded history", failures)
    require("## Superseded Preview 19" in rc, "preview.19 must be preserved as superseded history", failures)
    require("## Superseded Preview 12" in rc, "preview.12 must be marked superseded", failures)
    require(TAG in rc and VERSION in rc, "current version/tag missing from RC document", failures)
    require(COMMIT in rc and COMMIT in second, "exact release commit missing from acceptance documents", failures)
    require(RELEASE_URL in rc, "public prerelease URL missing from RC document", failures)
    for label, checksum in CHECKSUMS.items():
        require(checksum in rc, f"{label} checksum missing from RC document", failures)

    open_gate_markers = (
        "current-package approved Runtime completion",
        "physical second-device",
        "another-Mac clean install",
        "logout/reboot service proof",
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
    require(TAG in launcher, "installed app receipt must name the current prerelease tag", failures)
    require("The Host PID and both independent service Worker PIDs" in normalized_launcher,
            "launcher receipt must preserve Host and service Worker PIDs", failures)
    require("preview.29 app open" in normalized_launcher,
            "launcher receipt must name the current-package process-reuse check", failures)
    require("browser_visual_readback_performed:false" in normalized_launcher,
            "launcher receipt must not synthesize a preview.29 browser visual check", failures)
    require("the address bar contained no fragment" in normalized_launcher, "launcher receipt must prove fragment scrubbing", failures)
    require("the manual setup-code input was absent" in normalized_launcher, "launcher receipt must prove graphical setup-code handoff", failures)
    require("live_execution_performed:false" in normalized_launcher, "launcher receipt must prove no live task ran", failures)
    require("A separate clean Mac still must" in launcher, "another-Mac launcher gate must remain open", failures)
    require("## Local Service Loaded Receipt" in service, "local loaded-service receipt missing", failures)
    require("preview.29 host service loaded" in normalized_service,
            "installed preview.29 service-load receipt missing", failures)
    require("launchd reports the Host-only service loaded" in service, "loaded Host service receipt missing", failures)
    require("loaded receipt is not logout/reboot proof" in normalized_service, "service receipt must not claim reboot proof", failures)
    require("exact release commit `574c735`" in normalized_service,
            "installed preview.29 service receipt missing", failures)
    require("actual independent hermes and openclaw launchagent units showed both still running" in normalized_service,
            "service restart must preserve independent Worker receipt", failures)
    require("still does not substitute for a physical logout/reboot receipt" in normalized_service,
            "service restart receipt must keep the physical reboot gate open", failures)
    require("## Installed Preview 29 Backup Receipt" in backup,
            "installed preview.29 backup receipt missing", failures)
    require("secret store was excluded" in normalized_backup and "no raw" in normalized_backup,
            "installed backup privacy receipt missing", failures)
    require("not a restore of the user's live ledger" in normalized_backup,
            "installed backup receipt must not claim a live restore", failures)

    output = {
        "operation": "private_host_rc_status_smoke",
        "ok": not failures,
        "version": VERSION,
        "tag": TAG,
        "exact_commit": COMMIT,
        "checksums_recorded": len(CHECKSUMS),
        "local_receipts": [
            "installed_app_launch",
            "host_service_loaded",
            "installed_service_restart",
            "installed_backup_verified",
        ],
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
