#!/usr/bin/env python3
"""Verify the current Private Host prerelease and open physical gates stay explicit."""
from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RC = ROOT / "docs" / "PRIVATE_HOST_RC_ACCEPTANCE.md"
SECOND_DEVICE = ROOT / "docs" / "PRIVATE_HOST_SECOND_DEVICE_ACCEPTANCE.md"
SERVICE_UPGRADE = ROOT / "docs" / "PRIVATE_HOST_SERVICE_UPGRADE_MIGRATION_ACCEPTANCE.md"
REAL_RUNTIME = ROOT / "docs" / "PRIVATE_HOST_REAL_RUNTIME_CLIENT_ACCEPTANCE.md"

VERSION = "1.6.0-private-host-preview.35"
TAG = f"v{VERSION}"
COMMIT = "6424ec144013517b21438cd7e528c6db106a0a5e"
RELEASE_URL = f"https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/{TAG}"
CHECKSUMS = {
    "provenance": "bb87a5c74ec2b5afd510b92ee3023a97991e156d98f6556a871ece3250f8cbe4",
    "manifest": "b4cd6da7dc6bd327eef292d188699f38e8a69bc77f0ae8619dfccf85e9663386",
    "tar": "77ba016157dcd0880a42bc17bc1a5aad6a9cb26039506e769c7315018cf973ca",
    "zip": "02703e5b4dabdf3cc1dec501cc5dbe8735798493fcab1928d5ea0e4c266a2f6c",
    "bootstrap": "75854f364502722eb24d5a7df3c0fc26685bf25acae6d5926e4c6396d16bd812",
}


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def heading_section(text: str, heading: str) -> str:
    marker = f"## {heading}"
    start = text.find(marker)
    if start < 0:
        return ""
    remainder = text[start:]
    next_heading = remainder.find("\n## ", len(marker))
    return remainder if next_heading < 0 else remainder[:next_heading]


def main() -> int:
    failures: list[str] = []
    rc = RC.read_text(encoding="utf-8")
    second = SECOND_DEVICE.read_text(encoding="utf-8")
    service_upgrade = SERVICE_UPGRADE.read_text(encoding="utf-8")
    runtime = REAL_RUNTIME.read_text(encoding="utf-8")
    rc_headings = [line for line in rc.splitlines() if line.startswith("## Current Preview ")]
    current_rc = heading_section(rc, "Current Preview 35")
    normalized_current_rc = " ".join(current_rc.split())
    normalized_second = " ".join(second.split())
    normalized_service = " ".join(service_upgrade.split())
    normalized_runtime = " ".join(runtime.split())

    require(len(rc_headings) == 1, "RC document must name exactly one Current Preview", failures)
    require("## Current Preview 35" in rc, "preview.35 must be the current RC prerelease", failures)
    require("## Superseded Preview 31" in rc, "preview.31 must be preserved as superseded history", failures)
    require("## Superseded Preview 30" in rc, "preview.30 must preserve its immutable upgrade-defect history", failures)
    require("## Superseded Preview 29" in rc, "preview.29 must be preserved as superseded history", failures)
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
    require(TAG in current_rc and VERSION in current_rc, "current version/tag missing from current RC section", failures)
    require(COMMIT in current_rc and COMMIT in second, "exact release commit missing from current acceptance evidence", failures)
    require(RELEASE_URL in current_rc, "public prerelease URL missing from current RC section", failures)
    for label, checksum in CHECKSUMS.items():
        require(checksum in current_rc, f"{label} checksum missing from current RC section", failures)

    open_gate_markers = (
        "deployed Relay/DNS/TLS",
        "physical pairing and authenticated dispatch",
        "physical disconnect/reconnect",
        "Host logout/reboot recovery",
        "another-Mac clean installation",
    )
    for marker in open_gate_markers:
        require(marker.lower() in normalized_current_rc.lower(), f"open external gate is no longer explicit in current RC section: {marker}", failures)
    require("The current preview therefore remains a prerelease." in current_rc,
            "current preview must not claim final RC", failures)

    require(
        "Status: advanced Tailscale-mode protocol; browser-only Relay protocol pending" in second,
        "second-device document must identify Tailscale as an advanced fallback and keep browser-only Relay pending",
        failures,
    )
    require(
        "cannot close the browser-only Console gate" in normalized_second,
        "advanced Tailscale receipt must not substitute for browser-only Console acceptance",
        failures,
    )
    require("Automated browser runtimes outside the Host tailnet are not accepted as a substitute." in normalized_second,
            "physical evidence anti-substitution boundary missing", failures)
    require("## Preview 35 MacBook Client Staging" in second,
            "physical MacBook preview.35 staging receipt missing", failures)
    require(TAG in second and COMMIT in second,
            "physical MacBook receipt must bind the exact preview.35 package", failures)
    require("all returned HTTP 401" in normalized_second and "task count remained 25 before and after" in normalized_second,
            "physical MacBook anonymous denial receipt missing", failures)
    require("it does not prove an authenticated Console workflow" in normalized_second,
            "physical MacBook receipt must keep authenticated workflow open", failures)
    require("Tailscale Serve remained the transport and Funnel stayed disabled" in normalized_second,
            "advanced transport boundary missing from MacBook receipt", failures)

    require(TAG in service_upgrade and COMMIT in service_upgrade,
            "preview.35 service-upgrade receipt is not exact-package bound", failures)
    require("no-repository install/start/status/stop receipt" in normalized_service,
            "preview.35 no-repository release receipt missing", failures)
    require("preserved user data" in normalized_service and "fresh idle heartbeats" in normalized_service,
            "preview.35 data/Worker recovery receipt missing", failures)
    require("Funnel disabled" in normalized_service,
            "preview.35 upgrade must preserve the private transport boundary", failures)

    require(TAG in runtime and COMMIT in runtime,
            "preview.35 Runtime receipt is not exact-package bound", failures)
    require("run_gw_45eac4968e30" in runtime and "run_gw_7ac27edaf52c" in runtime,
            "fresh preview.35 OpenClaw/Hermes run evidence missing", failures)
    require("ap_customer_worker_delivery_run_gw_7ac27edaf52c` remains `pending`" in runtime,
            "Hermes Human Approval Wall state is no longer explicit", failures)
    require("No raw prompt, raw response, credential, private message, full transcript or database content was retained" in normalized_runtime,
            "preview.35 Runtime privacy boundary missing", failures)

    output = {
        "operation": "private_host_rc_status_smoke",
        "ok": not failures,
        "version": VERSION,
        "tag": TAG,
        "exact_commit": COMMIT,
        "checksums_recorded": len(CHECKSUMS),
        "local_receipts": [
            "release_asset_install",
            "service_upgrade_migration",
            "real_runtime_evidence",
            "physical_macbook_anonymous_boundary",
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
