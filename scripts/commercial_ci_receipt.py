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
SENSITIVE_COMMAND_NAME_RE = re.compile(r"(?i)(token|key|secret|password|dsn|url|path|bin)")
URL_VALUE_RE = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://")
POSIX_ABSOLUTE_PATH_RE = re.compile(r"""(?:^|[\s"'=:(])/(?!/)[^\s"'`]+""")
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"""(?:^|[\s"'=:(])(?:[A-Za-z]:[\\/]|\\\\)[^\s"'`]+""")
HOME_PATH_RE = re.compile(r"""(?:^|[\s"'=:(])~[\\/][^\s"'`]+""")
SAFE_CODE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,119}$")
REDACTED_COMMAND_VALUE = "[REDACTED]"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_sha256(payload: Any) -> str:
    return sha256_bytes(json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8"))


def git_head(root: Path = ROOT) -> str:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    candidate = proc.stdout.strip().lower()
    return candidate if SHA_RE.fullmatch(candidate) else ""


def current_sha() -> str:
    candidate = str(os.environ.get("GITHUB_SHA") or "").strip().lower()
    if SHA_RE.fullmatch(candidate):
        return candidate
    return git_head(ROOT)


def exact_sha(value: object) -> str:
    if type(value) is not str:
        return ""
    candidate = value.lower()
    return candidate if SHA_RE.fullmatch(candidate) else ""


def resolve_source_root(value: object) -> Path | None:
    if value is None or value == "":
        return ROOT.resolve()
    if type(value) is not str:
        return None
    try:
        candidate = Path(value)
        resolved = candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved if resolved.is_dir() else None


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


def strict_boolean_claim(value: Any) -> bool | None:
    return value if type(value) is bool else None


def strict_all_true_claim(values: list[Any]) -> bool | None:
    claims = [strict_boolean_claim(value) for value in values]
    return None if any(value is None for value in claims) else all(claims)


def sensitive_command_name(value: str) -> bool:
    return SENSITIVE_COMMAND_NAME_RE.search(value) is not None


def known_repo_script(value: str, source_root: Path | None = ROOT) -> str | None:
    roots = [root.resolve() for root in (source_root, ROOT) if root is not None]
    for root in dict.fromkeys(roots):
        try:
            candidate = Path(value)
            resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
            relative = resolved.relative_to(root)
        except (OSError, RuntimeError, ValueError):
            continue
        if relative.parts[:1] == ("scripts",) and relative.suffix == ".py" and resolved.is_file():
            return relative.as_posix()
    return None


def unsafe_command_value(value: str) -> bool:
    return (
        URL_VALUE_RE.search(value) is not None
        or POSIX_ABSOLUTE_PATH_RE.search(value) is not None
        or WINDOWS_ABSOLUTE_PATH_RE.search(value) is not None
        or HOME_PATH_RE.search(value) is not None
    )


def safe_command_value(value: str, source_root: Path | None = ROOT) -> str:
    script = known_repo_script(value, source_root)
    if script is not None:
        return script
    roots = [root.resolve() for root in (source_root, ROOT) if root is not None]
    if any(str(root) in value for root in roots):
        return REDACTED_COMMAND_VALUE
    return REDACTED_COMMAND_VALUE if unsafe_command_value(value) else value


def executable_basename(value: str) -> str:
    basename = value.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return basename or REDACTED_COMMAND_VALUE


def safe_command(command: list[str], source_root: Path | None = ROOT) -> list[str]:
    if not command:
        return []
    safe = [executable_basename(str(command[0]))]
    index = 1
    while index < len(command):
        arg = str(command[index])
        if "=" in arg:
            name, raw_value = arg.split("=", 1)
            value = (
                REDACTED_COMMAND_VALUE
                if sensitive_command_name(name)
                else safe_command_value(raw_value, source_root)
            )
            safe.append(f"{name}={value}")
            index += 1
            continue
        if arg.startswith("--") and sensitive_command_name(arg):
            safe.append(arg)
            if index + 1 < len(command):
                safe.append(REDACTED_COMMAND_VALUE)
                index += 2
            else:
                index += 1
            continue
        safe.append(safe_command_value(arg, source_root))
        index += 1
    return safe


def real_runtime_security_claims(payload: dict[str, Any]) -> dict[str, Any]:
    raw_adapters = payload.get("adapters")
    adapters = (
        sorted(raw_adapters)
        if isinstance(raw_adapters, list) and all(type(item) is str for item in raw_adapters)
        else None
    )
    workers = payload.get("workers") if isinstance(payload.get("workers"), dict) else {}
    guards = payload.get("manifest_authority_guards") if isinstance(payload.get("manifest_authority_guards"), dict) else {}
    reviews = payload.get("human_reviews") if isinstance(payload.get("human_reviews"), dict) else {}
    raw_identity = payload.get("runtime_dependency_identity") if isinstance(payload.get("runtime_dependency_identity"), dict) else {}
    runtime_dependency_identity = {
        key: raw_identity[key]
        for key in ("hermes_endpoint_sha256", "openclaw_binary_sha256")
        if type(raw_identity.get(key)) is str and re.fullmatch(r"[0-9a-f]{64}", raw_identity[key])
    }
    adapter_claims: dict[str, dict[str, Any]] = {}
    for adapter in adapters or []:
        if adapter not in {"hermes", "openclaw"}:
            continue
        worker = workers.get(adapter) if isinstance(workers.get(adapter), dict) else {}
        guard = guards.get(adapter) if isinstance(guards.get(adapter), dict) else {}
        review = reviews.get(adapter) if isinstance(reviews.get(adapter), dict) else {}
        first_outcome = review.get("delivery_approval_first_outcome")
        replay_outcome = review.get("delivery_approval_replay_outcome")
        delivery_request_outcome = worker.get("delivery_approval_request_outcome")
        delivery_creation_source = worker.get("delivery_approval_creation_source")
        delivery_event_count = worker.get("delivery_approval_runtime_event_count")
        delivery_audit_count = worker.get("delivery_approval_audit_count")
        adapter_claims[adapter] = {
            "provider_call_performed": strict_boolean_claim(worker.get("provider_call_performed")),
            "dry_run": strict_boolean_claim(worker.get("dry_run")),
            "manifest_complete_run_evidence_enforced": strict_all_true_claim(
                [
                    guard.get("complete_run_tool_evidence_enforced"),
                    guard.get("complete_run_evaluation_evidence_enforced"),
                    guard.get("complete_run_artifact_evidence_enforced"),
                    guard.get("audit_evidence_server_derived"),
                ]
            ),
            "customer_delivery_revalidation_blocked": strict_boolean_claim(
                guard.get("customer_delivery_revalidation_blocked")
            ),
            "approved_customer_delivery_evidence_sealed": strict_boolean_claim(
                guard.get("approved_customer_delivery_evidence_sealed")
            ),
            "blocked_customer_delivery_request_persisted": strict_boolean_claim(
                guard.get("blocked_customer_delivery_request_persisted")
            ),
            "delivery_approval_created_through_production_owner": (
                delivery_request_outcome == "created"
                and delivery_creation_source
                == "production_next_typescript_postgres_agent_gateway_route"
                and delivery_event_count == 1
                and delivery_audit_count == 1
                if (
                    type(delivery_request_outcome) is str
                    and type(delivery_creation_source) is str
                    and type(delivery_event_count) is int
                    and type(delivery_audit_count) is int
                )
                else None
            ),
            "delivery_approval_updated_once": (
                review.get("delivery_approval_first_outcome") == "updated"
                and review.get("delivery_approval_replay_outcome") == "unchanged"
                if type(first_outcome) is str and type(replay_outcome) is str
                else None
            )
        }
    return {
        "contract": payload.get("contract") if type(payload.get("contract")) is str else "",
        "control_plane": payload.get("control_plane") if type(payload.get("control_plane")) is str else "",
        "adapters": adapters,
        "adapter_claims": adapter_claims,
        "runtime_dependency_identity": runtime_dependency_identity,
        "real_runtime_execution_performed": strict_boolean_claim(payload.get("real_runtime_execution_performed")),
        "manifest_authority_guards_passed": strict_boolean_claim(payload.get("manifest_authority_guards_passed")),
        "real_run_bound_delivery_decisions_completed": strict_boolean_claim(
            payload.get("real_run_bound_delivery_decisions_completed")
        ),
        "python_api_started": strict_boolean_claim(payload.get("python_api_started")),
        "python_or_sqlite_commercial_default": strict_boolean_claim(
            payload.get("python_or_sqlite_commercial_default")
        ),
        "worker_created_delivery_approvals": strict_boolean_claim(payload.get("worker_created_delivery_approvals")),
        "delivery_approval_creation_source": (
            payload.get("delivery_approval_creation_source")
            if type(payload.get("delivery_approval_creation_source")) is str
            else ""
        ),
    }


def real_runtime_security_claims_complete(claims: dict[str, Any]) -> bool:
    expected_adapters = ["hermes", "openclaw"]
    adapter_claims = claims.get("adapter_claims") if isinstance(claims.get("adapter_claims"), dict) else {}
    runtime_dependency_identity = claims.get("runtime_dependency_identity") if isinstance(claims.get("runtime_dependency_identity"), dict) else {}
    return (
        claims.get("contract") == "nextjs_postgres_real_worker_human_review_v1"
        and claims.get("control_plane") == "typescript_postgres"
        and claims.get("adapters") == expected_adapters
        and claims.get("real_runtime_execution_performed") is True
        and claims.get("manifest_authority_guards_passed") is True
        and claims.get("real_run_bound_delivery_decisions_completed") is True
        and claims.get("python_api_started") is False
        and claims.get("python_or_sqlite_commercial_default") is False
        and claims.get("worker_created_delivery_approvals") is True
        and claims.get("delivery_approval_creation_source")
        == "production_next_typescript_postgres_agent_gateway_route"
        and set(adapter_claims) == set(expected_adapters)
        and set(runtime_dependency_identity) == {"hermes_endpoint_sha256", "openclaw_binary_sha256"}
        and all(
            type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value)
            for value in runtime_dependency_identity.values()
        )
        and all(
            adapter_claims[adapter].get("provider_call_performed") is True
            and adapter_claims[adapter].get("dry_run") is False
            and adapter_claims[adapter].get("manifest_complete_run_evidence_enforced") is True
            and adapter_claims[adapter].get("customer_delivery_revalidation_blocked") is True
            and adapter_claims[adapter].get("approved_customer_delivery_evidence_sealed") is True
            and adapter_claims[adapter].get("blocked_customer_delivery_request_persisted") is False
            and adapter_claims[adapter].get("delivery_approval_created_through_production_owner") is True
            and adapter_claims[adapter].get("delivery_approval_updated_once") is True
            for adapter in expected_adapters
        )
    )


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


