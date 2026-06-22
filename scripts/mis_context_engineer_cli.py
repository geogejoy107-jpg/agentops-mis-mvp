#!/usr/bin/env python3
"""Dependency-light builder for bounded, token-aware Context Manifests."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills" / "mis-context-engineer"
EXAMPLES = SKILL_ROOT / "examples"

AUTHORITY = {
    "git_fact": 1.00,
    "mis_execution_fact": 0.98,
    "approved_project_state": 0.96,
    "approved_memory": 0.82,
    "candidate_memory": 0.35,
    "external_research": 0.45,
    "chat_source": 0.20,
}
AUTHORITATIVE = {"git_fact", "mis_execution_fact", "approved_project_state", "approved_memory"}
WORD_RE = re.compile(r"[A-Za-z0-9_./:-]+|[\u3400-\u9fff]")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value: Any) -> str:
    text = value if isinstance(value, str) else canonical(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def resolve(value: Any, request_path: Path, fallback: str) -> dict[str, Any]:
    if isinstance(value, dict):
        return json.loads(json.dumps(value))
    name = str(value or fallback)
    for path in (request_path.parent / name, EXAMPLES / name, Path(name)):
        if path.exists():
            return load(path)
    raise FileNotFoundError(name)


def tokens(text: str) -> int:
    if not text:
        return 0
    ascii_chars = sum(1 for ch in text if ord(ch) < 128 and not ch.isspace())
    non_ascii = sum(1 for ch in text if ord(ch) >= 128 and not ch.isspace())
    return max(1, math.ceil(ascii_chars / 4 + non_ascii / 1.5))


def terms(text: str) -> set[str]:
    return {match.group(0).lower() for match in WORD_RE.finditer(text or "")}


def overlap(left: str, right: str) -> float:
    a, b = terms(left), terms(right)
    return len(a & b) / len(a | b) if a and b else 0.0


def is_code_request(objective: str, candidates: list[dict[str, Any]]) -> bool:
    markers = ("code", "commit", "branch", "repo", "test", "代码", "分支", "提交", "测试", "实现")
    return any(marker in objective.lower() for marker in markers) or any(c.get("authority_class") == "git_fact" for c in candidates)


def content_hash(item: dict[str, Any]) -> str:
    return digest({key: item.get(key) for key in (
        "source_ref", "source_version", "summary", "workspace_id", "project_id",
        "task_id", "access_tags", "relationship", "valid_from", "valid_to"
    )})


def gate(item: dict[str, Any], request: dict[str, Any], harness: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ref, version = str(item.get("source_ref") or ""), item.get("source_version")
    if not ref or not version:
        return None, {"source_ref": ref or "unknown", "reason_code": "missing_source", "reason": "Source and version are required."}
    context = request["project_context"]
    if item.get("workspace_id") != context.get("workspace_id"):
        return None, {"source_ref": ref, "reason_code": "scope_denied", "reason": "Workspace scope mismatch."}
    project = context.get("project_id")
    if project and item.get("project_id") and item.get("project_id") != project:
        return None, {"source_ref": ref, "reason_code": "scope_denied", "reason": "Project scope mismatch."}
    allowed_tags = set((harness.get("scope") or {}).get("access_tags") or [])
    item_tags = set(item.get("access_tags") or [])
    if allowed_tags and item_tags and not (allowed_tags & item_tags):
        return None, {"source_ref": ref, "reason_code": "scope_denied", "reason": "Access tags do not intersect."}
    if item.get("authority_class") == "candidate_memory" and (item.get("mandatory") or item.get("tier") == "mandatory_authority"):
        return None, {"source_ref": ref, "reason_code": "candidate_not_authority", "reason": "Candidate memory cannot satisfy mandatory authority."}
    if item.get("superseded"):
        return None, {"source_ref": ref, "reason_code": "superseded", "reason": "A newer source supersedes this item."}
    prepared = dict(item)
    prepared.setdefault("summary", ref)
    prepared.setdefault("tier", "optional_support")
    prepared.setdefault("mandatory", False)
    prepared.setdefault("authority_class", "external_research")
    prepared["content_hash"] = content_hash(prepared)
    prepared["token_estimate"] = int(prepared.get("token_estimate") or tokens(prepared["summary"]))
    return prepared, None


def score(item: dict[str, Any], objective: str) -> float:
    relevance = float(item.get("task_relevance") or overlap(objective, item.get("summary") or ""))
    lexical = float(item.get("lexical_score") or relevance)
    authority = AUTHORITY.get(str(item.get("authority_class")), 0.1)
    evidence = float(item.get("evidence_quality") or 0.5)
    return round(0.45 * relevance + 0.25 * lexical + 0.25 * authority + 0.05 * evidence, 6)


def build(request: dict[str, Any], request_path: Path, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    harness = resolve(request.get("harness_profile"), request_path, "default-harness-profile.json")
    loop = resolve(request.get("loop_policy"), request_path, "default-loop-policy.json")
    objective = str(request.get("objective") or "").strip()
    context = dict(request.get("project_context") or {})
    candidates = list(request.get("candidates") or [])
    excluded: list[dict[str, Any]] = []
    eligible: list[dict[str, Any]] = []

    missing_git = is_code_request(objective, candidates) and not re.fullmatch(r"[a-f0-9]{40}", str(context.get("commit") or ""))
    for item in candidates:
        accepted, rejection = gate(item, request, harness)
        if accepted:
            accepted["score"] = score(accepted, objective)
            eligible.append(accepted)
        elif rejection:
            excluded.append(rejection)

    stable_payload = {
        "harness": harness.get("name"),
        "harness_version": harness.get("version"),
        "authority": harness.get("authority"),
        "scope": harness.get("scope"),
        "schemas": ["context-manifest.schema.json", "memory-write-proposal.schema.json"]
    }
    stable_tokens = tokens(canonical(stable_payload))
    total_budget = int((harness.get("tokens") or {}).get("total_budget") or 8000)
    reserved_output = int((harness.get("tokens") or {}).get("reserved_output") or 1200)
    available = max(0, total_budget - reserved_output)

    prior_hashes = {item.get("content_hash") for item in (previous or {}).get("included_items", [])}
    mandatory = sorted([i for i in eligible if i.get("mandatory")], key=lambda i: (-i["score"], i["source_ref"]))
    optional = sorted([i for i in eligible if not i.get("mandatory")], key=lambda i: (-i["score"] / max(1, i["token_estimate"]), i["source_ref"]))

    included: list[dict[str, Any]] = []
    used = stable_tokens
    insufficient = False
    for item in mandatory:
        if used + item["token_estimate"] > available:
            insufficient = True
            excluded.append({"source_ref": item["source_ref"], "reason_code": "insufficient_budget", "reason": "Mandatory context does not fit."})
        else:
            included.append(item)
            used += item["token_estimate"]
    if not insufficient:
        for item in optional:
            if used + item["token_estimate"] <= available:
                included.append(item)
                used += item["token_estimate"]
            else:
                excluded.append({"source_ref": item["source_ref"], "reason_code": "token_budget", "reason": "Optional item exceeds remaining budget."})

    mandatory_total = len(mandatory)
    mandatory_included = sum(1 for item in included if item.get("mandatory"))
    coverage = mandatory_included / mandatory_total if mandatory_total else 1.0
    authoritative = [item for item in included if item.get("authority_class") in AUTHORITATIVE]
    authority_precision = len(authoritative) / len(included) if included else 1.0
    min_coverage = float(loop.get("minimum_coverage") or 0.85)
    if missing_git:
        stop_reason = "missing_git_context"
    elif insufficient:
        stop_reason = "insufficient_budget"
    elif coverage >= min_coverage:
        stop_reason = "success"
    else:
        stop_reason = "no_more_sources"

    reused = [item["content_hash"] for item in included if item["content_hash"] in prior_hashes]
    full_tokens = used
    delta_tokens = stable_tokens + sum(item["token_estimate"] for item in included if item["content_hash"] not in prior_hashes)
    useful_tokens = sum(item["token_estimate"] for item in included)
    harness_hash, loop_hash = digest(harness), digest(loop)
    checkpoint = digest({"included": [i["content_hash"] for i in included], "excluded": excluded, "stop_reason": stop_reason})
    deterministic = {
        "objective": objective,
        "project_context": context,
        "harness_hash": harness_hash,
        "loop_hash": loop_hash,
        "included": [i["content_hash"] for i in included],
        "excluded": [(i["source_ref"], i["reason_code"]) for i in excluded],
        "checkpoint": checkpoint
    }
    output_hash = digest(deterministic)
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    return {
        "schema_version": "0.2",
        "manifest_id": f"ctx_{output_hash[:20]}",
        "objective": objective,
        "project_context": context,
        "harness": {"name": harness.get("name"), "version": harness.get("version"), "hash": harness_hash},
        "loop": {"name": loop.get("name"), "hash": loop_hash, "max_iterations": int(loop.get("max_iterations") or 1)},
        "included_items": included,
        "reused_items": reused,
        "excluded_items": excluded,
        "unresolved_questions": ["Verify the exact Git commit before making code-state claims."] if missing_git else [],
        "budget": {"limit": total_budget, "reserved_output": reserved_output, "available_input": available, "stable_prefix_tokens": stable_tokens, "full_context_tokens": full_tokens, "delta_context_tokens": delta_tokens, "overflow": full_tokens > available},
        "cache": {"stable_prefix_hash": digest(stable_payload), "eligible_items": len(included), "hit_items": len(reused), "hit_rate": round(len(reused) / len(included), 6) if included else 0.0},
        "performance": {"wall_time_ms": elapsed, "candidate_count": len(candidates), "gated_count": len(excluded), "included_count": len(included), "token_utilization": round(full_tokens / available, 6) if available else 0.0, "token_efficiency": round(useful_tokens / full_tokens, 6) if full_tokens else 0.0},
        "iterations": [{"iteration": 1, "retrieval_mode": "mandatory+lexical", "coverage": round(coverage, 6), "authority_precision": round(authority_precision, 6), "marginal_gain": round(coverage, 6), "latency_ms": elapsed, "checkpoint_hash": checkpoint, "decision": "stop"}],
        "evaluation": {"pass": stop_reason == "success", "coverage": round(coverage, 6), "authority_precision": round(authority_precision, 6), "scope_violations": 0, "stop_reason": stop_reason},
        "safety": {"scope_gate_applied": true, "candidate_writeback_only": true},
        "evidence_refs": [".agents/skills/mis-context-engineer/SKILL.md", "scripts/mis_context_engineer_cli.py"],
        "output_hash": output_hash
    }


def validate(manifest: dict[str, Any]) -> list[str]:
    failures: list[str] = []
    if manifest.get("schema_version") != "0.2": failures.append("schema_version")
    if not re.fullmatch(r"ctx_[A-Za-z0-9._:-]+", str(manifest.get("manifest_id") or "")): failures.append("manifest_id")
    if not re.fullmatch(r"[a-f0-9]{64}", str(manifest.get("output_hash") or "")): failures.append("output_hash")
    budget = manifest.get("budget") or {}
    if budget.get("overflow"): failures.append("budget_overflow")
    if not manifest.get("iterations"): failures.append("iterations")
    return failures


def benchmark(path: Path) -> dict[str, Any]:
    suite = load(path)
    results, all_pass = [], True
    for case in suite.get("cases") or []:
        previous = None
        manifests = []
        started = time.perf_counter()
        for _ in range(int(case.get("repeat") or 1)):
            result = build(case["request"], path, previous)
            manifests.append(result)
            if case.get("chain_previous"): previous = result
        final = manifests[-1]
        failures = validate(final)
        expected = case.get("expect") or {}
        if expected.get("stop_reason") and final["evaluation"]["stop_reason"] != expected["stop_reason"]:
            failures.append("stop_reason")
        if expected.get("reuse_required") and final["cache"]["hit_items"] < 1:
            failures.append("reuse")
        if expected.get("deterministic_hash") and len({m["output_hash"] for m in manifests}) != 1:
            failures.append("determinism")
        passed = not failures
        all_pass = all_pass and passed
        results.append({"id": case["id"], "pass": passed, "failures": failures, "elapsed_ms": round((time.perf_counter() - started) * 1000, 3), "stop_reason": final["evaluation"]["stop_reason"], "full_tokens": final["budget"]["full_context_tokens"], "delta_tokens": final["budget"]["delta_context_tokens"]})
    return {"ok": all_pass, "case_count": len(results), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    build_p = sub.add_parser("build")
    build_p.add_argument("--request", type=Path, required=True)
    build_p.add_argument("--previous", type=Path)
    build_p.add_argument("--output", type=Path)
    validate_p = sub.add_parser("validate")
    validate_p.add_argument("--manifest", type=Path, required=True)
    bench_p = sub.add_parser("benchmark")
    bench_p.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "build":
        request = load(args.request)
        previous = load(args.previous) if args.previous else None
        value = build(request, args.request, previous)
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        if args.output:
            args.output.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
        return 0 if not validate(value) else 1
    if args.command == "validate":
        failures = validate(load(args.manifest))
        print(json.dumps({"ok": not failures, "failures": failures}, indent=2))
        return 0 if not failures else 1
    value = benchmark(args.cases)
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if value["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
