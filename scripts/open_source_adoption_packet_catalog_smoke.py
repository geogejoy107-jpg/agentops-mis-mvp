#!/usr/bin/env python3
"""Validate concrete open-source adoption packets."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKET_DIR = ROOT / "docs" / "open_source_adoption_packets"
SPEC = ROOT / "docs" / "OPEN_SOURCE_ADOPTION_PACKET_SPEC.md"
CI = ROOT / ".github" / "workflows" / "ci.yml"
RELEASE_SMOKE = ROOT / "scripts" / "release_evidence_packet_smoke.py"
RELEASE_DOC = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"

COMMAND = "python3 scripts/open_source_adoption_packet_catalog_smoke.py"

REQUIRED_FIELDS = [
    "packet_id",
    "packet_version",
    "source_name",
    "source_url_or_branch",
    "source_kind",
    "license_summary",
    "owner_lane",
    "mis_authority_objects_touched",
    "intake_lane",
    "allowed_operations",
    "forbidden_operations",
    "raw_data_omissions",
    "runtime_requirements",
    "verification_commands",
    "product_claim_limit",
    "merge_decision",
    "rollback_plan",
    "evidence_refs",
]

VALID_LANES = {
    "research_packet",
    "incubator",
    "adapter",
    "read_model",
    "first_party_migration",
    "reject",
}

LIST_FIELDS = {
    "mis_authority_objects_touched",
    "allowed_operations",
    "forbidden_operations",
    "raw_data_omissions",
    "runtime_requirements",
    "verification_commands",
    "evidence_refs",
}

REQUIRED_OMISSIONS = [
    "raw prompts",
    "raw responses",
    "credentials",
    "tokens",
    "private messages",
    "full transcripts",
    "local DBs",
    "generated exports",
    "customer raw documents",
]

STAR_OFFICE_REQUIRED = {
    "packet_id": "ospkt_star_office_ui_read_model_v1",
    "source_name": "Star Office UI visual base",
    "intake_lane": "read_model",
}

SPATIAL_RESEARCH_REQUIRED = {
    "packet_id": "ospkt_spatial_research_art_source_v1",
    "source_name": "Spatial Research District art source branch",
    "intake_lane": "incubator",
}

UI_V2_REQUIRED = {
    "packet_id": "ospkt_ui_v2_mission_control_source_v1",
    "source_name": "UI v2 Mission Control source branch",
    "intake_lane": "first_party_migration",
}

SECRET_PATTERNS = [
    re.compile(r"Authorization:\s*(Bearer|Basic|Token)\s+", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"gh[opsu]_[A-Za-z0-9_]+"),
]


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def as_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def validate_packet(path: Path, packet: dict[str, Any], failures: list[str]) -> dict[str, Any]:
    prefix = str(path.relative_to(ROOT))
    for field in REQUIRED_FIELDS:
        require(field in packet, f"{prefix}: missing field {field}", failures)
    for field in LIST_FIELDS:
        require(isinstance(packet.get(field), list) and bool(packet.get(field)), f"{prefix}: {field} must be a non-empty list", failures)

    packet_id = str(packet.get("packet_id") or "")
    require(packet_id.startswith("ospkt_"), f"{prefix}: packet_id must start with ospkt_", failures)
    require(str(packet.get("packet_version") or ""), f"{prefix}: packet_version is empty", failures)
    require(packet.get("intake_lane") in VALID_LANES, f"{prefix}: invalid intake_lane {packet.get('intake_lane')}", failures)
    require(str(packet.get("product_claim_limit") or ""), f"{prefix}: product_claim_limit is empty", failures)
    require(str(packet.get("rollback_plan") or ""), f"{prefix}: rollback_plan is empty", failures)

    omissions_lower = "\n".join(as_list(packet.get("raw_data_omissions"))).lower()
    for marker in REQUIRED_OMISSIONS:
        require(marker.lower() in omissions_lower, f"{prefix}: raw-data omission missing {marker}", failures)

    forbidden_lower = "\n".join(as_list(packet.get("forbidden_operations"))).lower()
    require("authority" in forbidden_lower, f"{prefix}: forbidden operations must mention authority boundary", failures)
    require("agentops mis" in str(packet.get("product_claim_limit") or "").lower(), f"{prefix}: claim limit must name AgentOps MIS", failures)

    for command in as_list(packet.get("verification_commands")):
        if command.startswith("python3 scripts/"):
            script = command.split()[1]
            require((ROOT / script).exists(), f"{prefix}: verification script missing: {script}", failures)
    for ref in as_list(packet.get("evidence_refs")):
        if ref.startswith("docs/") or ref.startswith("knowledge/") or ref.startswith("scripts/"):
            require((ROOT / ref).exists(), f"{prefix}: evidence ref missing: {ref}", failures)

    return {
        "packet_id": packet_id,
        "source_name": packet.get("source_name"),
        "intake_lane": packet.get("intake_lane"),
        "merge_decision": packet.get("merge_decision"),
        "product_claim_limit": packet.get("product_claim_limit"),
    }


def main() -> int:
    failures: list[str] = []
    require(SPEC.exists(), "missing adoption packet spec", failures)
    require(PACKET_DIR.exists(), "missing adoption packet directory", failures)
    packets: list[dict[str, Any]] = []
    packet_ids: set[str] = set()

    for path in sorted(PACKET_DIR.glob("*.json")):
        text = read(path)
        require(not any(pattern.search(text) for pattern in SECRET_PATTERNS), f"{path.relative_to(ROOT)}: secret-like marker found", failures)
        try:
            packet = json.loads(text)
        except json.JSONDecodeError as exc:
            failures.append(f"{path.relative_to(ROOT)}: invalid json: {exc}")
            continue
        require(isinstance(packet, dict), f"{path.relative_to(ROOT)}: packet must be a json object", failures)
        if not isinstance(packet, dict):
            continue
        summary = validate_packet(path, packet, failures)
        packet_id = summary["packet_id"]
        require(packet_id not in packet_ids, f"duplicate packet_id: {packet_id}", failures)
        packet_ids.add(packet_id)
        packets.append(summary)

    require(bool(packets), "no adoption packets found", failures)
    star = next((packet for packet in packets if packet.get("packet_id") == STAR_OFFICE_REQUIRED["packet_id"]), None)
    require(star is not None, "missing Star Office adoption packet", failures)
    if star:
        for key, expected in STAR_OFFICE_REQUIRED.items():
            require(star.get(key) == expected, f"Star Office packet {key} mismatch: {star.get(key)}", failures)
        require(
            "commercial assets must be original or separately licensed" in str(star.get("product_claim_limit") or ""),
            "Star Office packet claim limit must preserve asset license boundary",
            failures,
        )

    spatial = next((packet for packet in packets if packet.get("packet_id") == SPATIAL_RESEARCH_REQUIRED["packet_id"]), None)
    require(spatial is not None, "missing Spatial Research art adoption packet", failures)
    if spatial:
        for key, expected in SPATIAL_RESEARCH_REQUIRED.items():
            require(spatial.get(key) == expected, f"Spatial Research packet {key} mismatch: {spatial.get(key)}", failures)
        require(
            "no PR #23 art outputs or Advanced Spatial route are product-merged" in str(spatial.get("product_claim_limit") or ""),
            "Spatial Research packet claim limit must block direct PR #23 asset/route merge",
            failures,
        )

    ui_v2 = next((packet for packet in packets if packet.get("packet_id") == UI_V2_REQUIRED["packet_id"]), None)
    require(ui_v2 is not None, "missing UI v2 adoption packet", failures)
    if ui_v2:
        for key, expected in UI_V2_REQUIRED.items():
            require(ui_v2.get(key) == expected, f"UI v2 packet {key} mismatch: {ui_v2.get(key)}", failures)
        require(
            "no PR #11 shell, Mission Control route, generated screenshot workflow, or read-model replacement is product-merged" in str(ui_v2.get("product_claim_limit") or ""),
            "UI v2 packet claim limit must block direct PR #11 UI shell/read-model merge",
            failures,
        )

    ci = read(CI)
    release_smoke = read(RELEASE_SMOKE)
    release_doc = read(RELEASE_DOC)
    require(COMMAND in ci, "CI workflow missing adoption packet catalog smoke", failures)
    require(COMMAND in release_smoke, "release evidence smoke missing adoption packet catalog smoke", failures)
    require(COMMAND in release_doc, "release evidence doc missing adoption packet catalog smoke", failures)

    output = {
        "operation": "open_source_adoption_packet_catalog_smoke",
        "ok": not failures,
        "failure_count": len(failures),
        "failures": failures,
        "packet_count": len(packets),
        "packets": packets,
        "safety": {
            "read_only": True,
            "db_read": False,
            "ledger_mutated": False,
            "live_execution_performed": False,
            "third_party_assets_committed": False,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "token_omitted": True,
        },
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
