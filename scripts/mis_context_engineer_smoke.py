#!/usr/bin/env python3
"""Smoke-test the MIS Context Engineer prototype artifacts.

The repository intentionally keeps its Python package dependency-free, so this
script treats PyYAML/jsonschema as optional. YAML parsing falls back to Ruby's
stdlib Psych parser when PyYAML is not installed on the local machine.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills" / "mis-context-engineer"
SCHEMA_DIR = SKILL_ROOT / "schemas"
EVAL_DIR = SKILL_ROOT / "evals"

CONTEXT_SCHEMA = SCHEMA_DIR / "context-manifest.schema.json"
MEMORY_SCHEMA = SCHEMA_DIR / "memory-write-proposal.schema.json"
CASES_YAML = EVAL_DIR / "cases.yaml"

AUTHORITY_CLASSES = {
    "git_fact",
    "mis_execution_fact",
    "approved_project_state",
    "approved_memory",
    "candidate_memory",
    "external_research",
    "chat_source",
}
RELATIONSHIPS = {
    "new",
    "duplicate_of",
    "updates",
    "supersedes",
    "conflicts_with",
    "derived_from",
}
REASON_CODES = {
    "candidate_not_authority",
    "scope_denied",
    "superseded",
    "historical_mismatch",
    "token_budget",
    "other",
}
SHA_RE = re.compile(r"^[a-f0-9]{40}$")


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} must parse to a JSON object")
    return payload


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-not-found]

        with path.open("r", encoding="utf-8") as handle:
            payload = yaml.safe_load(handle)
    except ModuleNotFoundError:
        ruby = shutil.which("ruby")
        if not ruby:
            raise AssertionError("YAML validation needs PyYAML or system Ruby") from None
        script = (
            "require 'yaml'; require 'json'; "
            f"puts JSON.generate(YAML.load_file({json.dumps(str(path))}))"
        )
        proc = subprocess.run(
            [ruby, "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            raise AssertionError(f"Ruby YAML parser failed: {proc.stderr.strip() or proc.stdout.strip()}")
        payload = json.loads(proc.stdout)
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} must parse to a YAML mapping")
    return payload


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def git_output(args: list[str]) -> str | None:
    proc = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def schema_required(schema: dict[str, Any], required: set[str], title: str) -> None:
    require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", f"{title} schema draft mismatch")
    require(schema.get("type") == "object", f"{title} schema must describe an object")
    require(schema.get("additionalProperties") is False, f"{title} schema should reject unknown top-level fields")
    actual = set(schema.get("required") or [])
    missing = sorted(required - actual)
    require(not missing, f"{title} schema missing required fields: {missing}")


def optional_jsonschema_validate(schema: dict[str, Any], instance: dict[str, Any], title: str) -> str:
    try:
        import jsonschema  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return "skipped"
    jsonschema.Draft202012Validator.check_schema(schema)
    jsonschema.Draft202012Validator(schema).validate(instance)
    return "validated"


def sample_context_manifest() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "manifest_id": "ctx_smoke",
        "created_at": "2026-06-22T00:00:00Z",
        "objective": "Smoke-test the context manifest schema.",
        "mode": "candidate_writeback",
        "project_context": {
            "repository": "geogejoy107-jpg/agentops-mis-mvp",
            "branch": "codex/mis-context-engineer-v0",
            "commit": "ab3b151e970dfdf08fa3442e632429e8ae456e85",
            "workspace_id": "local-demo",
            "project_id": "agentops-mis",
            "task_id": None,
            "agent_id": "codex",
        },
        "policy": {
            "authority_order": [
                "git_fact",
                "mis_execution_fact",
                "approved_project_state",
                "approved_memory",
                "candidate_memory",
                "external_research",
                "chat_source",
            ],
            "token_budget": 4000,
            "writeback_mode": "candidate_only",
            "semantic_retrieval": False,
            "historical_as_of": None,
        },
        "included_items": [],
        "excluded_items": [],
        "conflicts": [],
        "unresolved_questions": [],
        "budget": {"limit": 4000, "reserved": 800, "used": 800, "overflow": False},
        "safety": {
            "scope_gate_applied": True,
            "redaction_applied": True,
            "raw_prompts_omitted": True,
            "raw_responses_omitted": True,
            "secrets_omitted": True,
            "chain_of_thought_omitted": True,
        },
        "evidence_refs": ["scripts/mis_context_engineer_smoke.py"],
        "output_hash": "0" * 64,
    }


def sample_memory_proposal() -> dict[str, Any]:
    return {
        "schema_version": "0.1",
        "proposal_id": "mwp_smoke",
        "created_at": "2026-06-22T00:00:00Z",
        "workspace_id": "local-demo",
        "project_id": "agentops-mis",
        "task_id": None,
        "agent_id": "codex",
        "status": "candidate",
        "canonical": False,
        "scope": "project",
        "memory_type": "agent_lesson",
        "proposed_text": "Context Engineer memory writes remain candidate-only until human review.",
        "source_type": "github",
        "source_refs": [".agents/skills/mis-context-engineer/SKILL.md"],
        "source_versions": ["ab3b151e970dfdf08fa3442e632429e8ae456e85"],
        "relationship": {"type": "derived_from", "target_memory_ids": [], "reason": "Smoke-test proposal."},
        "confidence": 0.8,
        "access_tags": ["local-demo", "project-owner"],
        "valid_from": None,
        "valid_to": None,
        "ttl_review_due_at": None,
        "review": {
            "required": True,
            "status": "pending",
            "eligible_for_auto_promotion": False,
            "required_reviewer_role": "human",
        },
        "redaction": {"applied": True, "redacted_fields": [], "raw_content_retained": False},
        "safety": {
            "scope_checked": True,
            "source_verified": True,
            "duplicate_checked": True,
            "conflict_checked": True,
            "raw_prompts_omitted": True,
            "raw_responses_omitted": True,
            "secrets_omitted": True,
            "chain_of_thought_omitted": True,
        },
    }


def validate_cases(payload: dict[str, Any]) -> dict[str, Any]:
    require(payload.get("schema_version") == "0.1", "cases.yaml schema_version must be 0.1")
    require(payload.get("suite") == "mis-context-engineer-v0", "cases.yaml suite mismatch")
    defaults = payload.get("defaults")
    require(isinstance(defaults, dict), "cases.yaml defaults must be a mapping")
    require(defaults.get("repository") == "geogejoy107-jpg/agentops-mis-mvp", "default repository mismatch")
    require(isinstance(defaults.get("token_budget"), int), "default token_budget must be an integer")
    default_branch = defaults.get("branch")
    default_commit = defaults.get("commit")
    require(isinstance(default_branch, str) and default_branch, "default branch must be set")
    require(isinstance(default_commit, str) and SHA_RE.match(default_commit), "default commit must be a full SHA")
    require(git_output(["cat-file", "-t", default_commit]) == "commit", "default commit must exist locally")
    remote_head = git_output(["rev-parse", f"refs/remotes/origin/{default_branch}"])
    if remote_head:
        require(
            default_commit == remote_head,
            f"default commit {default_commit} does not match origin/{default_branch} {remote_head}",
        )

    metrics = payload.get("metrics")
    require(isinstance(metrics, list) and len(metrics) >= 8, "metrics must list the v0 evaluation metrics")
    require("manifest_valid" in metrics, "metrics must include manifest_valid")

    cases = payload.get("cases")
    require(isinstance(cases, list) and len(cases) == 10, "cases.yaml must contain exactly 10 v0 cases")
    ids: set[str] = set()
    reason_counts: dict[str, int] = {}
    relationship_cases = 0
    for index, case in enumerate(cases, start=1):
        require(isinstance(case, dict), f"case #{index} must be a mapping")
        case_id = case.get("id")
        require(isinstance(case_id, str) and case_id, f"case #{index} missing id")
        require(case_id not in ids, f"duplicate case id: {case_id}")
        ids.add(case_id)
        require(isinstance(case.get("objective"), str) and case["objective"], f"{case_id} missing objective")
        fixtures = case.get("fixtures")
        require(isinstance(fixtures, list) and fixtures, f"{case_id} must define fixtures")
        expect = case.get("expect")
        require(isinstance(expect, dict) and expect, f"{case_id} must define expect")

        for fixture in fixtures:
            require(isinstance(fixture, dict), f"{case_id} fixture must be a mapping")
            require(isinstance(fixture.get("source_ref"), str), f"{case_id} fixture missing source_ref")
            authority = fixture.get("authority_class")
            require(authority in AUTHORITY_CLASSES, f"{case_id} has unknown authority_class: {authority}")
            require(isinstance(fixture.get("workspace_id"), str), f"{case_id} fixture missing workspace_id")
            require("version" in fixture, f"{case_id} fixture missing version")

        for exclusion in expect.get("excluded", []) or []:
            require(isinstance(exclusion, dict), f"{case_id} expected exclusion must be a mapping")
            reason = exclusion.get("reason_code")
            require(reason in REASON_CODES, f"{case_id} has unknown reason_code: {reason}")
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

        relationship = expect.get("relationship")
        if relationship is not None:
            require(relationship in RELATIONSHIPS, f"{case_id} has unknown relationship: {relationship}")
            relationship_cases += 1

    require("secret_redaction" in ids, "secret_redaction case is required")
    require("cross_workspace_leakage" in ids, "cross_workspace_leakage case is required")
    require("missing_git_commit_blocks_code_claims" in ids, "missing_git_commit_blocks_code_claims case is required")
    require(relationship_cases >= 1, "at least one case must exercise relationship classification")
    return {
        "case_count": len(cases),
        "metric_count": len(metrics),
        "reason_counts": reason_counts,
    }


def main() -> int:
    failures: list[str] = []
    result: dict[str, Any] = {
        "ok": False,
        "paths": {
            "skill_root": str(SKILL_ROOT.relative_to(ROOT)),
            "context_schema": str(CONTEXT_SCHEMA.relative_to(ROOT)),
            "memory_schema": str(MEMORY_SCHEMA.relative_to(ROOT)),
            "cases": str(CASES_YAML.relative_to(ROOT)),
        },
    }
    try:
        for path in [SKILL_ROOT / "SKILL.md", CONTEXT_SCHEMA, MEMORY_SCHEMA, CASES_YAML]:
            require(path.exists(), f"missing required artifact: {path.relative_to(ROOT)}")

        context_schema = load_json(CONTEXT_SCHEMA)
        memory_schema = load_json(MEMORY_SCHEMA)
        cases = load_yaml(CASES_YAML)

        schema_required(
            context_schema,
            {
                "schema_version",
                "manifest_id",
                "created_at",
                "objective",
                "mode",
                "project_context",
                "policy",
                "included_items",
                "excluded_items",
                "conflicts",
                "unresolved_questions",
                "budget",
                "safety",
                "evidence_refs",
                "output_hash",
            },
            "context manifest",
        )
        schema_required(
            memory_schema,
            {
                "schema_version",
                "proposal_id",
                "created_at",
                "workspace_id",
                "status",
                "canonical",
                "relationship",
                "review",
                "redaction",
                "safety",
            },
            "memory write proposal",
        )
        case_summary = validate_cases(cases)
        result["case_summary"] = case_summary
        result["optional_jsonschema"] = {
            "context_manifest": optional_jsonschema_validate(
                context_schema,
                sample_context_manifest(),
                "context manifest",
            ),
            "memory_write_proposal": optional_jsonschema_validate(
                memory_schema,
                sample_memory_proposal(),
                "memory write proposal",
            ),
        }
    except Exception as exc:
        failures.append(str(exc))

    result["ok"] = not failures
    result["failures"] = failures
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