def dependency_inputs(source_root: Path | None = ROOT) -> dict[str, Any]:
    if source_root is None:
        files: dict[str, str] = {}
        return {
            "python": sys.version.split()[0],
            "lockfile_sha256": files,
            "psycopg_install_spec": "",
            "inputs_sha256": canonical_sha256(files),
        }
    source_root = source_root.resolve()
    candidates = [
        source_root / "pyproject.toml",
        source_root / "requirements.txt",
        source_root / "ui" / "next-app" / "package-lock.json",
        source_root / "ui" / "start-building-app" / "package-lock.json",
    ]
    files: dict[str, str] = {}
    for path in candidates:
        try:
            resolved = path.resolve()
            resolved.relative_to(source_root)
        except (OSError, RuntimeError, ValueError):
            continue
        if path.is_symlink() or not resolved.is_file():
            continue
        files[resolved.relative_to(source_root).as_posix()] = sha256_bytes(resolved.read_bytes())
    psycopg_spec = ""
    optional_adapter = source_root / "scripts" / "storage_postgres_optional_adapter_smoke.py"
    if optional_adapter.is_file() and not optional_adapter.is_symlink():
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
    failures: list[str] = []
    requested_subject_sha = getattr(args, "subject_sha", "")
    if requested_subject_sha:
        subject_sha = exact_sha(requested_subject_sha)
        if not subject_sha:
            failures.append("subject_sha_invalid")
    else:
        subject_sha = current_sha()
        if not subject_sha:
            failures.append("subject_sha_unavailable")
    trusted_builder_sha = git_head(ROOT)
    requested_builder_sha = getattr(args, "builder_sha", "")
    if requested_builder_sha:
        builder_sha = exact_sha(requested_builder_sha)
        if not builder_sha:
            failures.append("builder_sha_invalid")
        elif not trusted_builder_sha:
            failures.append("builder_sha_unavailable")
        elif builder_sha != trusted_builder_sha:
            failures.append("builder_sha_mismatch")
    else:
        builder_sha = trusted_builder_sha
        if not builder_sha:
            failures.append("builder_sha_unavailable")
    source_root = resolve_source_root(getattr(args, "source_root", ""))
    if source_root is None:
        failures.append("source_root_invalid")

    if not command:
        failures.append("command_missing")
        proc = subprocess.CompletedProcess(command, 2, b"", b"")
    elif failures:
        failures.append("command_not_executed_invalid_context")
        proc = subprocess.CompletedProcess(command, 2, b"", b"")
    else:
        try:
            proc = subprocess.run(
                command,
                cwd=source_root,
                capture_output=True,
                timeout=args.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            proc = subprocess.CompletedProcess(command, 124, exc.stdout or b"", exc.stderr or b"")
            failures.append("command_timeout")
        except OSError:
            proc = subprocess.CompletedProcess(command, 126, b"", b"")
            failures.append("command_start_failed")
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
    runtime_security_claims = real_runtime_security_claims(payload)
    observed_values = all_scalar_values(payload)
    missing_contracts = sorted(set(args.expected_contract) - observed_values)
    if proc.returncode != 0:
        failures.append("command_exit_nonzero")
    if payload.get("ok") is not True:
        failures.append("payload_not_ok")
    if any_skipped(payload):
        failures.append("payload_contains_skipped_evidence")
    if missing_contracts:
        failures.append("expected_contract_missing")
    if (
        "nextjs_postgres_real_worker_human_review_v1" in args.expected_contract
        and not real_runtime_security_claims_complete(runtime_security_claims)
    ):
        failures.append("real_runtime_security_claims_incomplete")
    failures = sorted(set(failures))
    receipt = {
        "contract_id": "commercial_ci_command_receipt_v1",
        "generated_at": utc_now(),
        "subject_sha": subject_sha,
        "builder_sha": builder_sha,
        "github_run": {
            "run_id": str(os.environ.get("GITHUB_RUN_ID") or "local"),
            "run_attempt": str(os.environ.get("GITHUB_RUN_ATTEMPT") or "local"),
            "workflow": str(os.environ.get("GITHUB_WORKFLOW") or "local"),
            "repository": str(os.environ.get("GITHUB_REPOSITORY") or "local"),
            "ref": str(os.environ.get("GITHUB_REF") or "local"),
        },
        "gate_id": args.gate_id,
        "command_id": args.command_id,
        "command": safe_command(command, source_root),
        "exit_code": int(proc.returncode),
        "payload_ok": payload.get("ok") is True,
        "skipped_evidence": any_skipped(payload),
        "expected_contracts": sorted(set(args.expected_contract)),
        "missing_contracts": missing_contracts,
        "payload_diagnostics": payload_diagnostics(payload),
        "runtime_security_claims": runtime_security_claims,
        "stdout_sha256": sha256_bytes(stdout),
        "stdout_size_bytes": len(stdout),
        "stderr_sha256": sha256_bytes(stderr),
        "stderr_size_bytes": len(stderr),
        "container_image": docker_image_identity(args.container_image),
        "dependency_inputs": dependency_inputs(source_root),
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
            "repository": str(os.environ.get("GITHUB_REPOSITORY") or "local"),
            "ref": str(os.environ.get("GITHUB_REF") or "local"),
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
            "repository": str(os.environ.get("GITHUB_REPOSITORY") or "local"),
            "ref": str(os.environ.get("GITHUB_REF") or "local"),
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
    command.add_argument("--subject-sha", default="")
    command.add_argument("--builder-sha", default="")
    command.add_argument("--source-root", default="")
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
