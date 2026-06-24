#!/usr/bin/env python3
"""Static smoke for external exact-head commercial CI evidence."""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "commercial_exact_head_ci_evidence.py"
CONTRACT_ID = "commercial_exact_head_ci_evidence_v1"

REQUIRED_SCRIPT_STRINGS = {
    "commercial_exact_head_ci_evidence_v1",
    "Commercial Migration CI",
    "Commercial core gates",
    "Storage and Postgres parity",
    "UI, deployment, and BYOC evidence",
    "workflow_matches_expected",
    "--from-gh",
    "--require-current-head",
    "in_progress_ci_as_exact_head_proof",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_text(path: Path) -> str:
    require(path.exists(), f"missing file: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8", errors="replace")


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify external exact-head CI evidence reader.")
    parser.add_argument("--from-gh", action="store_true", help="Also exercise the live gh lookup.")
    parser.add_argument("--require-current-head", action="store_true", help="Fail unless live gh lookup verifies current HEAD.")
    args = parser.parse_args()

    script_text = read_text(SCRIPT)
    for needle in REQUIRED_SCRIPT_STRINGS:
        require(needle in script_text, f"script missing {needle!r}")

    default = run_script()
    require(default.returncode == 0, f"default evidence reader failed: {default.stdout}{default.stderr}")
    payload = json.loads(default.stdout)
    require(payload.get("ok") is True, "default payload must be ok")
    require(payload.get("contract") == CONTRACT_ID, "contract mismatch")
    require(payload.get("external_check_requested") is False, "default must not query external CI")
    require(payload.get("exact_head_ci_verified") is False, "default must not claim exact-head CI")
    require(payload.get("status") == "external_ci_check_not_requested", "default status mismatch")

    if args.from_gh or args.require_current_head:
        live_args = ["--from-gh"]
        if args.require_current_head:
            live_args.append("--require-current-head")
        live = run_script(*live_args)
        require(live.returncode == 0, f"live exact-head CI evidence failed: {live.stdout}{live.stderr}")
        live_payload = json.loads(live.stdout)
        require(live_payload.get("external_check_requested") is True, "live payload must request external check")
        if args.require_current_head:
            require(live_payload.get("exact_head_ci_verified") is True, "live payload must verify current HEAD")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT_ID,
        "live_check_requested": bool(args.from_gh or args.require_current_head),
        "strict_current_head_required": bool(args.require_current_head),
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
