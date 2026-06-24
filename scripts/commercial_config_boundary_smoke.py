#!/usr/bin/env python3
"""Validate commercial config examples stay safe-by-default and secret-free."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ENTITLEMENTS = ROOT / "config" / "entitlements.example.json"
RETENTION = ROOT / "config" / "retention-controls.example.json"

SECRET_PATTERNS = [
    re.compile(r"Authorization:", re.IGNORECASE),
    re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"agtok_[A-Za-z0-9_]+"),
    re.compile(r"agtsess_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"ntn_[A-Za-z0-9]{8,}"),
    re.compile(r"AGENTOPS_(API|ADMIN)_KEY=", re.IGNORECASE),
]


def require(condition: bool, message: str, failures: list[str]) -> None:
    if not condition:
        failures.append(message)


def load_json(path: Path, failures: list[str]) -> dict[str, Any]:
    require(path.is_file(), f"missing config: {path.relative_to(ROOT)}", failures)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        failures.append(f"invalid json in {path.relative_to(ROOT)}: {exc}")
        return {}
    require(isinstance(payload, dict), f"config must be object: {path.relative_to(ROOT)}", failures)
    return payload


def scan_secret_like_text(paths: list[Path], failures: list[str]) -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in paths if path.exists())
    hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(combined)]
    require(not hits, f"secret-like marker found in commercial config examples: {hits}", failures)


def validate_entitlements(payload: dict[str, Any], failures: list[str]) -> None:
    require(payload.get("schema_version") == "agentops-entitlements/v0", "entitlement schema version mismatch", failures)
    require(payload.get("edition") == "free_local", "example entitlements must default to free_local", failures)
    billing = payload.get("billing") if isinstance(payload.get("billing"), dict) else {}
    require(billing.get("provider") == "none", "example billing provider must be none", failures)
    for key in ("billing_call_enabled", "checkout_enabled", "metering_export_enabled"):
        require(billing.get(key) is False, f"billing.{key} must be false by default", failures)
    capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else {}
    for key in ("sqlite_ledger", "local_worker_loop", "agent_gateway", "pixel_office", "notion_dry_run_export"):
        require(capabilities.get(key) is True, f"local capability should stay enabled: {key}", failures)
    for key in (
        "confirmed_external_export",
        "report_templates",
        "postgres_adapter",
        "sso_hooks",
        "multi_workspace",
        "hosted_mode",
    ):
        require(capabilities.get(key) is False, f"commercial/shared capability must default false: {key}", failures)
    require(isinstance(payload.get("overrides"), dict), "overrides must be an object", failures)


def validate_retention(payload: dict[str, Any], failures: list[str]) -> None:
    require(payload.get("schema_version") == "agentops-retention-controls/v0", "retention schema version mismatch", failures)
    windows = payload.get("retention_windows") if isinstance(payload.get("retention_windows"), dict) else {}
    free_days = windows.get("free_local_days")
    pro_days = windows.get("pro_workspace_days")
    max_days = windows.get("max_retention_days")
    require(isinstance(free_days, int) and 1 <= free_days <= 90, f"free_local_days must be bounded local retention: {free_days}", failures)
    require(isinstance(pro_days, int) and pro_days >= free_days, "pro retention must be >= free retention", failures)
    require(isinstance(max_days, int) and max_days >= pro_days, "max retention must be >= pro retention", failures)
    cleanup = payload.get("cleanup_policy") if isinstance(payload.get("cleanup_policy"), dict) else {}
    require(cleanup.get("approval_required") is True, "cleanup must require approval", failures)
    require(cleanup.get("legal_hold_required_before_cleanup") is True, "cleanup must check legal hold", failures)
    for key in ("cleanup_execution_enabled", "cleanup_endpoint_exposed", "delete_supported"):
        require(cleanup.get(key) is False, f"cleanup.{key} must be false by default", failures)
    registry = payload.get("legal_hold_registry") if isinstance(payload.get("legal_hold_registry"), dict) else {}
    require(registry.get("configured") is True, "legal hold registry must be represented", failures)
    require(registry.get("example_only") is True, "legal hold registry example must be marked example_only", failures)
    holds = registry.get("legal_holds") if isinstance(registry.get("legal_holds"), list) else []
    require(bool(holds), "at least one legal hold example should be present", failures)
    for hold in holds:
        if not isinstance(hold, dict):
            failures.append("legal hold must be object")
            continue
        require(str(hold.get("hold_id", "")).startswith("hold_"), f"legal hold id should be explicit: {hold}", failures)
        require(hold.get("status") in {"active", "released", "expired"}, f"legal hold status invalid: {hold}", failures)
        require(hold.get("reason_code"), f"legal hold reason missing: {hold}", failures)


def main() -> int:
    failures: list[str] = []
    entitlements = load_json(ENTITLEMENTS, failures)
    retention = load_json(RETENTION, failures)
    validate_entitlements(entitlements, failures)
    validate_retention(retention, failures)
    scan_secret_like_text([ENTITLEMENTS, RETENTION], failures)
    output = {
        "ok": not failures,
        "operation": "commercial_config_boundary_smoke",
        "configs": [
            str(ENTITLEMENTS.relative_to(ROOT)),
            str(RETENTION.relative_to(ROOT)),
        ],
        "contract": "Commercial config examples are safe-by-default: free local, no billing call, no hosted mode, no destructive cleanup, and no secret material.",
        "safety": {
            "read_only": True,
            "billing_call_performed": False,
            "cleanup_execution_enabled": False,
            "live_execution_performed": False,
            "token_omitted": True,
        },
        "failures": failures,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
