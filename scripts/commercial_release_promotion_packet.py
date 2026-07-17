#!/usr/bin/env python3
"""Build the operator-facing commercial release promotion packet."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from commercial_evidence_receipts import build_payload as build_receipts_payload
from commercial_release_promotion_preflight import build_payload as build_preflight_payload


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "commercial_release_promotion_packet_v1"
PACKET_PATH = ROOT / "docs" / "COMMERCIAL_RELEASE_PROMOTION_PACKET.json"
REQUIRED_RUNTIME_CHECKS = {
    "Agent Gateway CLI smoke": "agent_gateway_run_id",
    "POST /api/integrations/openclaw/probe live": "openclaw_run_id",
    "POST /api/integrations/hermes/run-task live": "hermes_run_id",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_json(path: Path) -> dict[str, Any]:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return json.loads(path.read_text(encoding="utf-8"))


def git_head() -> str:
    import subprocess

    proc = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    return (proc.stdout or proc.stderr).strip()


def has_forbidden_payload_text(raw: str) -> bool:
    lowered = raw.lower()
    forbidden = [
        '"raw_prompt"',
        '"raw_prompts"',
        '"raw_response"',
        '"raw_responses"',
        '"private_transcript"',
        '"private_transcripts"',
        '"token_value"',
        '"token_values"',
        "openai_api_key",
        "anthropic_api_key",
        "notion_token",
        "dify_api_key",
    ]
    return any(marker in lowered for marker in forbidden)


def normalize_runtime_evidence(runtime: dict[str, Any], *, source: str, verified_head: str | None = None, current_session: bool = False) -> dict[str, Any]:
    normalized = {
        "source": source,
        "checked": True,
        "current_session": bool(current_session),
        "verified_head": verified_head or runtime.get("verified_head"),
        "live_openclaw": bool(runtime.get("live_openclaw")),
        "live_hermes": bool(runtime.get("live_hermes")),
        "require_hermes_api": bool(runtime.get("require_hermes_api")),
        "agent_gateway_run_id": str(runtime.get("agent_gateway_run_id") or ""),
        "openclaw_run_id": str(runtime.get("openclaw_run_id") or ""),
        "hermes_run_id": str(runtime.get("hermes_run_id") or ""),
        "raw_prompt_omitted": runtime.get("raw_prompt_omitted") is True,
        "raw_response_omitted": runtime.get("raw_response_omitted") is True,
        "private_transcripts_omitted": runtime.get("private_transcripts_omitted", True) is True,
        "token_values_omitted": runtime.get("token_values_omitted") is True,
    }
    normalized["real_runtime_acceptance_verified"] = bool(
        normalized["live_openclaw"]
        and normalized["live_hermes"]
        and normalized["require_hermes_api"]
        and normalized["agent_gateway_run_id"].startswith("run_gw_")
        and normalized["openclaw_run_id"].startswith("run_api_integrations_openclaw_probe_")
        and normalized["hermes_run_id"].startswith("run_api_integrations_hermes_run_task_")
        and normalized["raw_prompt_omitted"]
        and normalized["raw_response_omitted"]
        and normalized["private_transcripts_omitted"]
        and normalized["token_values_omitted"]
    )
    return normalized


def runtime_from_receipts(receipts: dict[str, Any]) -> dict[str, Any]:
    evidence = receipts.get("promotion_evidence") or {}
    runtime = evidence.get("real_runtime_acceptance") or {}
    if not runtime:
        return {
            "source": "docs/COMMERCIAL_EVIDENCE_RECEIPTS.json",
            "checked": False,
            "current_session": False,
            "real_runtime_acceptance_verified": False,
            "status": "real_runtime_evidence_missing",
        }
    return normalize_runtime_evidence(
        runtime,
        source="docs/COMMERCIAL_EVIDENCE_RECEIPTS.json#promotion_evidence.real_runtime_acceptance",
        verified_head=str(evidence.get("verified_head") or ""),
        current_session=False,
    )


def runtime_from_acceptance_json(path_value: str) -> dict[str, Any]:
    if path_value == "-":
        raw = sys.stdin.read()
        source = "stdin:local_runtime_acceptance_json"
    else:
        path = Path(path_value).expanduser()
        raw = path.read_text(encoding="utf-8")
        source = str(path)
    payload = json.loads(raw)
    require(payload.get("ok") is True, "runtime acceptance JSON did not pass")
    require(payload.get("live_openclaw") is True, "runtime acceptance JSON did not run live OpenClaw")
    require(payload.get("live_hermes") is True, "runtime acceptance JSON did not run live Hermes")
    require(payload.get("require_hermes_api") is True, "runtime acceptance JSON did not require Hermes API")
    require(not has_forbidden_payload_text(raw), "runtime acceptance JSON contains forbidden raw/token material")

    runtime: dict[str, Any] = {
        "live_openclaw": True,
        "live_hermes": True,
        "require_hermes_api": True,
        "raw_prompt_omitted": True,
        "raw_response_omitted": True,
        "private_transcripts_omitted": True,
        "token_values_omitted": True,
    }
    checks = payload.get("checks") or []
    by_name = {str(item.get("name")): item for item in checks if isinstance(item, dict)}
    for check_name, field in REQUIRED_RUNTIME_CHECKS.items():
        item = by_name.get(check_name) or {}
        require(item.get("ok") is True, f"runtime acceptance check failed or missing: {check_name}")
        detail = item.get("detail") or {}
        runtime[field] = str(detail.get("run_id") or "")
    return normalize_runtime_evidence(runtime, source=source, verified_head=git_head(), current_session=True)


def build_packet(
    *,
    include_external_ci: bool = False,
    require_external_ci: bool = False,
    external_ci_run_id: str | None = None,
    runtime_acceptance_json: str | None = None,
    require_current_runtime: bool = False,
) -> dict[str, Any]:
    spec = read_json(PACKET_PATH)
    require(spec.get("contract_id") == CONTRACT_ID, "promotion packet contract mismatch")
    receipts = build_receipts_payload()
    preflight = build_preflight_payload(
        include_external_ci=include_external_ci,
        require_external_ci=require_external_ci,
        external_ci_run_id=external_ci_run_id,
    )
    runtime = runtime_from_acceptance_json(runtime_acceptance_json) if runtime_acceptance_json else runtime_from_receipts(receipts)

    promotion_checks = dict(preflight.get("promotion_checks") or {})
    packet_checks = {
        "all_local_receipts_complete": bool((preflight.get("receipt_state") or {}).get("all_local_receipts_complete")),
        "gates_with_release_grade_receipts_complete": bool(promotion_checks.get("release_grade_receipts_complete")),
        "clean_worktree_verified": bool(promotion_checks.get("clean_worktree_verified")),
        "remote_sync_verified": bool(promotion_checks.get("remote_sync_verified")),
        "exact_head_ci_verified": bool(promotion_checks.get("exact_head_ci_verified")),
        "real_runtime_acceptance_verified": bool(runtime.get("real_runtime_acceptance_verified")),
        "current_runtime_evidence_supplied": bool(runtime.get("current_session")),
        "release_complete": bool(promotion_checks.get("release_complete")),
        "commercial_handoff_allowed": bool(promotion_checks.get("commercial_handoff_allowed")),
        "ready_to_merge": bool(promotion_checks.get("ready_to_merge")),
    }

    blockers = list(preflight.get("blockers") or [])
    if not packet_checks["real_runtime_acceptance_verified"]:
        blockers.append("real_runtime_acceptance_not_verified")
    if require_current_runtime and not packet_checks["current_runtime_evidence_supplied"]:
        blockers.append("current_runtime_evidence_not_supplied")
    blockers = sorted(dict.fromkeys(blockers))
    packet_ready = not blockers

    return {
        "ok": True,
        "contract": CONTRACT_ID,
        "status": "promotion_packet_ready" if packet_ready else "blocked_release_promotion_required",
        "ci_safe": True,
        "read_only": True,
        "current_git_head": git_head(),
        "source_contracts": list(spec.get("source_contracts") or []),
        "source_packets": list(preflight.get("source_packets") or []),
        "promotion_preflight": {
            "contract": preflight.get("contract"),
            "status": preflight.get("status"),
            "promotion_checks": promotion_checks,
            "blockers": list(preflight.get("blockers") or []),
        },
        "receipt_summary": receipts.get("receipt_summary") or {},
        "external_exact_head_ci_evidence": preflight.get("external_exact_head_ci_evidence") or {},
        "real_runtime_acceptance": runtime,
        "packet_checks": packet_checks,
        "packet_requires": dict(spec.get("packet_requires") or {}),
        "blockers": blockers,
        "required_commands": list(spec.get("required_commands") or []),
        "must_not_use": list(spec.get("must_not_use") or []),
        "safety": {
            "read_only": True,
            "ci_safe": True,
            "network_called": bool((preflight.get("external_exact_head_ci_evidence") or {}).get("checked")),
            "live_execution_performed": False,
            "token_omitted": True,
            "raw_prompt_omitted": True,
            "raw_response_omitted": True,
            "private_transcripts_omitted": True,
            "billing_call_performed": False,
            "mutates_receipts": False,
            "allows_handoff_or_merge": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Print commercial release promotion packet.")
    parser.add_argument("--include-external-ci-evidence", action="store_true", help="Query GitHub Actions for current HEAD exact CI evidence.")
    parser.add_argument("--require-external-ci-evidence", action="store_true", help="Fail unless GitHub Actions verifies current HEAD exact CI evidence.")
    parser.add_argument("--external-ci-run-id", help="Specific GitHub Actions run id to verify as exact-head CI evidence.")
    parser.add_argument("--runtime-acceptance-json", help="Path to local_runtime_acceptance.py JSON output, or '-' for stdin.")
    parser.add_argument("--require-current-runtime-evidence", action="store_true", help="Require operator-supplied runtime acceptance JSON for this packet.")
    parser.add_argument("--require-promotion-packet-ready", action="store_true", help="Fail unless every packet requirement is ready.")
    args = parser.parse_args()

    payload = build_packet(
        include_external_ci=bool(args.include_external_ci_evidence or args.require_external_ci_evidence),
        require_external_ci=bool(args.require_external_ci_evidence),
        external_ci_run_id=args.external_ci_run_id,
        runtime_acceptance_json=args.runtime_acceptance_json,
        require_current_runtime=bool(args.require_current_runtime_evidence),
    )
    if args.require_promotion_packet_ready:
        require(payload["status"] == "promotion_packet_ready", f"promotion packet blockers remain: {payload['blockers']}")
        for key, expected in (payload.get("packet_requires") or {}).items():
            require((payload.get("packet_checks") or {}).get(key) is expected, f"packet requirement not met: {key}")

    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
