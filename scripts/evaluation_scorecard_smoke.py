#!/usr/bin/env python3
"""Validate the AgentOps MIS Evaluation Scorecard v0 docs.

This smoke keeps the scorecard reviewable as a governed measurement contract
without requiring live ledger, UAT, or economic pilot data.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCORECARD = ROOT / "docs" / "evaluation" / "EVALUATION_SCORECARD_V0.md"
DICTIONARY = ROOT / "docs" / "evaluation" / "EVALUATION_METRIC_DICTIONARY_V0.yaml"
BASELINE = ROOT / "docs" / "evaluation" / "EVALUATION_BASELINE_2026-06-22.md"
HANDOFF = ROOT / "docs" / "project" / "EVALUATION_SCORECARD_HANDOFF.md"
PLAN = ROOT / "docs" / "agent_plans" / "2026-06-22-evaluation-scorecard-v0.md"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-not-found]

        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except ModuleNotFoundError:
        ruby = shutil.which("ruby")
        require(bool(ruby), "YAML validation needs PyYAML or system Ruby")
        script = (
            "require 'yaml'; require 'json'; "
            f"puts JSON.generate(YAML.load_file({json.dumps(str(path))}))"
        )
        proc = subprocess.run(
            [str(ruby), "-e", script],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        require(proc.returncode == 0, proc.stderr.strip() or proc.stdout.strip())
        payload = json.loads(proc.stdout)
    require(isinstance(payload, dict), f"{path.relative_to(ROOT)} must parse as a YAML mapping")
    return payload


def main() -> None:
    required_files = [SCORECARD, DICTIONARY, BASELINE, HANDOFF, PLAN]
    for path in required_files:
        require(path.is_file(), f"missing required scorecard file: {path.relative_to(ROOT)}")

    scorecard = SCORECARD.read_text(encoding="utf-8")
    baseline = BASELINE.read_text(encoding="utf-8")
    handoff = HANDOFF.read_text(encoding="utf-8")
    dictionary = load_yaml(DICTIONARY)

    require(dictionary.get("schema_version") == "0.1", "metric dictionary schema_version must be 0.1")
    require(dictionary.get("scorecard_id") == "agentops-mis-evaluation-scorecard-v0", "scorecard_id mismatch")
    require(dictionary.get("canonical") is False, "scorecard v0 must remain candidate/non-canonical")

    metrics = dictionary.get("metrics")
    require(isinstance(metrics, list) and len(metrics) >= 20, "metric dictionary must define at least 20 metrics")
    metric_ids: list[str] = []
    categories: set[str] = set()
    unknown_states = 0
    safety_guardrails = 0
    for index, metric in enumerate(metrics):
        require(isinstance(metric, dict), f"metrics[{index}] must be a mapping")
        metric_id = metric.get("id")
        require(isinstance(metric_id, str) and metric_id, f"metrics[{index}] missing id")
        metric_ids.append(metric_id)
        category = metric.get("category")
        require(isinstance(category, str) and category, f"{metric_id} missing category")
        categories.add(category)
        require(metric.get("authority"), f"{metric_id} missing authority")
        require(metric.get("evidence_level_required"), f"{metric_id} missing evidence level")
        current_state = str(metric.get("current_state") or "")
        if "unknown" in current_state:
            unknown_states += 1
        if metric_id.startswith("SAFE-"):
            safety_guardrails += 1
            require(metric.get("target") == 0, f"{metric_id} guardrail target must be zero")

    require(len(metric_ids) == len(set(metric_ids)), "metric ids must be unique")
    require({"workflow", "safety", "technical", "governance", "knowledge"} <= categories, "missing core metric category")
    require(unknown_states >= 5, "scorecard must preserve Unknown for unmeasured live/UAT/economic values")
    require(safety_guardrails >= 5, "scorecard must include zero-tolerance safety guardrails")

    required_phrases = [
        "Safety guardrails are not averaged",
        "Unknown stays Unknown",
        "Privacy precedes analysis",
        "Governed Task Closure Rate",
        "raw prompts, responses",
        "Raw private prompt/response/customer body",
    ]
    for phrase in required_phrases:
        require(phrase in scorecard, f"scorecard missing phrase: {phrase}")

    require("Unknown" in baseline, "baseline must preserve unknown values instead of inferring them")
    require("Lane A" in handoff, "handoff must identify the Lane A deliverable")
    require("read-only aggregate GTCR" in handoff, "handoff must name the next live-ledger baseline action")

    print(
        json.dumps(
            {
                "ok": True,
                "operation": "evaluation_scorecard_smoke",
                "metric_count": len(metrics),
                "category_count": len(categories),
                "unknown_state_count": unknown_states,
                "safety_guardrail_count": safety_guardrails,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
