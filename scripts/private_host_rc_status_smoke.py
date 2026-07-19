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

VERSION = "1.6.0-private-host-preview.36"
TAG = f"v{VERSION}"
COMMIT = "a5c7d559cfce5157b10401e34204a6b6a405a554"
RELEASE_URL = f"https://github.com/geogejoy107-jpg/agentops-mis-mvp/releases/tag/{TAG}"
PHYSICAL_VERSION = "1.6.0-private-host-preview.35"
PHYSICAL_TAG = f"v{PHYSICAL_VERSION}"
PHYSICAL_COMMIT = "6424ec144013517b21438cd7e528c6db106a0a5e"
CHECKSUMS = {
    "provenance": "fc7ca64aab0b4cd573365ed18dc2dd8e3f39cc792092b2974beb8fc0ddb6beac",
    "manifest": "1868238dc606b4dc4728e70ad6e6028699e6925fcf1a7ba0c45034a91efb2377",
    "tar": "3cb5e38cd772a1fea0ecfc74f529fec2bc068d069e055c67e7454077b2f9842b",
    "zip": "9c8dd0abc955c974aeb2374bf2d52a92ccc877e445fd76810a2101759d961c6c",
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
    current_rc = heading_section(rc, "Current Preview 36")
    normalized_current_rc = " ".join(current_rc.split())
    normalized_second = " ".join(second.split())
    normalized_service = " ".join(service_upgrade.split())
    normalized_runtime = " ".join(runtime.split())

    require(len(rc_headings) == 1, "RC document must name exactly one Current Preview", failures)
    require("## Current Preview 36" in rc, "preview.36 must be the current RC prerelease", failures)
    require("## Superseded Preview 35" in rc, "preview.35 physical evidence must be preserved as superseded history", failures)
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
        "no-Tailscale browser pairing",
        "deployed-Relay interruption",
        "launchd convergence fix is installed",
        "Host logout/reboot recovery",
        "another-Mac clean installation",
    )
    for marker in open_gate_markers:
        require(marker.lower() in normalized_current_rc.lower(), f"open external gate is no longer explicit in current RC section: {marker}", failures)
    require("The current preview therefore remains a prerelease." in current_rc,
            "current preview must not claim final RC", failures)

    require(
        "Status: preview.36 Host package" in second
        and "ordinary browser-only Relay protocol remains pending" in second,
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
    require("## Preview 36 Host Staging" in second,
            "preview.36 Host staging receipt missing", failures)
    require(TAG in second and COMMIT in second,
            "preview.36 Host staging is not exact-package bound", failures)
    require("## Preview 36 Physical MacBook Retest" in second,
            "preview.36 physical MacBook retest receipt missing", failures)
    require("tsk_570cb03937f6" in second and "run_gw_c8d2ad1aa845" in second,
            "preview.36 physical marker or OpenClaw run evidence missing", failures)
    require("zero external-write PreparedActions" in normalized_second
            and "protected Dashboard request returned HTTP 401" in normalized_second,
            "preview.36 physical safety/logout proof missing", failures)
    require("## Preview 35 MacBook Client Staging" in second,
            "physical MacBook preview.35 staging receipt missing", failures)
    require(PHYSICAL_TAG in second and PHYSICAL_COMMIT in second,
            "physical MacBook receipt must bind the exact preview.35 package", failures)
    require("all returned HTTP 401" in normalized_second and "task count remained 25 before and after" in normalized_second,
            "physical MacBook anonymous denial receipt missing", failures)
    require("Tailscale Serve remained the transport and Funnel stayed disabled" in normalized_second,
            "advanced transport boundary missing from MacBook receipt", failures)
    require("## Preview 35 Authenticated MacBook Evidence" in second,
            "authenticated physical MacBook evidence section missing", failures)
    require("run_gw_edfe2753846f" in second and "phr_c2ea51dd3d37a09055e20889" in second,
            "authenticated MacBook run/receipt evidence missing", failures)
    require("disconnect/reconnect passed: true" in normalized_second and "logout denial passed: true" in normalized_second,
            "physical browser disconnect or logout-denial evidence missing", failures)
    require("70bae606c577191041778a92e3480138f3b67795" in second
            and "preview.36 packages the fix" in normalized_second
            and "closes the exact-package physical retest" in normalized_second,
            "preview.35 marker defect history or preview.36 closure is missing", failures)
    require("overall second-device protocol remains partial" in normalized_second,
            "advanced receipt must not claim ordinary browser-only acceptance", failures)

    require(TAG in service_upgrade and COMMIT in service_upgrade,
            "preview.36 service-upgrade receipt is not exact-package bound", failures)
    require("no-repository install/start/status/stop receipt" in normalized_service,
            "preview.36 no-repository release receipt missing", failures)
    require("preserved Host data" in normalized_service and "two execution-capacity lanes" in normalized_service,
            "preview.36 data/Worker recovery receipt missing", failures)
    require("Funnel disabled" in normalized_service,
            "preview.36 upgrade must preserve the private transport boundary", failures)

    require(PHYSICAL_TAG in runtime and PHYSICAL_COMMIT in runtime,
            "preview.35 Runtime receipt is not exact-package bound", failures)
    require("run_gw_45eac4968e30" in runtime and "run_gw_7ac27edaf52c" in runtime,
            "fresh preview.35 OpenClaw/Hermes run evidence missing", failures)
    require("ap_customer_worker_delivery_run_gw_7ac27edaf52c` remains `pending`" in runtime,
            "Hermes Human Approval Wall state is no longer explicit", failures)
    require("No raw prompt, raw response, credential, private message, full transcript or database content was retained" in normalized_runtime,
            "preview.35 Runtime privacy boundary missing", failures)
    require(TAG in runtime and COMMIT in runtime,
            "preview.36 Runtime receipt is not exact-package bound", failures)
    require("run_gw_ed42f579d487" in runtime and "pem_e1b9275c986daf4b" in runtime,
            "fresh preview.36 OpenClaw negated-intent evidence missing", failures)
    require("ap_customer_worker_delivery_run_gw_ed42f579d487` remains `pending`" in runtime,
            "preview.36 delivery decision boundary is no longer explicit", failures)
    require("zero PreparedActions" in normalized_runtime,
            "preview.36 negated external-write proof missing", failures)
    require("## Exact-Package Preview 36 Physical MacBook Result" in runtime,
            "preview.36 physical Runtime receipt missing", failures)
    require("wfjob_9940b1e6ea15" in runtime and "run_gw_c8d2ad1aa845" in runtime
            and "pem_094a19932cdcc50e" in runtime,
            "preview.36 physical OpenClaw evidence is incomplete", failures)
    require("ap_customer_worker_delivery_run_gw_c8d2ad1aa845` remains `pending`" in runtime,
            "preview.36 physical delivery decision boundary is no longer explicit", failures)

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
            "preview36_negated_read_only_runtime",
            "physical_macbook_anonymous_boundary",
            "physical_macbook_authenticated_workflow",
            "preview36_physical_marker",
            "preview36_physical_openclaw_runtime",
            "physical_browser_disconnect_reconnect",
            "approved_artifact_and_host_receipt_download",
            "physical_logout_denial",
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
