#!/usr/bin/env python3
"""Release evidence entry-point smoke for the commercial migration branch."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
PACKET_PATH = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.json"
PACKET_DOC = ROOT / "docs" / "RELEASE_EVIDENCE_PACKET.md"
COMMERCIAL_PACKET = ROOT / "docs" / "COMMERCIAL_RELEASE_EVIDENCE_PACKET.json"
COMMERCIAL_SMOKE = ROOT / "scripts" / "commercial_release_evidence_packet_smoke.py"
CONTRACT_ID = "release_evidence_packet_v1"
COMMERCIAL_CONTRACT_ID = "commercial_release_evidence_packet_v1"

REQUIRED_GATE5_COMMANDS = {
    "python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture",
    "python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture",
    "python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
    "HERMES_ALLOW_REAL_RUN=true python3 scripts/local_runtime_acceptance.py --live-openclaw --live-hermes --require-hermes-api",
}

REQUIRED_GATE5_CONTRACTS = {
    "deployment_readiness_postgres_runtime_write_fixture_v1",
    "nextjs_deployment_postgres_runtime_write_fixture_v1",
    "byoc_deployment_acceptance_v1",
    "postgres_http_runtime_prepared_action_write_v1",
    "postgres_http_runtime_approval_decision_write_v1",
    "real_hermes_openclaw_acceptance",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path))


def main() -> int:
    packet = read_json(PACKET_PATH)
    require(packet.get("contract_id") == CONTRACT_ID, f"contract_id must be {CONTRACT_ID}")
    require(packet.get("status") == "delegates_to_commercial_release_evidence_packet", "release packet must delegate to the commercial packet")
    require(packet.get("source_packet") == "docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "source packet path mismatch")
    require(packet.get("source_contract_id") == COMMERCIAL_CONTRACT_ID, "source contract mismatch")
    require(packet.get("verification_command") == "python3 scripts/release_evidence_packet_smoke.py", "verification command mismatch")
    require(packet.get("commercial_verification_command") == "python3 scripts/commercial_release_evidence_packet_smoke.py", "commercial verification command mismatch")
    require(packet.get("release_complete") is False, "release entry point must not claim completion")
    require(REQUIRED_GATE5_COMMANDS <= set(packet.get("gate_5_required_commands") or []), "release packet misses Gate 5 commands")
    require(REQUIRED_GATE5_CONTRACTS <= set(packet.get("gate_5_required_contracts") or []), "release packet misses Gate 5 contracts")
    require("--skip-postgres-if-unavailable" in set(packet.get("must_not_use") or []), "release packet must reject skipped Postgres proof")

    commercial = read_json(COMMERCIAL_PACKET)
    require(commercial.get("contract_id") == COMMERCIAL_CONTRACT_ID, "commercial packet contract mismatch")
    commercial_gate5 = {
        str(gate.get("id")): gate
        for gate in commercial.get("phase_gate_evidence") or []
        if isinstance(gate, dict)
    }.get("gate_5_byoc_enterprise_deployment") or {}
    commercial_commands = set(commercial_gate5.get("required_commands") or [])
    commercial_contracts = set(commercial_gate5.get("required_contracts") or [])
    require(REQUIRED_GATE5_COMMANDS <= commercial_commands, "commercial packet misses Gate 5 commands")
    require(REQUIRED_GATE5_CONTRACTS <= commercial_contracts, "commercial packet misses Gate 5 contracts")
    require(not any("--skip-postgres-if-unavailable" in item for item in commercial_commands), "commercial packet must not skip Postgres proof")

    doc = read_text(PACKET_DOC)
    require(CONTRACT_ID in doc, "release packet doc must name the contract")
    require(COMMERCIAL_CONTRACT_ID in doc, "release packet doc must name the commercial contract")
    for command in REQUIRED_GATE5_COMMANDS:
        require(command in doc, f"release packet doc missing {command}")

    proc = subprocess.run(
        [sys.executable, str(COMMERCIAL_SMOKE)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=60,
        check=False,
    )
    require(proc.returncode == 0, f"commercial packet smoke failed: {proc.stdout}{proc.stderr}")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "source_contract": COMMERCIAL_CONTRACT_ID,
        "gate_5_commands": sorted(REQUIRED_GATE5_COMMANDS),
        "release_complete": False,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
