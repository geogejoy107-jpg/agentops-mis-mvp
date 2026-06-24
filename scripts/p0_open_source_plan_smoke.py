#!/usr/bin/env python3
"""Validate the P0 open-source research and execution plan docs."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs" / "P0_OPEN_SOURCE_RESEARCH_AND_DELIVERY_PLAN.md"
BACKLOG = ROOT / "docs" / "P0_CODEX_EXECUTION_BACKLOG.md"

REQUIRED = {
    PLAN: [
        "AgentOps MIS Control Plane",
        "唯一权威状态",
        "MIS 是 source of truth",
        "Agent Method Block",
        "Shared Knowledge Index",
        "Real Local Runtime",
        "Approval Wall",
        "Local Coding Project Template",
        "Hermes / OpenClaw",
        "SQLite FTS5",
        "prepared action",
        "checkpoint",
        "用 MIS 开发 MIS",
    ],
    BACKLOG: [
        "一项 PR 一个可验收增量",
        "不把 Star-Office-UI 变成权威账本",
        "所有第三方代码复用先检查许可证",
        "perf/baseline-and-safety-tests",
        "feature/agent-method-block",
        "feature/shared-knowledge-index",
        "runtime/durable-local-runner",
        "feature/approval-resume",
        "template/local-coding-project",
        "真实 Agnesfallback/Hermes smoke test",
        "不要为了展示而启动无边界 swarm",
    ],
}

FORBIDDEN_PATTERNS = [
    ("notion_token_literal", re.compile(r"\bntn_[A-Za-z0-9._~+/=-]{8,}\b")),
    ("openai_key_literal", re.compile(r"\bsk-[A-Za-z0-9._~+/=-]{20,}\b")),
    ("github_token_literal", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
]


def main() -> int:
    failures: list[dict[str, str]] = []
    evidence: dict[str, object] = {"docs": {}, "required_terms": {}}

    for path, terms in REQUIRED.items():
        relative = str(path.relative_to(ROOT))
        if not path.exists():
            failures.append({"file": relative, "reason": "missing"})
            continue

        text = path.read_text(encoding="utf-8")
        evidence["docs"][relative] = {
            "bytes": len(text.encode("utf-8")),
            "line_count": len(text.splitlines()),
        }

        matched = [term for term in terms if term in text]
        evidence["required_terms"][relative] = matched
        for term in terms:
            if term not in text:
                failures.append({"file": relative, "reason": "missing_term", "term": term})

        lowered = text.lower()
        if "license" not in lowered and "许可证" not in text:
            failures.append({"file": relative, "reason": "missing_license_boundary"})
        if "approval" not in lowered and "审批" not in text:
            failures.append({"file": relative, "reason": "missing_approval_boundary"})
        if "hermes" not in lowered or "openclaw" not in lowered:
            failures.append({"file": relative, "reason": "missing_runtime_boundary"})

        for name, pattern in FORBIDDEN_PATTERNS:
            if pattern.search(text):
                failures.append({"file": relative, "reason": "forbidden_pattern", "pattern": name})

    result = {
        "ok": not failures,
        "operation": "p0_open_source_plan_smoke",
        "failures": failures,
        "evidence": evidence,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
