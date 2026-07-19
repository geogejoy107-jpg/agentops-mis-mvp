#!/usr/bin/env python3
"""Create immutable command, scope, and aggregate CI evidence receipts."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SENSITIVE_ASSIGNMENT_RE = re.compile(r"(?i)^([^=]*(?:token|secret|password|key|dsn)[^=]*)=(.*)$")
SAFE_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,119}$")


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(payload: Any) -> str:
    return sha256_bytes(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def current_sha() -> str:
    candidate = str(os.environ.get("GITHUB_SHA") or "").strip().lower()
    if SHA_RE.fullmatch(candidate):
        return candidate
    proc = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    candidate = proc.stdout.strip().lower()
    return candidate if SHA_RE.fullmatch(candidate) else ""


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def all_scalar_values(value: Any) -> set[str]:
    values: set[str] = set()
    if isinstance(value, dict):
        for child in value.values():
            values.update(all_scalar_values(child))
    elif isinstance(value, list):
        for child in value:
            values.update(all_scalar_values(child))
    elif isinstance(value, str):
        values.add(value)
    return values


def any_skipped(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("skipped") is True:
            return True
        return any(any_skipped(child) for child in value.values())
    if isinstance(value, list):
        return any(any_skipped(child) for child in value)
    return False


def payload_diagnostics(payload: dict[str, Any]) -> dict[str, Any]:
    error_codes: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in {"error", "error_type", "error_stage"} and isinstance(child, str) and SAFE_CODE_RE.fullmatch(child):
                    error_codes.add(child)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(payload)
    failures = payload.get("failures") if isinstance(payload.get("failures"), list) else []
    for failure in failures:
        if isinstance(failure, str) and SAFE_CODE_RE.fullmatch(failure):
            error_codes.add(failure)
    raw_failure_count = payload.get("failure_count")
    failure_count = raw_failure_count if isinstance(raw_failure_count, int) and raw_failure_count >= 0 else len(failures)
    return {
        "error_codes": sorted(error_codes),
        "failure_count": failure_count,
        "failure_hashes": [sha256_bytes(str(item).encode("utf-8", errors="replace")) for item in failures],
        "failure_text_stored": False,
    }


def safe_command(command: list[str]) -> list[str]:
    safe: list[str] = []
    redact_next = False
    for arg in command:
        if redact_next:
            safe.append("[REDACTED]")
            redact_next = False
            continue
        lower = arg.lower()
        if lower in {"--password", "--token", "--secret", "--key", "--dsn"} or lower.endswith("-dsn"):
            safe.append(arg)
            redact_next = True
            continue
        assignment = SENSITIVE_ASSIGNMENT_RE.match(arg)
        safe.append(f"{assignment.group(1)}=[REDACTED]" if assignment else arg)
    return safe


def docker_image_identity(image: str) -> dict[str, Any]:
    if not image:
        return {"requested": None, "available": False}
    proc = subprocess.run(
        ["docker", "image", "inspect", image],
        cwd=ROOT,
        capture_output=True,
        timeout=20,
        check=False,
    )
    if proc.returncode != 0:
        return {"requested": image, "available": False}
    try:
        items = json.loads(proc.stdout)
        item = items[0] if isinstance(items, list) and items else {}
    except Exception:
        item = {}
    digests = sorted(str(value) for value in (item.get("RepoDigests") or []) if value)
    return {
        "requested": image,
        "available": bool(item),
        "image_id": str(item.get("Id") or ""),
        "repo_digests": digests,
        "immutable_identity_present": bool(digests or item.get("Id")),
    }


def dependency_inputs() -> dict[str, Any]:
    candidates = [
        ROOT / "pyproject.toml",
        ROOT / "requirements.txt",
        ROOT / "ui" / "next-app" / "package-lock.json",
        ROOT / "ui" / "start-building-app" / "package-lock.json",
    ]
    files = {
        str(path.relative_to(ROOT)): sha256_bytes(path.read_bytes())
        for path in candidates
        if path.exists()
    }
    psycopg_spec = ""
    optional_adapter = ROOT / "scripts" / "storage_postgres_optional_adapter_smoke.py"
    if optional_adapter.exists():
        match = re.search(
            r'PSYCOPG_INSTALL_SPEC\s*=\s*[^\n]*?["\'](psycopg\[binary\][^"\']+)["\']',
            optional_adapter.read_text(encoding="utf-8"),
        )
        psycopg_spec = match.group(1) if match else "unlocked"
    return {
        "python": sys.version.split()[0],
        "lockfile_sha256": files,
        "psycopg_install_spec": psycopg_spec,
        "inputs_sha256": canonical_sha256(files),
    }


def command_receipt(args: argparse.Namespace) -> int:
    command = list(args.command)
    if command and command[0] == "--":
        command = command[1:]
    subject_sha = current_sha()
    failures: list[str] = []
    if not command:
        failures.append("command_missing")
        proc = subprocess.CompletedProcess(command, 2, b"", b"")
    else:
        try:
            proc = subprocess.run(
                command,
                cwd=ROOT,
                capture_output=True,
                timeout=args.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            proc = subprocess.CompletedProcess(command, 124, exc.stdout or b"", exc.stderr or b"")
            failures.append("command_timeout")
    stdout = proc.stdout if isinstance(proc.stdout, bytes) else str(proc.stdout or "").encode("utf-8", errors="replace")
    stderr = proc.stderr if isinstance(proc.stderr, bytes) else str(proc.stderr or "").encode("utf-8", errors="replace")
    stdout_text = stdout.decode("utf-8", errors="replace")
    payload: object | None = None
    try:
        payload = json.loads(stdout_text)
    except Exception:
        for line in reversed(stdout_text.splitlines()):
            candidate = line.strip()
            if not candidate.startswith("{") or not candidate.endswith("}"):
                continue
            try:
                decoded = json.loads(candidate)
            except Exception:
                continue
            if isinstance(decoded, dict) and "ok" in decoded:
                payload = decoded
                break
    if payload is None:
        payload = {}
        failures.append("stdout_json_invalid")
    payload = payload if isinstance(payload, dict) else {}
    observed_values = all_scalar_values(payload)
    missing_contracts = sorted(set(args.expected_contract) - observed_values)
    if not subject_sha:
        failures.append("subject_sha_unavailable")
    if proc.returncode != 0:
        failures.append("command_exit_nonzero")
    if payload.get("ok") is not True:
        failures.append("payload_not_ok")
    if any_skipped(payload):
        failures.append("payload_contains_skipped_evidence")
    if missing_contracts:
        failures.append("expected_contract_missing")
    failures = sorted(set(failures))
    receipt = {
        "contract_id": "commercial_ci_command_receipt_v1",
        "generated_at": utc_now(),
        "subject_sha": subject_sha,
        "builder_sha": subject_sha,
        "github_run": {
            "run_id": str(os.environ.get("GITHUB_RUN_ID") or "local"),
            "run_attempt": str(os.environ.get("GITHUB_RUN_ATTEMPT") or "local"),
            "workflow": str(os.environ.get("GITHUB_WORKFLOW") or "local"),
        },
        "gate_id": args.gate_id,
        "command_id": args.command_id,
        "command": safe_command(command),
        "exit_code": int(proc.returncode),
        "payload_ok": payload.get("ok") is True,
        "skipped_evidence": any_skipped(payload),
        "expected_contracts": sorted(set(args.expected_contract)),
        "missing_contracts": missing_contracts,
        "payload_diagnostics": payload_diagnostics(payload),
        "stdout_sha256": sha256_bytes(stdout),
        "stdout_size_bytes": len(stdout),
        "stderr_sha256": sha256_bytes(stderr),
        "stderr_size_bytes": len(stderr),
        "container_image": docker_image_identity(args.container_image),
        "dependency_inputs": dependency_inputs(),
        "evidence_complete": not failures,
        "failures": failures,
        "raw_output_stored": False,
        "credentials_stored": False,
        "release_complete": False,
        "commercial_handoff_allowed": False,
        "ready_to_merge": False,
    }
    write_json(Path(args.output), receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if receipt["evidence_complete"] else 1


def scope_receipt(args: argparse.Namespace) -> int:
    subject_sha = current_sha()
    receipt_dir = Path(args.receipts_dir)
    command_receipts: dict[str, dict[str, Any]] = {}
    for path in sorted(receipt_dir.glob("*.json")) if receipt_dir.exists() else []:
        payload = read_json(path)
        command_id = str(payload.get("command_id") or "")
        if command_id:
            command_receipts[command_id] = payload
    required = list(dict.fromkeys(args.required_command_id))
    missing = [command_id for command_id in required if command_id not in command_receipts]
    invalid: list[str] = []
    summaries: list[dict[str, Any]] = []
    for command_id in required:
        receipt = command_receipts.get(command_id) or {}
        if receipt and (
            receipt.get("contract_id") != "commercial_ci_command_receipt_v1"
            or receipt.get("subject_sha") != subject_sha
            or receipt.get("gate_id") != args.gate_id
            or receipt.get("evidence_complete") is not True
        ):
            invalid.append(command_id)
        if receipt:
            summaries.append({
                "command_id": command_id,
                "command": receipt.get("command") or [],
                "receipt_sha256": canonical_sha256(receipt),
                "stdout_sha256": receipt.get("stdout_sha256"),
                "exit_code": receipt.get("exit_code"),
                "payload_ok": receipt.get("payload_ok") is True,
                "evidence_complete": receipt.get("evidence_complete") is True,
                "skipped_evidence": receipt.get("skipped_evidence") is True,
                "expected_contracts": receipt.get("expected_contracts") or [],
                "missing_contracts": receipt.get("missing_contracts") or [],
                "failures": receipt.get("failures") or [],
                "payload_diagnostics": receipt.get("payload_diagnostics") or {},
                "container_image": receipt.get("container_image") or {},
                "dependency_inputs": receipt.get("dependency_inputs") or {},
            })
    failures = []
    if not subject_sha:
        failures.append("subject_sha_unavailable")
    if missing:
        failures.append("required_command_receipt_missing")
    if invalid:
        failures.append("required_command_receipt_invalid")
    payload = {
        "contract_id": "commercial_postgres_byoc_ci_receipt_v1",
        "generated_at": utc_now(),
        "subject_sha": subject_sha,
        "builder_sha": subject_sha,
        "github_run": {
            "run_id": str(os.environ.get("GITHUB_RUN_ID") or "local"),
            "run_attempt": str(os.environ.get("GITHUB_RUN_ATTEMPT") or "local"),
        },
        "gate_id": args.gate_id,
        "required_command_ids": required,
        "missing_command_ids": missing,
        "invalid_command_ids": invalid,
        "command_receipts": summaries,
        "scope_evidence_complete": not failures,
        "failures": failures,
        "raw_output_stored": False,
        "credentials_stored": False,
        "release_complete": False,
        "commercial_handoff_allowed": False,
        "ready_to_merge": False,
    }
    write_json(Path(args.output), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["scope_evidence_complete"] else 1


def aggregate_receipt(args: argparse.Namespace) -> int:
    subject_sha = current_sha()
    scopes: dict[str, dict[str, Any]] = {}
    for value in args.scope_receipt:
        payload = read_json(Path(value))
        gate_id = str(payload.get("gate_id") or "")
        if gate_id:
            scopes[gate_id] = payload
    jobs: dict[str, str] = {}
    for value in args.job_result:
        name, separator, result = value.partition("=")
        if separator and name:
            jobs[name] = result
    missing = [scope for scope in args.required_scope if scope not in scopes]
    invalid = [
        scope
        for scope in args.required_scope
        if scope in scopes and (
            scopes[scope].get("contract_id") != "commercial_postgres_byoc_ci_receipt_v1"
            or scopes[scope].get("subject_sha") != subject_sha
            or scopes[scope].get("scope_evidence_complete") is not True
        )
    ]
    failing_jobs = sorted(name for name, result in jobs.items() if result != "success")
    scope_complete = bool(subject_sha) and not missing and not invalid
    failures = []
    if not subject_sha:
        failures.append("subject_sha_unavailable")
    if missing:
        failures.append("required_scope_receipt_missing")
    if invalid:
        failures.append("required_scope_receipt_invalid")
    if failing_jobs:
        failures.append("ci_job_not_successful")
    payload = {
        "contract_id": "commercial_migration_ci_receipt_v1",
        "generated_at": utc_now(),
        "subject_sha": subject_sha,
        "builder_sha": subject_sha,
        "github_run": {
            "run_id": str(os.environ.get("GITHUB_RUN_ID") or "local"),
            "run_attempt": str(os.environ.get("GITHUB_RUN_ATTEMPT") or "local"),
            "workflow": str(os.environ.get("GITHUB_WORKFLOW") or "local"),
        },
        "required_scopes": args.required_scope,
        "scope_receipts": [
            {
                "gate_id": scope,
                "receipt_sha256": canonical_sha256(scopes[scope]),
                "scope_evidence_complete": scopes[scope].get("scope_evidence_complete") is True,
            }
            for scope in args.required_scope
            if scope in scopes
        ],
        "missing_scopes": missing,
        "invalid_scopes": invalid,
        "job_results": jobs,
        "failing_jobs": failing_jobs,
        "scope_evidence_complete": scope_complete,
        "ci_run_complete": scope_complete and not failing_jobs,
        "failures": failures,
        "raw_output_stored": False,
        "credentials_stored": False,
        "release_complete": False,
        "commercial_handoff_allowed": False,
        "ready_to_merge": False,
    }
    write_json(Path(args.output), payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["ci_run_complete"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create hash-only commercial CI evidence receipts.")
    sub = parser.add_subparsers(dest="mode", required=True)

    command = sub.add_parser("command", help="Execute one JSON-producing command and write a hash-only receipt.")
    command.add_argument("--gate-id", required=True)
    command.add_argument("--command-id", required=True)
    command.add_argument("--expected-contract", action="append", default=[])
    command.add_argument("--container-image", default="")
    command.add_argument("--output", required=True)
    command.add_argument("--timeout", type=int, default=900)
    command.add_argument("command", nargs=argparse.REMAINDER)
    command.set_defaults(func=command_receipt)

    scope = sub.add_parser("scope", help="Combine command receipts for one gate.")
    scope.add_argument("--gate-id", required=True)
    scope.add_argument("--receipts-dir", required=True)
    scope.add_argument("--required-command-id", action="append", default=[], required=True)
    scope.add_argument("--output", required=True)
    scope.set_defaults(func=scope_receipt)

    aggregate = sub.add_parser("aggregate", help="Combine exact-head gate receipts and CI job results.")
    aggregate.add_argument("--scope-receipt", action="append", default=[])
    aggregate.add_argument("--required-scope", action="append", default=[], required=True)
    aggregate.add_argument("--job-result", action="append", default=[])
    aggregate.add_argument("--output", required=True)
    aggregate.set_defaults(func=aggregate_receipt)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
