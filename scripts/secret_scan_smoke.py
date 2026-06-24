#!/usr/bin/env python3
"""Scan tracked files for token-like secrets before release packaging."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_FILE_BYTES = 2_000_000
ALLOW_FIXTURE_PATHS = {
    "scripts/agent_gateway_runtime_event_smoke.py",
    "scripts/agentops_worker_service_check_smoke.py",
    "scripts/agentops_worker_service_control_smoke.py",
    "scripts/agentops_worker_service_install_smoke.py",
    "scripts/prepared_action_approval_wall_smoke.py",
    "scripts/redaction_fuzz_smoke.py",
    "scripts/redaction_policy_smoke.py",
    "scripts/worker_secret_boundary_smoke.py",
}
ALLOW_FIXTURE_MARKERS = (
    "demo",
    "fake",
    "fixture",
    "fuzz",
    "public",
    "raw-checkpoint",
    "redaction",
    "secret",
    "should_not",
    "workerboundary",
)
PATTERNS = [
    ("openai_api_key", re.compile(r"(?i)\bsk-[A-Za-z0-9._~+/=-]{8,}\b")),
    ("notion_token", re.compile(r"\bntn_[A-Za-z0-9._~+/=-]{8,}\b")),
    ("agent_gateway_token", re.compile(r"\bagt(?:ok|sess)_[A-Za-z0-9._~+/=-]{8,}\b")),
    ("github_token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("slack_token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
]


def tracked_files() -> list[str]:
    return subprocess.check_output(["git", "ls-files"], cwd=ROOT, text=True).splitlines()


def is_allowed_fixture(path: str, line: str) -> bool:
    lowered = line.lower()
    return path in ALLOW_FIXTURE_PATHS and any(marker in lowered for marker in ALLOW_FIXTURE_MARKERS)


def scan_file(path: str) -> list[dict]:
    full_path = ROOT / path
    try:
        if full_path.stat().st_size > MAX_TEXT_FILE_BYTES:
            return []
        raw = full_path.read_bytes()
        if b"\x00" in raw:
            return []
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    findings: list[dict] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in PATTERNS:
            for match in pattern.finditer(line):
                if is_allowed_fixture(path, line):
                    continue
                findings.append({
                    "path": path,
                    "line": line_no,
                    "kind": kind,
                    "match_preview": f"{match.group(0)[:6]}...[redacted]",
                })
    return findings


def main() -> int:
    findings: list[dict] = []
    scanned = 0
    for path in tracked_files():
        scanned += 1
        findings.extend(scan_file(path))

    result = {
        "ok": not findings,
        "operation": "secret_scan_smoke",
        "scanned_files": scanned,
        "finding_count": len(findings),
        "findings": findings[:50],
        "allow_fixture_paths": sorted(ALLOW_FIXTURE_PATHS),
        "token_omitted": True,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
