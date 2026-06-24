#!/usr/bin/env python3
"""Smoke-test the MIS Context Engineer v0.2 package."""
from __future__ import annotations

import json
import py_compile
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "mis-context-engineer"
CLI = ROOT / "scripts" / "mis_context_engineer_cli.py"

REQUIRED = [
    SKILL / "SKILL.md",
    SKILL / "README.md",
    SKILL / "CHANGELOG.md",
    SKILL / "THIRD_PARTY_NOTICES.md",
    SKILL / "references" / "SOTA_MATRIX.md",
    SKILL / "references" / "LOOP_HARNESS_ENGINEERING.md",
    SKILL / "references" / "PERFORMANCE_TOKEN_EFFICIENCY.md",
    SKILL / "schemas" / "context-manifest.schema.json",
    SKILL / "schemas" / "memory-write-proposal.schema.json",
    SKILL / "schemas" / "harness-profile.schema.json",
    SKILL / "schemas" / "loop-policy.schema.json",
    SKILL / "examples" / "default-harness-profile.json",
    SKILL / "examples" / "default-loop-policy.json",
    SKILL / "examples" / "sample-request.json",
    SKILL / "evals" / "cases.yaml",
    SKILL / "evals" / "performance_cases.json",
    CLI,
]


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"{path} must contain a JSON object")
    return value


def run(*args: str) -> dict[str, Any]:
    proc = subprocess.run([sys.executable, str(CLI), *args], cwd=ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise AssertionError(proc.stderr.strip() or proc.stdout.strip())
    value = json.loads(proc.stdout)
    if not isinstance(value, dict):
        raise AssertionError("CLI output must be a JSON object")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    failures: list[str] = []
    result: dict[str, Any] = {"ok": False, "version": "0.2.0"}
    try:
        for path in REQUIRED:
            require(path.exists(), f"missing {path.relative_to(ROOT)}")

        py_compile.compile(str(CLI), doraise=True)
        py_compile.compile(__file__, doraise=True)

        schemas = {
            name: load_json(SKILL / "schemas" / name)
            for name in [
                "context-manifest.schema.json",
                "memory-write-proposal.schema.json",
                "harness-profile.schema.json",
                "loop-policy.schema.json",
            ]
        }
        require(schemas["context-manifest.schema.json"].get("type") == "object", "context schema")
        require(schemas["harness-profile.schema.json"].get("properties", {}).get("schema_version", {}).get("const") == "0.2", "harness schema version")
        require(schemas["loop-policy.schema.json"].get("properties", {}).get("schema_version", {}).get("const") == "0.2", "loop schema version")

        harness = load_json(SKILL / "examples" / "default-harness-profile.json")
        loop = load_json(SKILL / "examples" / "default-loop-policy.json")
        request = load_json(SKILL / "examples" / "sample-request.json")
        require(harness.get("schema_version") == "0.2", "harness example version")
        require(loop.get("schema_version") == "0.2", "loop example version")
        require(int(loop.get("max_iterations") or 0) <= 10, "loop must be bounded")
        require(int((harness.get("tokens") or {}).get("total_budget") or 0) > int((harness.get("tokens") or {}).get("reserved_output") or 0), "token budget")
        require(request.get("project_context", {}).get("commit") not in {None, "", "Unknown"}, "sample request Git context")

        with tempfile.TemporaryDirectory(prefix="mis-context-engineer-") as tmp:
            manifest_path = Path(tmp) / "manifest.json"
            subprocess.run([
                sys.executable,
                str(CLI),
                "build",
                "--request",
                str(SKILL / "examples" / "sample-request.json"),
                "--output",
                str(manifest_path),
            ], cwd=ROOT, check=True, capture_output=True, text=True)
            manifest = load_json(manifest_path)
            validation = run("validate", "--manifest", str(manifest_path))
            require(validation.get("ok") is True, f"manifest validation failed: {validation}")
            budget = manifest.get("budget") or {}
            require(int(budget.get("full_context_tokens") or 0) <= int(budget.get("available_input") or 0), "context exceeds input budget")
            require(len(manifest.get("iterations") or []) <= int((manifest.get("loop") or {}).get("max_iterations") or 0), "loop exceeded policy")
            require((manifest.get("safety") or {}).get("scope_gate_applied") is True, "scope gate evidence missing")

        benchmark = run("benchmark", "--cases", str(SKILL / "evals" / "performance_cases.json"))
        require(benchmark.get("ok") is True, f"benchmark failed: {benchmark}")
        require(int(benchmark.get("case_count") or 0) >= 4, "benchmark case count")
        delta_case = next(item for item in benchmark["results"] if item["id"] == "delta_context_reuse")
        require(int(delta_case["delta_tokens"]) <= int(delta_case["full_tokens"]), "delta context did not reduce tokens")
        deterministic = next(item for item in benchmark["results"] if item["id"] == "deterministic_build")
        require(deterministic["pass"] is True, "deterministic case")

        result.update({
            "required_file_count": len(REQUIRED),
            "schema_count": len(schemas),
            "benchmark_case_count": benchmark["case_count"],
            "benchmark": benchmark,
        })
    except Exception as exc:
        failures.append(str(exc))

    result["ok"] = not failures
    result["failures"] = failures
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
