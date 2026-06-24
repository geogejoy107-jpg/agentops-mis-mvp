#!/usr/bin/env python3
"""Build and benchmark bounded, token-aware Context Manifests."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".agents" / "skills" / "mis-context-engineer"
EXAMPLES = SKILL / "examples"
AUTHORITY = {"git_fact": 1.0, "mis_execution_fact": .98, "approved_project_state": .96, "approved_memory": .82, "candidate_memory": .35, "external_research": .45, "chat_source": .2}
AUTHORITATIVE = {"git_fact", "mis_execution_fact", "approved_project_state", "approved_memory"}
WORDS = re.compile(r"[A-Za-z0-9_./:-]+|[\u3400-\u9fff]")


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha(value: Any) -> str:
    return hashlib.sha256((value if isinstance(value, str) else canonical(value)).encode()).hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
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


def estimate_tokens(text: str) -> int:
    ascii_count = sum(1 for ch in text if ord(ch) < 128 and not ch.isspace())
    non_ascii = sum(1 for ch in text if ord(ch) >= 128 and not ch.isspace())
    return max(1, math.ceil(ascii_count / 4 + non_ascii / 1.5)) if text else 0


def overlap(a: str, b: str) -> float:
    left = {m.group(0).lower() for m in WORDS.finditer(a or "")}
    right = {m.group(0).lower() for m in WORDS.finditer(b or "")}
    return len(left & right) / len(left | right) if left and right else 0.0


def item_hash(item: dict[str, Any]) -> str:
    keys = ("source_ref", "source_version", "summary", "workspace_id", "project_id", "task_id", "access_tags", "relationship")
    return sha({key: item.get(key) for key in keys})


def gate(item: dict[str, Any], request: dict[str, Any], harness: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    ref, version = str(item.get("source_ref") or ""), item.get("source_version")
    if not ref or not version:
        return None, {"source_ref": ref or "unknown", "reason_code": "missing_source", "reason": "Source and version are required."}
    context = request["project_context"]
    if item.get("workspace_id") != context.get("workspace_id"):
        return None, {"source_ref": ref, "reason_code": "scope_denied", "reason": "Workspace mismatch."}
    project = context.get("project_id")
    if project and item.get("project_id") and item.get("project_id") != project:
        return None, {"source_ref": ref, "reason_code": "scope_denied", "reason": "Project mismatch."}
    allowed = set((harness.get("scope") or {}).get("access_tags") or [])
    tags = set(item.get("access_tags") or [])
    if allowed and tags and not (allowed & tags):
        return None, {"source_ref": ref, "reason_code": "scope_denied", "reason": "Access tags do not intersect."}
    if item.get("authority_class") == "candidate_memory" and (item.get("mandatory") or item.get("tier") == "mandatory_authority"):
        return None, {"source_ref": ref, "reason_code": "candidate_not_authority", "reason": "Candidate memory cannot satisfy mandatory authority."}
    if item.get("superseded"):
        return None, {"source_ref": ref, "reason_code": "superseded", "reason": "A newer source supersedes this item."}
    value = dict(item)
    value.setdefault("summary", ref)
    value.setdefault("mandatory", False)
    value.setdefault("authority_class", "external_research")
    value["content_hash"] = item_hash(value)
    value["token_estimate"] = int(value.get("token_estimate") or estimate_tokens(value["summary"]))
    relevance = float(value.get("task_relevance") or overlap(str(request.get("objective") or ""), value["summary"]))
    value["score"] = round(.65 * relevance + .3 * AUTHORITY.get(value["authority_class"], .1) + .05 * float(value.get("evidence_quality") or .5), 6)
    return value, None


def build(request: dict[str, Any], request_path: Path, previous: dict[str, Any] | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    harness = resolve(request.get("harness_profile"), request_path, "default-harness-profile.json")
    loop = resolve(request.get("loop_policy"), request_path, "default-loop-policy.json")
    objective = str(request.get("objective") or "")
    context = dict(request.get("project_context") or {})
    candidates = list(request.get("candidates") or [])
    excluded, eligible = [], []
    code_request = any(x in objective.lower() for x in ("code", "commit", "branch", "repo", "test", "代码", "分支", "提交", "测试", "实现")) or any(c.get("authority_class") == "git_fact" for c in candidates)
    missing_git = code_request and not re.fullmatch(r"[a-f0-9]{40}", str(context.get("commit") or ""))
    for item in candidates:
        accepted, rejection = gate(item, request, harness)
        (eligible if accepted else excluded).append(accepted or rejection)

    stable = {"harness": harness.get("name"), "version": harness.get("version"), "authority": harness.get("authority"), "scope": harness.get("scope")}
    stable_tokens = estimate_tokens(canonical(stable))
    token_cfg = harness.get("tokens") or {}
    total = int(token_cfg.get("total_budget") or 8000)
    reserved = int(token_cfg.get("reserved_output") or 1200)
    available = max(0, total - reserved)
    prior = {i.get("content_hash") for i in (previous or {}).get("included_items", [])}
    mandatory = sorted((i for i in eligible if i.get("mandatory")), key=lambda i: (-i["score"], i["source_ref"]))
    optional = sorted((i for i in eligible if not i.get("mandatory")), key=lambda i: (-i["score"] / max(1, i["token_estimate"]), i["source_ref"]))
    included, used, insufficient = [], stable_tokens, False
    for item in mandatory:
        if used + item["token_estimate"] > available:
            insufficient = True
            excluded.append({"source_ref": item["source_ref"], "reason_code": "insufficient_budget", "reason": "Mandatory context does not fit."})
        else:
            included.append(item); used += item["token_estimate"]
    if not insufficient:
        for item in optional:
            if used + item["token_estimate"] <= available:
                included.append(item); used += item["token_estimate"]
            else:
                excluded.append({"source_ref": item["source_ref"], "reason_code": "token_budget", "reason": "Optional item exceeds remaining budget."})

    mandatory_included = sum(bool(i.get("mandatory")) for i in included)
    coverage = mandatory_included / len(mandatory) if mandatory else 1.0
    authority_precision = sum(i.get("authority_class") in AUTHORITATIVE for i in included) / len(included) if included else 1.0
    minimum_coverage = float(loop.get("minimum_coverage") or .85)
    stop = "missing_git_context" if missing_git else "insufficient_budget" if insufficient else "success" if coverage >= minimum_coverage else "no_more_sources"
    reused = [i["content_hash"] for i in included if i["content_hash"] in prior]
    delta = stable_tokens + sum(i["token_estimate"] for i in included if i["content_hash"] not in prior)
    checkpoint = sha({"included": [i["content_hash"] for i in included], "excluded": excluded, "stop": stop})
    harness_hash, loop_hash = sha(harness), sha(loop)
    deterministic = {"objective": objective, "context": context, "harness": harness_hash, "loop": loop_hash, "included": [i["content_hash"] for i in included], "excluded": [(i["source_ref"], i["reason_code"]) for i in excluded], "checkpoint": checkpoint}
    output_hash = sha(deterministic)
    elapsed = round((time.perf_counter() - started) * 1000, 3)
    useful = sum(i["token_estimate"] for i in included)
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
        "budget": {"limit": total, "reserved_output": reserved, "available_input": available, "stable_prefix_tokens": stable_tokens, "full_context_tokens": used, "delta_context_tokens": delta, "overflow": used > available},
        "cache": {"stable_prefix_hash": sha(stable), "eligible_items": len(included), "hit_items": len(reused), "hit_rate": round(len(reused) / len(included), 6) if included else 0.0},
        "performance": {"wall_time_ms": elapsed, "candidate_count": len(candidates), "gated_count": len(excluded), "included_count": len(included), "token_utilization": round(used / available, 6) if available else 0.0, "token_efficiency": round(useful / used, 6) if used else 0.0},
        "iterations": [{"iteration": 1, "retrieval_mode": "mandatory+lexical", "coverage": round(coverage, 6), "authority_precision": round(authority_precision, 6), "marginal_gain": round(coverage, 6), "latency_ms": elapsed, "checkpoint_hash": checkpoint, "decision": "stop"}],
        "evaluation": {"pass": stop == "success", "coverage": round(coverage, 6), "authority_precision": round(authority_precision, 6), "scope_violations": 0, "stop_reason": stop},
        "safety": {"scope_gate_applied": True, "candidate_writeback_only": True},
        "evidence_refs": [".agents/skills/mis-context-engineer/SKILL.md", "scripts/mis_context_engineer_cli.py"],
        "output_hash": output_hash
    }


def validate(manifest: dict[str, Any]) -> list[str]:
    failures = []
    if manifest.get("schema_version") != "0.2": failures.append("schema_version")
    if not re.fullmatch(r"ctx_[A-Za-z0-9._:-]+", str(manifest.get("manifest_id") or "")): failures.append("manifest_id")
    if not re.fullmatch(r"[a-f0-9]{64}", str(manifest.get("output_hash") or "")): failures.append("output_hash")
    if (manifest.get("budget") or {}).get("overflow"): failures.append("budget_overflow")
    if not manifest.get("iterations"): failures.append("iterations")
    return failures


def benchmark(path: Path) -> dict[str, Any]:
    results, ok = [], True
    for case in load(path).get("cases") or []:
        previous, manifests = None, []
        started = time.perf_counter()
        for _ in range(int(case.get("repeat") or 1)):
            result = build(case["request"], path, previous)
            manifests.append(result)
            if case.get("chain_previous"): previous = result
        final, expected = manifests[-1], case.get("expect") or {}
        failures = validate(final)
        if expected.get("stop_reason") and final["evaluation"]["stop_reason"] != expected["stop_reason"]: failures.append("stop_reason")
        if expected.get("reuse_required") and final["cache"]["hit_items"] < 1: failures.append("reuse")
        if expected.get("deterministic_hash") and len({m["output_hash"] for m in manifests}) != 1: failures.append("determinism")
        passed = not failures; ok = ok and passed
        results.append({"id": case["id"], "pass": passed, "failures": failures, "elapsed_ms": round((time.perf_counter() - started) * 1000, 3), "stop_reason": final["evaluation"]["stop_reason"], "full_tokens": final["budget"]["full_context_tokens"], "delta_tokens": final["budget"]["delta_context_tokens"]})
    return {"ok": ok, "case_count": len(results), "results": results}


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("build"); p.add_argument("--request", type=Path, required=True); p.add_argument("--previous", type=Path); p.add_argument("--output", type=Path)
    p = sub.add_parser("validate"); p.add_argument("--manifest", type=Path, required=True)
    p = sub.add_parser("benchmark"); p.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        value = build(load(args.request), args.request, load(args.previous) if args.previous else None)
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        args.output.write_text(text + "\n", encoding="utf-8") if args.output else print(text)
        return 0 if not validate(value) else 1
    if args.command == "validate":
        failures = validate(load(args.manifest)); print(json.dumps({"ok": not failures, "failures": failures}, indent=2)); return 0 if not failures else 1
    value = benchmark(args.cases); print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)); return 0 if value["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
