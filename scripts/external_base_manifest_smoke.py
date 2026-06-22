#!/usr/bin/env python3
"""Validate an AgentOps MIS external-base manifest without network access."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REQUIRED_TOP_LEVEL = {
    "schema_version",
    "base_id",
    "provider",
    "display_name",
    "project",
    "resource",
    "authority_roles",
    "capabilities",
    "approval_policy",
    "governance",
    "field_map",
    "ingestion",
    "export",
    "implementation",
}

FORBIDDEN_KEY_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "credential",
    "private_key",
    "api_key",
)


def walk_keys(value: Any, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            keys.append(path)
            keys.extend(walk_keys(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            keys.extend(walk_keys(child, f"{prefix}[{index}]"))
    return keys


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_manifest(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(REQUIRED_TOP_LEVEL - set(data))
    require(not missing, f"missing top-level keys: {missing}", errors)
    require(
        data.get("schema_version") == "agentops.external_base.v0",
        "unexpected schema_version",
        errors,
    )
    require(
        str(data.get("base_id", "")).startswith("base_"),
        "base_id must start with 'base_'",
        errors,
    )
    require(
        data.get("provider") in {"notion", "github", "chatgpt_project", "agentops_mis", "local"},
        "unsupported provider",
        errors,
    )

    capabilities = data.get("capabilities")
    require(isinstance(capabilities, dict), "capabilities must be an object", errors)
    if isinstance(capabilities, dict):
        expected = {"read", "search", "write", "sync", "webhook"}
        require(expected <= set(capabilities), "capabilities is missing required flags", errors)
        for key in expected:
            require(isinstance(capabilities.get(key), bool), f"capabilities.{key} must be boolean", errors)

    policy = data.get("approval_policy")
    require(isinstance(policy, dict), "approval_policy must be an object", errors)
    if isinstance(policy, dict):
        require(policy.get("write") in {"confirm", "disabled"}, "writes must be confirmed or disabled", errors)
        require(policy.get("destructive") == "blocked", "destructive actions must be blocked in v0", errors)

    governance = data.get("governance")
    require(isinstance(governance, dict), "governance must be an object", errors)
    if isinstance(governance, dict):
        canonical = set(governance.get("canonical_statuses", []))
        candidates = set(governance.get("candidate_statuses", []))
        require(bool(canonical), "canonical_statuses cannot be empty", errors)
        require(bool(candidates), "candidate_statuses cannot be empty", errors)
        require(canonical.isdisjoint(candidates), "canonical and candidate statuses must be disjoint", errors)
        require(governance.get("raw_prompts_allowed") is False, "raw prompts must be disabled", errors)
        require(governance.get("raw_transcripts_allowed") is False, "raw transcripts must be disabled", errors)
        require(governance.get("credentials_allowed") is False, "credentials must be disabled", errors)

    ingestion = data.get("ingestion")
    require(isinstance(ingestion, dict), "ingestion must be an object", errors)
    if isinstance(ingestion, dict):
        require(
            ingestion.get("candidate_records_are_authority") is False,
            "candidate records cannot be authority",
            errors,
        )
        require(ingestion.get("requires_provenance") is True, "ingestion must require provenance", errors)
        require(ingestion.get("requires_workspace_acl") is True, "ingestion must require workspace ACL", errors)

    implementation = data.get("implementation")
    require(isinstance(implementation, dict), "implementation must be an object", errors)
    if isinstance(implementation, dict):
        require(implementation.get("live_sync_enabled") is False, "v0 must not enable live sync", errors)

    suspicious = [
        key
        for key in walk_keys(data)
        if any(fragment in key.lower() for fragment in FORBIDDEN_KEY_FRAGMENTS)
    ]
    require(not suspicious, f"credential-like keys are forbidden: {suspicious}", errors)
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "manifest",
        nargs="?",
        default="config/external_bases/notion_project_ledger.json",
        help="Path to the external-base manifest.",
    )
    args = parser.parse_args()
    path = Path(args.manifest)
    if not path.exists():
        print(json.dumps({"ok": False, "error": "manifest_not_found", "path": str(path)}))
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": "manifest_unreadable", "detail": str(exc)}))
        return 1
    if not isinstance(data, dict):
        print(json.dumps({"ok": False, "error": "manifest_must_be_object"}))
        return 1
    errors = validate_manifest(data)
    result = {
        "ok": not errors,
        "schema_version": data.get("schema_version"),
        "base_id": data.get("base_id"),
        "provider": data.get("provider"),
        "live_sync_enabled": data.get("implementation", {}).get("live_sync_enabled"),
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
