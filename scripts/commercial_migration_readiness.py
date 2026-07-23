#!/usr/bin/env python3
"""Read-only commercial migration readiness checker.

Local engineering checks avoid external services. When an external Runtime
receipt is supplied, the checker also verifies its GitHub attestation and source
workflow run before granting that receipt release authority.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
HASH_RE = re.compile(r"^[0-9a-f]{64}$")
SENSITIVE_COMMAND_NAME_RE = re.compile(r"(?i)(token|key|secret|password|dsn|url|path|bin)")
URL_VALUE_RE = re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://")
POSIX_ABSOLUTE_PATH_RE = re.compile(r"""(?:^|[\s"'=:(])/(?!/)[^\s"'`]+""")
WINDOWS_ABSOLUTE_PATH_RE = re.compile(r"""(?:^|[\s"'=:(])(?:[A-Za-z]:[\\/]|\\\\)[^\s"'`]+""")
HOME_PATH_RE = re.compile(r"""(?:^|[\s"'=:(])~[\\/][^\s"'`]+""")
REDACTED_COMMAND_VALUE = "[REDACTED]"
MAX_EXTERNAL_EVIDENCE_BYTES = 32 * 1024 * 1024
GITHUB_RUN_TIME_TOLERANCE = dt.timedelta(minutes=5)
TRUSTED_RUNTIME_WORKFLOW_PATH = ".github/workflows/commercial-real-runtime-acceptance.yml"
TRUSTED_RUNTIME_JOB_ID = "trusted-real-runtime"
TRUSTED_RUNTIME_MAIN_GUARD = (
    "github.event_name == 'workflow_dispatch' && github.ref == 'refs/heads/main'"
)
TRUSTED_RUNTIME_PERMISSIONS = {
    "contents": "read",
    "id-token": "write",
    "attestations": "write",
    "artifact-metadata": "write",
}
TRUSTED_RUNTIME_CHECKOUT_ACTION = (
    "actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683"
)
TRUSTED_RUNTIME_ATTEST_ACTION = (
    "actions/attest@f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6"
)
TRUSTED_RUNTIME_UPLOAD_ACTION = (
    "actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02"
)
TRUSTED_RUNTIME_SUPPLY_CHAIN_BLOCKERS = {
    "trusted_real_runtime_builder_not_established": "supply_chain",
    "trusted_runtime_identity_attestation_missing": "runtime_identity",
    "receipt_verifier_binary_trust_missing": "supply_chain",
}

BLOCKED_PATH_PARTS = (
    "node_modules/",
    "/dist/",
    ".agentops_runtime/",
    "__pycache__/",
)
BLOCKED_SUFFIXES = (
    ".db",
    ".db-journal",
    ".db-shm",
    ".db-wal",
    ".env",
    ".log",
    ".tsbuildinfo",
)


def run_git(args: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        return False, str(exc)
    output = result.stdout.strip() or result.stderr.strip()
    return result.returncode == 0, output


def file_contains(path: str, needle: str) -> bool:
    target = ROOT / path
    if not target.exists():
        return False
    return needle in target.read_text(encoding="utf-8", errors="replace")


def python_functions_call(path: str, function_names: tuple[str, ...], callee: str) -> bool:
    target = ROOT / path
    if not target.exists():
        return False
    try:
        tree = ast.parse(target.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return False
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    return all(
        name in functions
        and any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == callee
            for node in ast.walk(functions[name])
        )
        for name in function_names
    )


def read_json(path: str) -> dict:
    target = ROOT / path
    if not target.exists():
        return {}
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _yaml_strip_comment(value: str) -> str:
    quote = ""
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if quote == '"' and char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            if not quote:
                quote = char
            elif quote == char:
                quote = ""
            continue
        if char == "#" and not quote and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
    return value.rstrip()


def _yaml_mapping_entry(value: str) -> tuple[str, str]:
    match = re.fullmatch(r"([A-Za-z0-9_.-]+):(.*)", value)
    if not match:
        raise ValueError("unsupported_yaml_mapping_entry")
    return match.group(1), match.group(2).strip()


def _yaml_inline_values(value: str) -> list[str]:
    values: list[str] = []
    start = 0
    quote = ""
    escaped = False
    for index, char in enumerate(value):
        if escaped:
            escaped = False
            continue
        if quote == '"' and char == "\\":
            escaped = True
            continue
        if char in {"'", '"'}:
            if not quote:
                quote = char
            elif quote == char:
                quote = ""
            continue
        if char == "," and not quote:
            values.append(value[start:index].strip())
            start = index + 1
    if quote:
        raise ValueError("unterminated_yaml_quote")
    values.append(value[start:].strip())
    return values


def _yaml_scalar(value: str) -> object:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    if value in {"null", "Null", "NULL", "~"}:
        return None
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    if value == "[]":
        return []
    if value == "{}":
        return {}
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [_yaml_scalar(item) for item in _yaml_inline_values(inner)]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("invalid_yaml_double_quoted_scalar") from exc
        if not isinstance(parsed, str):
            raise ValueError("invalid_yaml_string_scalar")
        return parsed
    if value.startswith(("&", "*", "!")):
        raise ValueError("yaml_alias_anchor_or_tag_not_supported")
    return value


def parse_restricted_workflow_yaml(text: str) -> dict:
    """Parse the mapping/list subset used by the trusted acceptance workflow."""
    tokens: list[tuple[int, int, str, str]] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip())]:
            raise ValueError("yaml_tab_indentation_not_supported")
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        raw_content = raw_line[indent:]
        content = _yaml_strip_comment(raw_content)
        if not content or content in {"---", "..."}:
            continue
        tokens.append((line_number, indent, content, raw_content))
    if not tokens:
        raise ValueError("workflow_yaml_empty")

    def parse_block(index: int, indent: int) -> tuple[object, int]:
        if index >= len(tokens) or tokens[index][1] != indent:
            raise ValueError("workflow_yaml_invalid_indentation")
        if tokens[index][2].startswith("-"):
            return parse_sequence(index, indent)
        return parse_mapping(index, indent)

    def parse_mapping(index: int, indent: int) -> tuple[dict, int]:
        result: dict[str, object] = {}
        while index < len(tokens):
            line_number, current_indent, content, _raw_content = tokens[index]
            if current_indent < indent:
                break
            if current_indent != indent or content.startswith("-"):
                raise ValueError(f"workflow_yaml_invalid_mapping_line_{line_number}")
            key, raw_value = _yaml_mapping_entry(content)
            if key in result:
                raise ValueError(f"workflow_yaml_duplicate_key_{key}")
            index += 1
            if raw_value in {"|", "|-", "|+", ">", ">-", ">+"}:
                block_lines: list[str] = []
                while index < len(tokens) and tokens[index][1] > indent:
                    block_lines.append(tokens[index][3].lstrip())
                    index += 1
                result[key] = "\n".join(block_lines)
            elif raw_value:
                result[key] = _yaml_scalar(raw_value)
            elif index < len(tokens) and tokens[index][1] > indent:
                result[key], index = parse_block(index, tokens[index][1])
            else:
                result[key] = None
        return result, index

    def parse_sequence(index: int, indent: int) -> tuple[list, int]:
        result: list[object] = []
        while index < len(tokens):
            line_number, current_indent, content, _raw_content = tokens[index]
            if current_indent < indent:
                break
            if current_indent != indent or not content.startswith("-"):
                raise ValueError(f"workflow_yaml_invalid_sequence_line_{line_number}")
            remainder = content[1:].strip()
            index += 1
            if not remainder:
                if index >= len(tokens) or tokens[index][1] <= indent:
                    raise ValueError(f"workflow_yaml_empty_sequence_item_{line_number}")
                item, index = parse_block(index, tokens[index][1])
                result.append(item)
                continue
            if re.fullmatch(r"[A-Za-z0-9_.-]+:.*", remainder):
                key, raw_value = _yaml_mapping_entry(remainder)
                item: dict[str, object] = {}
                if raw_value in {"|", "|-", "|+", ">", ">-", ">+"}:
                    block_lines = []
                    while index < len(tokens) and tokens[index][1] > indent:
                        block_lines.append(tokens[index][3].lstrip())
                        index += 1
                    item[key] = "\n".join(block_lines)
                elif raw_value:
                    item[key] = _yaml_scalar(raw_value)
                elif index < len(tokens) and tokens[index][1] > indent:
                    item[key], index = parse_block(index, tokens[index][1])
                else:
                    item[key] = None
                if index < len(tokens) and tokens[index][1] > indent:
                    continuation, index = parse_block(index, tokens[index][1])
                    if not isinstance(continuation, dict):
                        raise ValueError(
                            f"workflow_yaml_sequence_mapping_expected_{line_number}"
                        )
                    overlap = set(item).intersection(continuation)
                    if overlap:
                        raise ValueError(
                            "workflow_yaml_duplicate_sequence_key_" + sorted(overlap)[0]
                        )
                    item.update(continuation)
                result.append(item)
            else:
                result.append(_yaml_scalar(remainder))
                if index < len(tokens) and tokens[index][1] > indent:
                    raise ValueError(
                        f"workflow_yaml_scalar_sequence_has_children_{line_number}"
                    )
        return result, index

    parsed, final_index = parse_block(0, tokens[0][1])
    if final_index != len(tokens) or not isinstance(parsed, dict) or tokens[0][1] != 0:
        raise ValueError("workflow_yaml_root_mapping_required")
    return parsed


def _normalized_workflow_command(value: object) -> str:
    return " ".join(str(value or "").split())


def trusted_real_runtime_workflow_failures(text: str) -> list[str]:
    failures: list[str] = []

    def require(condition: bool, failure: str) -> None:
        if not condition:
            failures.append(failure)

    try:
        workflow = parse_restricted_workflow_yaml(text)
    except (TypeError, ValueError):
        return ["trusted_runtime_workflow_yaml_invalid"]

    events = workflow.get("on")
    require(
        isinstance(events, dict) and set(events) == {"workflow_dispatch"},
        "trusted_runtime_trigger_not_workflow_dispatch_only",
    )
    dispatch = events.get("workflow_dispatch") if isinstance(events, dict) else None
    inputs = dispatch.get("inputs") if isinstance(dispatch, dict) else None
    expected_sha_input = inputs.get("expected_sha") if isinstance(inputs, dict) else None
    candidate_ref_input = inputs.get("candidate_ref") if isinstance(inputs, dict) else None
    require(
        isinstance(expected_sha_input, dict)
        and expected_sha_input.get("required") is True
        and expected_sha_input.get("type") == "string",
        "trusted_runtime_expected_sha_input_invalid",
    )
    require(
        isinstance(candidate_ref_input, dict)
        and candidate_ref_input.get("required") is True
        and candidate_ref_input.get("type") == "string",
        "trusted_runtime_candidate_ref_input_invalid",
    )
    require(
        workflow.get("name") == "commercial-real-runtime-acceptance",
        "trusted_runtime_workflow_name_invalid",
    )
    require(
        workflow.get("permissions") == TRUSTED_RUNTIME_PERMISSIONS,
        "trusted_runtime_permissions_not_least_privilege",
    )
    concurrency = workflow.get("concurrency")
    require(
        isinstance(concurrency, dict)
        and concurrency.get("group")
        == "commercial-real-runtime-${{ inputs.expected_sha }}"
        and concurrency.get("cancel-in-progress") is False,
        "trusted_runtime_expected_sha_concurrency_binding_missing",
    )

    jobs = workflow.get("jobs")
    require(
        isinstance(jobs, dict) and set(jobs) == {TRUSTED_RUNTIME_JOB_ID},
        "trusted_runtime_single_trusted_job_required",
    )
    job = jobs.get(TRUSTED_RUNTIME_JOB_ID) if isinstance(jobs, dict) else None
    if not isinstance(job, dict):
        return sorted(set(failures + ["trusted_runtime_job_missing"]))
    require(
        _normalized_workflow_command(job.get("if")) == TRUSTED_RUNTIME_MAIN_GUARD,
        "trusted_runtime_exact_main_ref_guard_missing",
    )
    require(
        job.get("environment") == "commercial-real-runtime",
        "trusted_runtime_protected_environment_missing",
    )
    require(
        job.get("runs-on") == ["self-hosted", "agentops-real-runtime"],
        "trusted_runtime_dedicated_runner_missing",
    )
    require("permissions" not in job, "trusted_runtime_job_permission_override_forbidden")
    timeout_minutes = job.get("timeout-minutes")
    require(
        type(timeout_minutes) is int and 0 < timeout_minutes <= 30,
        "trusted_runtime_job_timeout_invalid",
    )

    steps = job.get("steps")
    if not isinstance(steps, list) or any(not isinstance(step, dict) for step in steps):
        return sorted(set(failures + ["trusted_runtime_steps_invalid"]))
    require(len(steps) == 8, "trusted_runtime_unexpected_step_count")
    require(
        all(
            "continue-on-error" not in step and "working-directory" not in step
            for step in steps
        ),
        "trusted_runtime_step_fail_open_or_workdir_override",
    )

    checkout_steps = [
        step for step in steps if step.get("uses") == TRUSTED_RUNTIME_CHECKOUT_ACTION
    ]
    require(len(checkout_steps) == 2, "trusted_runtime_dual_checkout_missing")
    checkout_by_path: dict[str, dict] = {}
    for step in checkout_steps:
        checkout_with = step.get("with")
        if not isinstance(checkout_with, dict):
            continue
        path = checkout_with.get("path")
        if isinstance(path, str):
            checkout_by_path[path] = checkout_with
        require(
            checkout_with.get("fetch-depth") == 1
            and checkout_with.get("persist-credentials") is False,
            "trusted_runtime_checkout_hardening_missing",
        )
    trusted_checkout = checkout_by_path.get("trusted")
    candidate_checkout = checkout_by_path.get("candidate")
    require(
        isinstance(trusted_checkout, dict)
        and trusted_checkout.get("ref") == "${{ github.sha }}",
        "trusted_runtime_main_checkout_binding_missing",
    )
    require(
        isinstance(candidate_checkout, dict)
        and candidate_checkout.get("ref") == "${{ inputs.candidate_ref }}",
        "trusted_runtime_candidate_checkout_binding_missing",
    )

    run_steps = [step for step in steps if isinstance(step.get("run"), str)]
    commands = [_normalized_workflow_command(step.get("run")) for step in run_steps]
    install_steps = [
        step
        for step in run_steps
        if _normalized_workflow_command(step.get("run"))
        == "npm --prefix candidate/ui/next-app ci --ignore-scripts"
    ]
    require(len(install_steps) == 1, "trusted_runtime_candidate_install_path_invalid")

    verification_markers = (
        '[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]]',
        '[[ "$CANDIDATE_REF" =~ ^[A-Za-z0-9._/-]{1,180}$ ]]',
        'test "$(git -C trusted rev-parse HEAD)" = "$GITHUB_SHA"',
        'test "$(git -C candidate rev-parse HEAD)" = "$EXPECTED_SHA"',
        'test -z "$(git -C trusted status --short)"',
        'test -z "$(git -C candidate status --short)"',
    )
    verification_steps = [
        step
        for step in run_steps
        if all(
            marker in _normalized_workflow_command(step.get("run"))
            for marker in verification_markers
        )
    ]
    require(len(verification_steps) == 1, "trusted_runtime_exact_sha_verification_missing")
    if verification_steps:
        verification_env = verification_steps[0].get("env")
        require(
            isinstance(verification_env, dict)
            and verification_env.get("EXPECTED_SHA") == "${{ inputs.expected_sha }}"
            and verification_env.get("CANDIDATE_REF") == "${{ inputs.candidate_ref }}",
            "trusted_runtime_verification_input_binding_missing",
        )

    runtime_steps = [step for step in run_steps if step.get("id") == "runtime_receipt"]
    require(len(runtime_steps) == 1, "trusted_runtime_receipt_step_missing")
    if runtime_steps:
        runtime_step = runtime_steps[0]
        runtime_command = _normalized_workflow_command(runtime_step.get("run"))
        runtime_env = runtime_step.get("env")
        require(
            isinstance(runtime_env, dict)
            and runtime_env.get("EXPECTED_SHA") == "${{ inputs.expected_sha }}",
            "trusted_runtime_receipt_expected_sha_env_missing",
        )
        required_runtime_fragments = (
            '"$PYTHON_BIN" -B trusted/scripts/commercial_ci_receipt.py command',
            "--gate-id gate_5_human_memory_real_runtime",
            "--command-id trusted_main_real_runtime_human_review",
            "--expected-contract nextjs_postgres_real_worker_human_review_v1",
            '--subject-sha "$EXPECTED_SHA"',
            '--builder-sha "$GITHUB_SHA"',
            '"$PYTHON_BIN" -B "$GITHUB_WORKSPACE/trusted/scripts/nextjs_postgres_real_worker_human_review_smoke.py"',
            "--adapter hermes",
            "--adapter openclaw",
        )
        require(
            all(fragment in runtime_command for fragment in required_runtime_fragments),
            "trusted_runtime_receipt_or_harness_contract_missing",
        )
        require(
            runtime_command.count('--source-root "$GITHUB_WORKSPACE/candidate"') == 2,
            "trusted_runtime_candidate_build_source_binding_missing",
        )
        require(
            "candidate/scripts/" not in runtime_command
            and "$GITHUB_WORKSPACE/candidate/scripts/" not in runtime_command,
            "trusted_runtime_candidate_controlled_harness_forbidden",
        )

    all_commands = "\n".join(commands)
    require(
        all_commands.count("trusted/scripts/commercial_ci_receipt.py") == 1
        and all_commands.count(
            "trusted/scripts/nextjs_postgres_real_worker_human_review_smoke.py"
        )
        == 1,
        "trusted_runtime_harness_must_only_execute_from_trusted_checkout",
    )

    attest_steps = [
        step for step in steps if step.get("uses") == TRUSTED_RUNTIME_ATTEST_ACTION
    ]
    require(
        len(attest_steps) == 1
        and attest_steps[0].get("id") == "runtime_attestation"
        and isinstance(attest_steps[0].get("with"), dict)
        and attest_steps[0]["with"].get("subject-path")
        == "receipts/human-memory-real-runtime.json",
        "trusted_runtime_attestation_step_invalid",
    )
    collect_steps = [
        step
        for step in run_steps
        if "steps.runtime_attestation.outputs.bundle-path"
        in _normalized_workflow_command(step.get("run"))
        and "receipts/human-memory-real-runtime.attestation.json"
        in _normalized_workflow_command(step.get("run"))
    ]
    require(len(collect_steps) == 1, "trusted_runtime_attestation_bundle_collection_missing")
    upload_steps = [
        step for step in steps if step.get("uses") == TRUSTED_RUNTIME_UPLOAD_ACTION
    ]
    if len(upload_steps) != 1 or not isinstance(upload_steps[0].get("with"), dict):
        failures.append("trusted_runtime_receipt_upload_invalid")
    else:
        upload_with = upload_steps[0]["with"]
        upload_path = str(upload_with.get("path") or "")
        require(
            upload_with.get("name")
            == "commercial-real-runtime-receipt-${{ inputs.expected_sha }}"
            and upload_with.get("if-no-files-found") == "error"
            and "receipts/human-memory-real-runtime.json" in upload_path
            and "receipts/human-memory-real-runtime.attestation.json" in upload_path,
            "trusted_runtime_receipt_upload_invalid",
        )

    recognized_steps = (
        len(checkout_steps)
        + len(install_steps)
        + len(verification_steps)
        + len(runtime_steps)
        + len(attest_steps)
        + len(collect_steps)
        + len(upload_steps)
    )
    require(
        recognized_steps == len(steps),
        "trusted_runtime_unrecognized_step_forbidden",
    )
    return sorted(set(failures))


def trusted_runtime_blocker_contract_failures(blockers: object) -> list[str]:
    if not isinstance(blockers, dict):
        return ["trusted_runtime_blocker_contract_invalid"]
    failures: list[str] = []
    requirement = blockers.get("external_runtime_receipt_requirement")
    if (
        not isinstance(requirement, dict)
        or requirement.get("builder_must_differ_from_candidate_authority") is not True
    ):
        failures.append("trusted_runtime_independent_builder_requirement_missing")
    open_blockers = blockers.get("open_blockers")
    if not isinstance(open_blockers, list):
        return sorted(set(failures + ["trusted_runtime_open_blockers_invalid"]))
    rows = [
        item
        for item in open_blockers
        if isinstance(item, dict)
        and item.get("id") in TRUSTED_RUNTIME_SUPPLY_CHAIN_BLOCKERS
    ]
    row_ids = [str(item.get("id")) for item in rows]
    if len(row_ids) != len(set(row_ids)):
        failures.append("trusted_runtime_supply_chain_blocker_duplicate")
    by_id = {str(item.get("id")): item for item in rows}
    for blocker_id, expected_kind in TRUSTED_RUNTIME_SUPPLY_CHAIN_BLOCKERS.items():
        item = by_id.get(blocker_id)
        if not isinstance(item, dict):
            failures.append(f"trusted_runtime_supply_chain_blocker_missing:{blocker_id}")
            continue
        if item.get("status") != "open" or item.get("kind") != expected_kind:
            failures.append(f"trusted_runtime_supply_chain_blocker_weakened:{blocker_id}")
    return sorted(set(failures))


def valid_utc_timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return False
    return parsed.tzinfo is not None and parsed.utcoffset() == dt.timedelta(0)


def parse_utc_timestamp(value: object) -> dt.datetime | None:
    if not valid_utc_timestamp(value):
        return None
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def read_regular_file_once(path: Path, label: str) -> tuple[bytes, str | None]:
    try:
        path_stat = os.lstat(path)
    except OSError:
        return b"", f"{label}_unreadable"
    if not stat.S_ISREG(path_stat.st_mode):
        return b"", f"{label}_not_regular"
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return b"", f"{label}_unreadable"
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or (before.st_dev, before.st_ino) != (path_stat.st_dev, path_stat.st_ino)
            or before.st_size < 0
            or before.st_size > MAX_EXTERNAL_EVIDENCE_BYTES
        ):
            return b"", (
                f"{label}_too_large"
                if before.st_size > MAX_EXTERNAL_EVIDENCE_BYTES
                else f"{label}_changed_before_read"
            )
        chunks: list[bytes] = []
        size = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, MAX_EXTERNAL_EVIDENCE_BYTES + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_EXTERNAL_EVIDENCE_BYTES:
                return b"", f"{label}_too_large"
        after = os.fstat(descriptor)
        if (
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            or size != before.st_size
        ):
            return b"", f"{label}_changed_during_read"
        return b"".join(chunks), None
    except OSError:
        return b"", f"{label}_unreadable"
    finally:
        os.close(descriptor)


def write_owner_only_snapshot(path: Path, value: bytes) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)
    os.chmod(path, 0o600)


def statement_binds_receipt_sha256(statement: object, receipt_sha256: str) -> bool:
    if not isinstance(statement, dict):
        return False
    subjects = statement.get("subject")
    if not isinstance(subjects, list) or len(subjects) != 1 or not isinstance(subjects[0], dict):
        return False
    digest = subjects[0].get("digest")
    return (
        isinstance(digest, dict)
        and set(digest) == {"sha256"}
        and digest.get("sha256") == receipt_sha256
    )


def command_value_is_safe(value: str) -> bool:
    return not (
        URL_VALUE_RE.search(value)
        or POSIX_ABSOLUTE_PATH_RE.search(value)
        or WINDOWS_ABSOLUTE_PATH_RE.search(value)
        or HOME_PATH_RE.search(value)
    )


def external_runtime_command_valid(value: object) -> bool:
    if not isinstance(value, list) or not value or any(type(item) is not str for item in value):
        return False
    executable = value[0]
    if executable != executable.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]:
        return False
    if "scripts/nextjs_postgres_real_worker_human_review_smoke.py" not in value:
        return False
    index = 1
    while index < len(value):
        arg = value[index]
        if not command_value_is_safe(arg):
            return False
        if "=" in arg:
            name, persisted_value = arg.split("=", 1)
            if SENSITIVE_COMMAND_NAME_RE.search(name) and persisted_value != REDACTED_COMMAND_VALUE:
                return False
        elif arg.startswith("--") and SENSITIVE_COMMAND_NAME_RE.search(arg):
            if index + 1 >= len(value) or value[index + 1] != REDACTED_COMMAND_VALUE:
                return False
            index += 1
        index += 1
    return True


def runtime_security_claims_valid(value: object, required_adapters: set[str]) -> bool:
    if not isinstance(value, dict):
        return False
    adapters = value.get("adapters")
    if (
        not required_adapters
        or not isinstance(adapters, list)
        or any(type(item) is not str for item in adapters)
        or len(adapters) != len(set(adapters))
        or set(adapters) != required_adapters
    ):
        return False
    adapter_claims = value.get("adapter_claims") if isinstance(value.get("adapter_claims"), dict) else {}
    runtime_dependency_identity = value.get("runtime_dependency_identity") if isinstance(value.get("runtime_dependency_identity"), dict) else {}
    return (
        value.get("contract") == "nextjs_postgres_real_worker_human_review_v1"
        and value.get("control_plane") == "typescript_postgres"
        and value.get("real_runtime_execution_performed") is True
        and value.get("manifest_authority_guards_passed") is True
        and value.get("real_run_bound_delivery_decisions_completed") is True
        and value.get("python_api_started") is False
        and value.get("python_or_sqlite_commercial_default") is False
        and value.get("worker_created_delivery_approvals") is True
        and value.get("delivery_approval_creation_source")
        == "production_next_typescript_postgres_agent_gateway_route"
        and set(adapter_claims) == required_adapters
        and set(runtime_dependency_identity) == {"hermes_endpoint_sha256", "openclaw_binary_sha256"}
        and all(type(item) is str and HASH_RE.fullmatch(item) is not None for item in runtime_dependency_identity.values())
        and all(
            isinstance(adapter_claims.get(adapter), dict)
            and adapter_claims[adapter].get("provider_call_performed") is True
            and adapter_claims[adapter].get("dry_run") is False
            and adapter_claims[adapter].get("manifest_complete_run_evidence_enforced") is True
            and adapter_claims[adapter].get("customer_delivery_revalidation_blocked") is True
            and adapter_claims[adapter].get("approved_customer_delivery_evidence_sealed") is True
            and adapter_claims[adapter].get("blocked_customer_delivery_request_persisted") is False
            and adapter_claims[adapter].get("delivery_approval_created_through_production_owner") is True
            and adapter_claims[adapter].get("delivery_approval_updated_once") is True
            for adapter in required_adapters
        )
    )


def validate_external_runtime_receipt(
    path_value: str | None,
    attestation_value: str | None,
    subject_sha: str,
    worktree_clean: bool,
    requirement: dict,
) -> dict:
    if not path_value:
        return {
            "provided": False,
            "valid": False,
            "failures": ["receipt_not_provided"],
            "subject_sha": None,
            "receipt_sha256": None,
            "attestation_verified": False,
            "github_run_verified": False,
            "release_authority": False,
        }
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    attestation_path = Path(attestation_value).expanduser() if attestation_value else None
    if attestation_path is not None and not attestation_path.is_absolute():
        attestation_path = ROOT / attestation_path
    failures: list[str] = []
    raw, receipt_file_failure = read_regular_file_once(path, "receipt")
    if receipt_file_failure:
        failures.append(receipt_file_failure)
    try:
        receipt = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        receipt = {}
        failures.append("receipt_json_invalid")
    if not isinstance(receipt, dict):
        receipt = {}
        failures.append("receipt_not_object")

    attestation_raw = b""
    attestation_file_failure = "attestation_bundle_missing"
    if attestation_path is not None:
        attestation_raw, attestation_file_failure = read_regular_file_once(
            attestation_path,
            "attestation_bundle",
        )
    if attestation_file_failure:
        failures.append(attestation_file_failure)

    raw_command = receipt.get("command")
    command = raw_command if isinstance(raw_command, list) else []
    adapters = {
        command[index + 1]
        for index, item in enumerate(command[:-1])
        if item == "--adapter" and type(command[index + 1]) is str
    }
    github_run = receipt.get("github_run") if isinstance(receipt.get("github_run"), dict) else {}
    diagnostics = receipt.get("payload_diagnostics") if isinstance(receipt.get("payload_diagnostics"), dict) else {}
    dependency_inputs = receipt.get("dependency_inputs") if isinstance(receipt.get("dependency_inputs"), dict) else {}
    runtime_security_claims = receipt.get("runtime_security_claims")
    builder_sha = receipt.get("builder_sha") if type(receipt.get("builder_sha")) is str else ""
    expected_contracts = {str(item) for item in receipt.get("expected_contracts") or []}
    repository = str(requirement.get("repository") or "")
    workflow = str(requirement.get("workflow") or "")
    signer_workflow = str(requirement.get("signer_workflow") or "")
    required_adapters = {str(item) for item in requirement.get("required_adapters") or []}
    allowed_refs = {str(item) for item in requirement.get("allowed_refs") or []}
    generated_at = None
    generated_at = parse_utc_timestamp(receipt.get("generated_at"))
    try:
        max_age = dt.timedelta(hours=float(requirement.get("max_age_hours") or 24))
    except (TypeError, ValueError):
        max_age = dt.timedelta(0)
    now = dt.datetime.now(dt.timezone.utc)
    checks = {
        "contract": receipt.get("contract_id") == "commercial_ci_command_receipt_v1",
        "gate": receipt.get("gate_id") == requirement.get("gate_id"),
        "command_id": receipt.get("command_id") == requirement.get("command_id"),
        "subject_sha": bool(subject_sha) and receipt.get("subject_sha") == subject_sha,
        "builder_sha": SHA_RE.fullmatch(builder_sha) is not None,
        "workflow": bool(workflow) and github_run.get("workflow") == workflow,
        "repository": bool(repository) and github_run.get("repository") == repository,
        "ref": github_run.get("ref") == "refs/heads/main"
        and (not allowed_refs or "refs/heads/main" in allowed_refs),
        "nonlocal_run": str(github_run.get("run_id") or "").isdigit(),
        "run_attempt": str(github_run.get("run_attempt") or "").isdigit(),
        "generated_at": generated_at is not None,
        "fresh": generated_at is not None
        and max_age > dt.timedelta(0)
        and now - max_age <= generated_at <= now + dt.timedelta(minutes=5),
        "exact_worktree": worktree_clean,
        "command": external_runtime_command_valid(raw_command),
        "adapters": bool(required_adapters) and adapters == required_adapters,
        "expected_contract": requirement.get("expected_contract") in expected_contracts,
        "evidence_complete": receipt.get("evidence_complete") is True,
        "payload_ok": receipt.get("payload_ok") is True,
        "not_skipped": receipt.get("skipped_evidence") is False,
        "exit_zero": receipt.get("exit_code") == 0,
        "no_failures": receipt.get("failures") == [],
        "no_missing_contracts": receipt.get("missing_contracts") == [],
        "payload_failure_free": diagnostics.get("failure_count") == 0
        and diagnostics.get("failure_hashes") == []
        and diagnostics.get("error_codes") == [],
        "hash_only": receipt.get("raw_output_stored") is False
        and HASH_RE.fullmatch(str(receipt.get("stdout_sha256") or "")) is not None
        and HASH_RE.fullmatch(str(receipt.get("stderr_sha256") or "")) is not None,
        "credentials_omitted": receipt.get("credentials_stored") is False,
        "dependency_identity": HASH_RE.fullmatch(str(dependency_inputs.get("inputs_sha256") or "")) is not None,
        "runtime_security_claims": runtime_security_claims_valid(runtime_security_claims, required_adapters),
    }
    failures.extend(name for name, ok in checks.items() if not ok)
    attestation_verified = False
    receipt_sha256 = hashlib.sha256(raw).hexdigest() if raw else ""
    if attestation_file_failure or receipt_file_failure:
        pass
    elif not repository or not signer_workflow or not subject_sha or not builder_sha or not raw or not attestation_raw:
        failures.append("attestation_policy_incomplete")
    else:
        try:
            predicate_type = str(requirement.get("predicate_type") or "")
            source_ref = "refs/heads/main"
            with tempfile.TemporaryDirectory(prefix="agentops-attestation-snapshot-") as snapshot_value:
                snapshot_dir = Path(snapshot_value)
                os.chmod(snapshot_dir, 0o700)
                receipt_snapshot = snapshot_dir / "receipt.json"
                attestation_snapshot = snapshot_dir / "attestation.json"
                write_owner_only_snapshot(receipt_snapshot, raw)
                write_owner_only_snapshot(attestation_snapshot, attestation_raw)
                verify_command = [
                    "gh",
                    "attestation",
                    "verify",
                    str(receipt_snapshot),
                    "--repo",
                    repository,
                    "--bundle",
                    str(attestation_snapshot),
                    "--signer-workflow",
                    signer_workflow,
                    "--signer-digest",
                    builder_sha,
                    "--source-digest",
                    builder_sha,
                    "--source-ref",
                    source_ref,
                    "--format",
                    "json",
                ]
                if predicate_type:
                    verify_command.extend(["--predicate-type", predicate_type])
                verified = subprocess.run(
                    verify_command,
                    cwd=ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=30,
                    check=False,
                )
            verified_payload = json.loads(verified.stdout) if verified.returncode == 0 else []
            attestation_verified = (
                isinstance(verified_payload, list)
                and len(verified_payload) > 0
                and all(
                    isinstance(item, dict)
                    and isinstance(item.get("verificationResult"), dict)
                    and isinstance(item["verificationResult"].get("statement"), dict)
                    and statement_binds_receipt_sha256(
                        item["verificationResult"]["statement"],
                        receipt_sha256,
                    )
                    and (
                        not predicate_type
                        or item["verificationResult"]["statement"].get("predicateType") == predicate_type
                    )
                    for item in verified_payload
                )
            )
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            attestation_verified = False
        if not attestation_verified:
            failures.append("attestation_verification_failed")
    github_run_verified = False
    github_run_time_bound = False
    if (
        not receipt_file_failure
        and not attestation_file_failure
        and repository
        and builder_sha
        and str(github_run.get("run_id") or "").isdigit()
    ):
        try:
            run_lookup = subprocess.run(
                [
                    "gh",
                    "api",
                    f"repos/{repository}/actions/runs/{github_run['run_id']}",
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            run_payload = json.loads(run_lookup.stdout) if run_lookup.returncode == 0 else {}
            run_started_at = parse_utc_timestamp(run_payload.get("run_started_at"))
            run_updated_at = parse_utc_timestamp(run_payload.get("updated_at"))
            github_run_time_bound = (
                generated_at is not None
                and run_started_at is not None
                and run_updated_at is not None
                and run_started_at <= run_updated_at
                and run_started_at - GITHUB_RUN_TIME_TOLERANCE
                <= generated_at
                <= run_updated_at + GITHUB_RUN_TIME_TOLERANCE
            )
            github_run_verified = (
                isinstance(run_payload, dict)
                and run_payload.get("status") == "completed"
                and run_payload.get("conclusion") == "success"
                and run_payload.get("head_sha") == builder_sha
                and run_payload.get("run_attempt") == int(str(github_run.get("run_attempt") or "0"))
                and run_payload.get("event") == "workflow_dispatch"
                and run_payload.get("head_branch") == "main"
                and run_payload.get("name") == workflow
                and str(run_payload.get("path") or "").startswith(
                    ".github/workflows/commercial-real-runtime-acceptance.yml@"
                )
                and isinstance(run_payload.get("head_repository"), dict)
                and run_payload["head_repository"].get("full_name") == repository
                and github_run_time_bound
            )
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError, ValueError):
            github_run_verified = False
    if not github_run_verified:
        failures.append("github_run_verification_failed")
    if not github_run_time_bound:
        failures.append("github_run_time_binding_failed")
    return {
        "provided": True,
        "valid": not failures,
        "failures": sorted(set(failures)),
        "subject_sha": receipt.get("subject_sha"),
        "builder_sha": builder_sha or None,
        "receipt_sha256": receipt_sha256 or None,
        "attestation_verified": attestation_verified,
        "github_run_verified": github_run_verified,
        "release_authority": not failures,
        "source": "external_uncommitted_github_actions_attested_artifact",
    }


def route_naming_decision_semantics_ok() -> bool:
    decision = read_json("docs/UI_ROUTE_NAMING_DECISION.json")
    if decision.get("contract_id") != "ui_route_naming_decision_v1":
        return False
    if decision.get("status") != "accepted_admin_operations_workspace_redirect_retirement":
        return False
    policy = decision.get("policy") or {}
    if policy.get("legacy_namespace") != "/admin" or policy.get("target_namespace") != "/workspace":
        return False
    if policy.get("alias_contract") != "ui_legacy_route_alias_v1":
        return False
    if policy.get("navigation_inventory_contract") != "ui_navigation_inventory_v1":
        return False
    if policy.get("retirement_packet_contract") != "ui_route_retirement_packet_v1":
        return False
    if policy.get("admin_operations_contract") != "ui_admin_operations_route_retirement_v1":
        return False
    if policy.get("retirement_allowed_by_default") is not False:
        return False
    if policy.get("redirects_required_before_retirement") is not True:
        return False
    required = {
        "task_detail": ("/admin/tasks/:id", "/workspace/tasks/:taskId", "/workspace/tasks/:id", "redirects_to_target_route"),
        "run_ledger": ("/admin/runs", "/workspace/runs", "/workspace/runs", "redirects_to_target_route"),
        "run_detail": ("/admin/runs/:id", "/workspace/runs/:runId", "/workspace/runs/:id", "redirects_to_target_route"),
        "agent_detail": ("/admin/agents/:id", "/workspace/agents/:agentId", "/workspace/agents/:id", "not_required_for_vite_only_legacy_alias"),
        "evaluation_room": ("/admin/evaluations", "/workspace/evaluations", "/workspace/evaluations", "not_required_for_vite_only_legacy_alias"),
        "tool_calls": ("/admin/toolcalls", "/workspace/tool-calls", "/workspace/tool-calls", "not_required_for_vite_only_legacy_alias"),
        "runtime_connectors": ("/admin/connectors", "/workspace/connectors", "/workspace/connectors", "not_required_for_vite_only_legacy_alias"),
        "external_bases_notion": ("/admin/bases/notion", "/workspace/external-bases/notion", "/workspace/external-bases/notion", "not_required_for_vite_only_legacy_alias"),
        "template_switching": ("/admin/templates", "/workspace/templates", "/workspace/templates", "not_required_for_vite_only_legacy_alias"),
        "audit": ("/admin/audit", "/workspace/audit", "/workspace/audit", "not_required_for_vite_only_legacy_alias"),
    }
    if set(policy.get("executed_route_retirement_ids") or []) != set(required):
        return False
    required_cutover = {
        "route_level_read_model_parity",
        "vite_and_next_browser_snapshot_parity",
        "backward_compatible_redirect_or_alias",
        "navigation_inventory_update",
        "explicit_route_retirement_commit",
    }
    pairs = {str(pair.get("id")): pair for pair in decision.get("route_pairs") or [] if isinstance(pair, dict)}
    for pair_id, (legacy, target, vite_target, alias_status) in required.items():
        pair = pairs.get(pair_id) or {}
        if pair.get("legacy_route") != legacy or pair.get("target_route") != target:
            return False
        if not file_contains("ui/start-building-app/src/app/App.tsx", vite_target):
            return False
        if pair.get("next_alias_status") != alias_status:
            return False
        if "backward_compatible_redirect_or_alias" not in set(pair.get("cutover_evidence") or []):
            return False
        if "canonical_navigation_inventory_verified" not in set(pair.get("cutover_evidence") or []):
            return False
        if "retirement_packet_executed" not in set(pair.get("cutover_evidence") or []):
            return False
        if "vite_primary_links_migrated_to_workspace" not in set(pair.get("cutover_evidence") or []):
            return False
        if pair_id not in {"task_detail", "run_ledger", "run_detail"} and "admin_operations_route_retirement_verified" not in set(pair.get("cutover_evidence") or []):
            return False
        if set(pair.get("remaining_cutover_requires") or []):
            return False
        if pair.get("retirement_allowed") is not True:
            return False
        if not required_cutover.issubset(set(pair.get("cutover_requires") or [])):
            return False
    return True


def status_paths() -> list[str]:
    ok, output = run_git(["status", "--short"])
    if not ok or not output:
        return []
    paths = []
    for line in output.splitlines():
        raw = line[2:].strip()
        if " -> " in raw:
            raw = raw.split(" -> ", 1)[1].strip()
        paths.append(raw.strip('"'))
    return paths


def blocked_status_paths(paths: list[str]) -> list[str]:
    blocked = []
    for path in paths:
        normalized = path.replace("\\", "/")
        with_slashes = f"/{normalized}"
        if any(part in normalized or part in with_slashes for part in BLOCKED_PATH_PARTS):
            blocked.append(path)
            continue
        if any(normalized.endswith(suffix) for suffix in BLOCKED_SUFFIXES):
            blocked.append(path)
    return blocked


def check(name: str, ok: bool, detail: str, command: str | None = None) -> dict:
    item = {
        "name": name,
        "ok": bool(ok),
        "detail": detail,
    }
    if command:
        item["command"] = command
    return item


def main() -> int:
    parser = argparse.ArgumentParser(description="Check commercial migration engineering and release readiness.")
    parser.add_argument(
        "--human-memory-runtime-receipt",
        default=os.environ.get("AGENTOPS_HUMAN_MEMORY_RUNTIME_RECEIPT"),
        help="External hash-only exact-head receipt from commercial-real-runtime-acceptance.",
    )
    parser.add_argument(
        "--human-memory-runtime-attestation",
        default=os.environ.get("AGENTOPS_HUMAN_MEMORY_RUNTIME_ATTESTATION"),
        help="Offline GitHub/Sigstore attestation bundle for the exact-head Runtime receipt.",
    )
    args = parser.parse_args()
    branch_ok, branch = run_git(["branch", "--show-current"])
    sha_ok, subject_sha = run_git(["rev-parse", "HEAD"])
    subject_sha = subject_sha.lower() if sha_ok and SHA_RE.fullmatch(subject_sha.lower()) else ""
    paths = status_paths()
    blocked_paths = blocked_status_paths(paths)

    required_docs = [
        "docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md",
        "docs/PRICING_AND_ENTITLEMENT_DRAFT.md",
        "docs/TECHNICAL_SOLUTION.md",
        "docs/PARALLEL_PRODUCT_DELIVERY_BRANCH_PLAN.md",
        "docs/CODEX_NEXTJS_HANDOFF_PROMPT.md",
        "docs/STORAGE_BOUNDARY_MAP.md",
        "docs/POSTGRES_PARITY_CONTRACT.md",
        "docs/RELEASE_EVIDENCE_PACKET.md",
        "docs/RELEASE_EVIDENCE_PACKET.json",
        "docs/RELEASE_FREEZE_PROTOCOL.md",
        "docs/RELEASE_FREEZE_PROTOCOL.json",
        "docs/MERGE_READINESS_STATUS.md",
        "docs/MERGE_READINESS_STATUS.json",
        "docs/COMMERCIAL_EVIDENCE_RECEIPTS.md",
        "docs/COMMERCIAL_EVIDENCE_RECEIPTS.json",
        "docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md",
        "docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json",
        "docs/COMMERCIAL_HANDOFF_STATUS.md",
        "docs/COMMERCIAL_HANDOFF_STATUS.json",
        "docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.md",
        "docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json",
        "docs/UI_ROUTE_NAMING_DECISION.md",
        "docs/UI_ROUTE_NAMING_DECISION.json",
        "docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.md",
        "docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json",
        "docs/HUMAN_MEMORY_REVIEW_RELEASE_BLOCKERS.json",
    ]
    required_stack = [
        "server.py",
        "agentops_mis_cli/agentops.py",
        "sql/schema.sql",
        "config/entitlements.example.json",
        "ui/start-building-app/package.json",
        "ui/next-app/package.json",
    ]
    human_memory_blockers = read_json("docs/HUMAN_MEMORY_REVIEW_RELEASE_BLOCKERS.json")
    trusted_runtime_workflow_path = ROOT / TRUSTED_RUNTIME_WORKFLOW_PATH
    trusted_runtime_workflow_text = (
        trusted_runtime_workflow_path.read_text(encoding="utf-8", errors="replace")
        if trusted_runtime_workflow_path.exists()
        else ""
    )
    trusted_runtime_workflow_contract_failures = (
        trusted_real_runtime_workflow_failures(trusted_runtime_workflow_text)
    )
    trusted_runtime_blocker_failures = trusted_runtime_blocker_contract_failures(
        human_memory_blockers
    )
    runtime_receipt = validate_external_runtime_receipt(
        args.human_memory_runtime_receipt,
        args.human_memory_runtime_attestation,
        subject_sha,
        not paths,
        human_memory_blockers.get("external_runtime_receipt_requirement") or {},
    )
    human_memory_open_blockers = [
        item
        for item in human_memory_blockers.get("open_blockers") or []
        if isinstance(item, dict) and item.get("status") == "open"
    ]
    human_memory_declared_blocker_ids = {
        str(item.get("id"))
        for item in human_memory_open_blockers
    }
    human_memory_effective_open_blockers = [
        item
        for item in human_memory_open_blockers
        if item.get("id") != "exact_head_real_runtime_receipt_missing" or not runtime_receipt["valid"]
    ]
    human_memory_blocker_ids = {
        str(item.get("id"))
        for item in human_memory_effective_open_blockers
    }

    checks = [
        check(
            "isolated_commercial_branch",
            branch_ok and (
                (branch.startswith("codex/") and branch != "codex/agent-gateway-kb-demo")
                or (branch == "main" and runtime_receipt["valid"])
            ),
            f"current_branch={branch or 'unknown'}",
            "git branch --show-current",
        ),
        check(
            "required_migration_docs_present",
            all((ROOT / path).exists() for path in required_docs),
            "required_docs=" + ",".join(required_docs),
        ),
        check(
            "human_memory_review_release_blockers_recorded",
            human_memory_blockers.get("contract_id") == "human_memory_review_release_blockers_v1"
            and human_memory_blockers.get("release_claim_allowed") == (not bool(human_memory_open_blockers))
            and human_memory_blockers.get("closed_loop_claim_allowed") == (not bool(human_memory_open_blockers))
            and {
                "production_api_route_ownership_incomplete",
                "trusted_proxy_ip_edge_rate_limit_required",
                "historical_audit_workspace_backfill_missing",
                "human_session_retention_job_missing",
                "human_memory_review_request_retention_policy_missing",
                "approval_decision_request_retention_policy_missing",
                "approval_expiry_reconciliation_missing",
                "typescript_approval_policy_entitlement_owner_missing",
                "production_prepared_action_resume_ownership_missing",
                "production_enrollment_issue_owner_missing",
                "ordinary_high_risk_tool_execution_receipt_missing",
                "owner_bootstrap_compiled_entry_missing",
                "trusted_real_runtime_builder_not_established",
                "trusted_runtime_identity_attestation_missing",
                "receipt_verifier_binary_trust_missing",
            }.issubset(human_memory_declared_blocker_ids)
            and (
                "exact_head_real_runtime_receipt_missing" in human_memory_declared_blocker_ids
                or runtime_receipt["valid"]
            )
            and {
                "approval_kind_binding_missing",
                "enrollment_approval_unique_binding_missing",
            }.isdisjoint(human_memory_declared_blocker_ids)
            and human_memory_blockers.get("local_precommit_observations", {}).get(
                "real_openclaw_worker_human_review_bridge_observed"
            ) is True
            and human_memory_blockers.get("local_precommit_observations", {}).get(
                "real_hermes_worker_human_review_bridge_observed"
            ) is True
            and human_memory_blockers.get("local_precommit_observations", {}).get(
                "real_openclaw_run_bound_delivery_decision_observed"
            ) is True
            and human_memory_blockers.get("local_precommit_observations", {}).get(
                "real_hermes_run_bound_delivery_decision_observed"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "approval_kind_v4_explicit_without_default"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "approval_kind_v4_immutable_and_edge_bound"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "approval_execution_binding_immutable"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "legacy_approval_kind_backfill_unclassified_fails_closed"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "enrollment_approval_unique_binding_enforced"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "customer_delivery_evidence_sealed_after_decision"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "plan_evidence_complete_tool_evaluation_artifact_set"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "plan_evidence_audit_ids_server_derived"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "external_runtime_receipt_security_claims_required"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "customer_delivery_run_unique_v5_enforced"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "customer_delivery_approval_request_typescript_postgres_owned"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "customer_delivery_approval_request_database_unique"
            ) is True
            and human_memory_blockers.get("acceptance_evidence", {}).get(
                "worker_created_delivery_approvals"
            ) is True
            and human_memory_blockers.get("acceptance_evidence", {}).get(
                "delivery_approval_creation_source"
            ) == "production_next_typescript_postgres_agent_gateway_route"
            and human_memory_blockers.get("acceptance_evidence", {}).get(
                "evidence_scope"
            ) == "local_precommit_engineering_only"
            and human_memory_blockers.get("acceptance_evidence", {}).get(
                "subject_sha"
            ) is None
            and human_memory_blockers.get("acceptance_evidence", {}).get(
                "executed_at"
            ) is None
            and human_memory_blockers.get("acceptance_evidence", {}).get(
                "receipt_id"
            ) is None
            and human_memory_blockers.get("acceptance_evidence", {}).get(
                "exact_head"
            ) is False
            and human_memory_blockers.get("acceptance_evidence", {}).get(
                "release_authority"
            ) is False
            and human_memory_blockers.get("external_runtime_receipt_requirement", {}).get(
                "contract_id"
            ) == "commercial_ci_command_receipt_v1"
            and human_memory_blockers.get("external_runtime_receipt_requirement", {}).get(
                "workflow"
            ) == "commercial-real-runtime-acceptance"
            and human_memory_blockers.get("external_runtime_receipt_requirement", {}).get(
                "repository"
            ) == "geogejoy107-jpg/agentops-mis-mvp"
            and human_memory_blockers.get("external_runtime_receipt_requirement", {}).get(
                "signer_workflow"
            ) == "geogejoy107-jpg/agentops-mis-mvp/.github/workflows/commercial-real-runtime-acceptance.yml"
            and set(human_memory_blockers.get("external_runtime_receipt_requirement", {}).get(
                "required_adapters"
            ) or []) == {"hermes", "openclaw"}
            and set(human_memory_blockers.get("external_runtime_receipt_requirement", {}).get(
                "allowed_refs"
            ) or []) == {"refs/heads/main"}
            and human_memory_blockers.get("external_runtime_receipt_requirement", {}).get(
                "max_age_hours"
            ) == 24
            and human_memory_blockers.get("external_runtime_receipt_requirement", {}).get(
                "builder_must_differ_from_candidate_authority"
            ) is True
            and not trusted_runtime_workflow_contract_failures
            and not trusted_runtime_blocker_failures
            and file_contains(
                "scripts/commercial_ci_receipt.py",
                "real_runtime_security_claims_incomplete",
            )
            and file_contains(
                "scripts/commercial_ci_receipt.py",
                "approved_customer_delivery_evidence_sealed",
            )
            and file_contains("scripts/commercial_migration_readiness.py", "gh")
            and file_contains("scripts/commercial_migration_readiness.py", "attestation")
            and human_memory_blockers.get("implemented_controls", {}).get(
                "free_local_legacy_workspace_mutation_same_origin_enforced"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "legacy_review_decisions_fail_closed"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "production_shared_python_proxy_helper_blocked"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "workspace_detail_read_routes_typescript_postgres_owned"
            ) is True
            and human_memory_blockers.get("implemented_controls", {}).get(
                "human_approval_decision_route_typescript_postgres_owned"
            ) is True,
            "the v5 approval schema and local pre-commit OpenClaw/Hermes production approval-request observations are separated from release evidence; an external exact-HEAD runtime receipt can resolve only its evidence blocker while the remaining route, expiry, entitlement, execution, ingress, audit mapping, retention, and packaging gaps stay open",
        ),
        check(
            "trusted_main_real_runtime_contract_hardened",
            not trusted_runtime_workflow_contract_failures
            and not trusted_runtime_blocker_failures,
            "workflow_failures="
            + ",".join(trusted_runtime_workflow_contract_failures)
            + ";blocker_failures="
            + ",".join(trusted_runtime_blocker_failures),
            "python3 scripts/commercial_trusted_main_readiness_smoke.py",
        ),
        check(
            "external_exact_head_real_runtime_receipt_valid_when_provided",
            not runtime_receipt["provided"] or runtime_receipt["valid"],
            "provided=" + str(runtime_receipt["provided"]).lower()
            + ",valid=" + str(runtime_receipt["valid"]).lower()
            + ",failures=" + ",".join(runtime_receipt["failures"]),
            "python3 scripts/commercial_migration_readiness.py --human-memory-runtime-receipt <receipt.json> --human-memory-runtime-attestation <attestation.json>",
        ),
        check(
            "current_product_stack_present",
            all((ROOT / path).exists() for path in required_stack),
            "required_stack=" + ",".join(required_stack),
        ),
        check(
            "no_big_bang_decision_recorded",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "no big-bang rewrite")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "bounded migration rollback"),
            "commercial migration advances route by route with explicit rollback instead of a big-bang rewrite",
        ),
        check(
            "production_readiness_surface_exists",
            file_contains("server.py", "/api/security/production-readiness")
            and file_contains("agentops_mis_cli/agentops.py", "production-readiness")
            and file_contains("scripts/production_auth_fail_closed_smoke.py", "--configured-production-fixture")
            and file_contains("scripts/production_auth_fail_closed_smoke.py", "AGENTOPS_DEPLOYMENT_MODE")
            and file_contains("scripts/production_auth_fail_closed_smoke.py", "read_only_hash_checked")
            and file_contains("scripts/security_production_readiness_smoke.py", "--configured-production-fixture")
            and file_contains("scripts/security_production_readiness_smoke.py", "AGENTOPS_DEPLOYMENT_MODE")
            and file_contains("scripts/security_production_readiness_smoke.py", "validate_configured_blocked")
            and file_contains("scripts/security_production_readiness_smoke.py", "validate_configured_ready")
            and file_contains("scripts/security_production_readiness_smoke.py", "prod-api-key-fixture")
            and file_contains("scripts/security_production_readiness_smoke.py", "admin_key_list_status")
            and file_contains("scripts/security_production_readiness_smoke.py", "db_dump_hash"),
            "server API, CLI production-readiness command, and configured production blocked/ready fixture are present",
        ),
        check(
            "gate2_isolated_governance_fixtures_exist",
            file_contains("scripts/smoke_isolated_server.py", "isolated_server")
            and file_contains("scripts/agent_gateway_scope_matrix_smoke.py", "--isolated-fixture")
            and file_contains("scripts/agent_gateway_scope_matrix_smoke.py", "submit_verified_agent_plan")
            and file_contains("scripts/workspace_isolation_smoke.py", "--isolated-fixture")
            and file_contains("scripts/workspace_isolation_smoke.py", "submit_verified_agent_plan")
            and file_contains("scripts/workspace_rbac_governance_smoke.py", "--isolated-fixture")
            and file_contains("scripts/workspace_memory_session_governance_smoke.py", "--isolated-fixture"),
            "Gate 2 workspace/scope governance smokes can start isolated temporary servers and avoid live ledger contamination",
        ),
        check(
            "local_runtime_acceptance_surface_exists",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "local_runtime_acceptance.py --live-openclaw --live-hermes")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "--openclaw-timeout 300 --hermes-timeout 600 --request-timeout 720")
            and file_contains("scripts/local_runtime_acceptance.py", '"agent-plan"')
            and file_contains("scripts/local_runtime_acceptance.py", '"plan-evidence"')
            and file_contains("scripts/local_runtime_acceptance.py", "--openclaw-timeout")
            and file_contains("scripts/local_runtime_acceptance.py", "--hermes-timeout")
            and file_contains("scripts/local_runtime_acceptance.py", "--request-timeout")
            and file_contains("scripts/local_runtime_acceptance.py", "AGENTOPS_CONFIG")
            and file_contains("scripts/local_runtime_acceptance.py", "env.pop(\"AGENTOPS_API_KEY\", None)")
            and file_contains("scripts/local_runtime_acceptance.py", "Agent Plan verification did not pass")
            and file_contains("scripts/local_runtime_acceptance.py", "Plan evidence manifest did not verify")
            and file_contains("scripts/local_runtime_acceptance.py", "prepared_runtime_prepare_payload")
            and file_contains("scripts/local_runtime_acceptance.py", 'payload = {"confirm_run": True}')
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "server-generated task/run/tool-call/approval/prepared-action IDs")
            and file_contains("scripts/local_runtime_acceptance.py", "prepared_action_status")
            and file_contains("scripts/local_runtime_acceptance.py", '"prepared_action_id"')
            and file_contains("scripts/local_runtime_acceptance.py", "Prepared runtime probe did not consume")
            and file_contains("scripts/local_runtime_acceptance.py", "runtime_failure_evidence")
            and file_contains("scripts/local_runtime_acceptance.py", "run_readback")
            and (ROOT / "scripts" / "local_runtime_acceptance_failure_readback_smoke.py").exists()
            and (ROOT / "scripts" / "local_runtime_acceptance_diagnostics.py").exists()
            and (ROOT / "scripts" / "local_runtime_acceptance_diagnostics_smoke.py").exists()
            and (ROOT / "scripts" / "local_runtime_acceptance.py").exists(),
            "Real Hermes/OpenClaw runtime acceptance requires Agent Plan-gated run start, verified plan-evidence, unique prepared actions, consumed prepared actions, and CI-safe failed-run diagnostics",
        ),
        check(
            "entitlement_direction_recorded",
            file_contains("docs/PRICING_AND_ENTITLEMENT_DRAFT.md", "Enterprise / BYOC")
            and file_contains("docs/PRICING_AND_ENTITLEMENT_DRAFT.md", "Free Local"),
            "edition ladder exists in pricing/entitlement draft",
        ),
        check(
            "entitlement_fail_closed_surface_exists",
            file_contains("server.py", "/api/commercial/entitlements")
            and file_contains("agentops_mis_cli/agentops.py", "commercial_entitlements")
            and file_contains("server.py", "COMMERCIAL_FAIL_CLOSED_CAPABILITIES")
            and file_contains("server.py", '"approval_policies"')
            and file_contains("scripts/commercial_entitlements_smoke.py", "validate_entitlement_audit")
            and file_contains("scripts/commercial_entitlements_smoke.py", "validate_pro_template_run")
            and file_contains("scripts/commercial_entitlements_smoke.py", "fail_closed")
            and file_contains("scripts/team_entitlement_enrollment_smoke.py", "validate_downgrade_issue_block")
            and file_contains("scripts/team_entitlement_enrollment_smoke.py", "team_governance")
            and (ROOT / "scripts" / "commercial_entitlements_smoke.py").exists()
            and (ROOT / "scripts" / "team_entitlement_enrollment_smoke.py").exists(),
            "commercial entitlement API/CLI has fail-closed gates, audit evidence, Pro allow-path, and Team enrollment-policy smoke coverage",
        ),
        check(
            "nextjs_is_gated_not_immediate",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "UI/API Parity Before Next.js"),
            "Next.js migration is behind a parity gate",
        ),
        check(
            "nextjs_parity_surface_exists",
            file_contains("ui/next-app/package.json", '"next": "16.2.11"')
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "AGENTOPS_API_BASE")
            and file_contains("ui/next-app/src/lib/mis.ts", "/dashboard/metrics")
            and file_contains("ui/next-app/src/lib/mis.ts", "/storage/backend-status")
            and file_contains("ui/next-app/src/lib/mis.ts", "/tool-calls")
            and file_contains("ui/next-app/src/lib/mis.ts", "/evaluations")
            and file_contains("ui/next-app/src/lib/mis.ts", "/runtime-connectors")
            and file_contains("ui/next-app/src/lib/mis.ts", "/integrations/notion/status")
            and file_contains("ui/next-app/src/lib/mis.ts", "/agents/${encodeURIComponent(agentId)}/performance")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerStorageBackendStatus")
            and file_contains("ui/next-app/src/components/AgentDetailPage.tsx", "AgentDetailParityPage")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "Storage backend migration gate")
            and file_contains("ui/next-app/src/components/ToolCallPages.tsx", "ToolCallsParityPage")
            and file_contains("ui/next-app/src/components/EvaluationPages.tsx", "EvaluationsParityPage")
            and file_contains("ui/next-app/src/components/ConnectorPages.tsx", "RuntimeConnectorsParityPage")
            and file_contains("ui/next-app/src/components/NotionBasePage.tsx", "NotionExternalBaseParityPage")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", "/workspace/tool-calls")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", "/workspace/evaluations")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", "/workspace/connectors")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", "/workspace/external-bases/notion")
            and file_contains("scripts/nextjs_agent_gateway_task_proxy_smoke.py", "nextjs_agent_gateway_task_proxy_v1")
            and file_contains("scripts/nextjs_agent_gateway_task_proxy_smoke.py", "/api/mis/agent-gateway/tasks")
            and file_contains("scripts/nextjs_agent_gateway_task_proxy_smoke.py", "no_token_status == 401")
            and file_contains("scripts/nextjs_agent_gateway_task_proxy_smoke.py", "direct_api_matches_next_proxy")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_agent_gateway_task_proxy_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_agent_gateway_cli_worker_dogfood_v1")
            and file_contains("scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py", "nextjs_agent_gateway_cli_worker_dogfood_v1")
            and file_contains("scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py", "/api/mis/agent-gateway/tasks")
            and file_contains("scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py", "scripts/agent_worker.py --once --adapter mock")
            and file_contains("scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py", "plan-evidence-manifests/:id/verify")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "mock_only_next_parity")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "isWorkerDispatchPath")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "force_release_not_allowed_next_parity")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "isWorkerReleasePath")
            and file_contains("ui/next-app/src/lib/mis.ts", "/workers/local/dispatch-once")
            and file_contains("ui/next-app/src/lib/mis.ts", "mock_only_next_parity")
            and file_contains("ui/next-app/src/lib/mis.ts", "/workers/tasks/release")
            and file_contains("ui/next-app/src/lib/mis.ts", "/workers/local/start")
            and file_contains("ui/next-app/src/lib/mis.ts", "/workers/local/stop")
            and file_contains("ui/next-app/src/lib/mis.ts", "/workers/local/restart")
            and file_contains("ui/next-app/src/lib/mis.ts", "/agent-gateway/enrollments")
            and file_contains("ui/next-app/src/lib/mis.ts", "/agent-gateway/enrollment/policy-preview")
            and file_contains("ui/next-app/src/lib/mis.ts", "/agent-gateway/enrollment/request")
            and file_contains("ui/next-app/src/components/AgentsParityPage.tsx", "dispatchLocalWorkerOnce")
            and file_contains("ui/next-app/src/components/AgentsParityPage.tsx", "releaseWorkerTask")
            and file_contains("ui/next-app/src/components/AgentsParityPage.tsx", "startMockWorkerDaemon")
            and file_contains("ui/next-app/src/components/AgentsParityPage.tsx", "stopMockWorkerDaemon")
            and file_contains("ui/next-app/src/components/AgentsParityPage.tsx", "requestAgentGatewayEnrollment")
            and file_contains("ui/next-app/app/workspace/agents/dispatch-once/route.ts", "/workers/local/dispatch-once")
            and file_contains("ui/next-app/app/workspace/agents/dispatch-once/route.ts", "mock_only_next_parity")
            and file_contains("ui/next-app/app/workspace/agents/release-task/route.ts", "/workers/tasks/release")
            and file_contains("ui/next-app/app/workspace/agents/release-task/route.ts", "task_id_required")
            and file_contains("ui/next-app/app/workspace/agents/daemon-control/route.ts", "/workers/local/${action}")
            and file_contains("ui/next-app/app/workspace/agents/daemon-control/route.ts", "mock_daemon_only_next_parity")
            and file_contains("ui/next-app/app/workspace/agents/enrollment-request/route.ts", "/agent-gateway/enrollment/request")
            and file_contains("ui/next-app/app/workspace/agents/enrollment-request/route.ts", "invalid_scopes")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "enrollment_token_issue_not_allowed_next_parity")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "mock_daemon_only_next_parity")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "live_worker_daemon_not_allowed_next_parity")
            and file_contains("scripts/nextjs_worker_dispatch_once_smoke.py", "nextjs_worker_dispatch_once_v1")
            and file_contains("scripts/nextjs_worker_dispatch_once_smoke.py", "/api/mis/workers/local/dispatch-once")
            and file_contains("scripts/nextjs_worker_dispatch_once_smoke.py", "mock_only_next_parity")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "isCustomerWorkerWorkflowPath")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "customerWorkerWorkflowGuard")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "prepared_action_required")
            and file_contains("ui/next-app/app/workspace/pixel-office/page.tsx", "PixelOfficeLivePage")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "Pixel Operating Map")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "Local brief controls")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "/workspace/pixel-office/local-brief")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "commercial-safe geometry")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "live runtime disabled")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "live brief approval-gated")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "Resume approved brief")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "isLocalBriefPath")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "prepared_action_required")
            and file_contains("ui/next-app/app/workspace/pixel-office/local-brief/route.ts", "/workflows/local-brief")
            and file_contains("ui/next-app/app/workspace/pixel-office/local-brief/route.ts", "prepared_action_id")
            and file_contains("ui/next-app/app/workspace/pixel-office/local-brief/route.ts", "approval_required")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", "/workspace/pixel-office")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerDashboardMetrics")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerAgents")
            and file_contains("scripts/nextjs_pixel_office_floor_smoke.py", "nextjs_pixel_office_floor_v1")
            and file_contains("scripts/nextjs_pixel_office_floor_smoke.py", "/workspace/pixel-office")
            and file_contains("scripts/nextjs_pixel_office_floor_smoke.py", "Owner dispatch workflow")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "owner-dispatch-workflow")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "template intake /workspace/dispatch")
            and file_contains("ui/next-app/src/components/PixelOfficePage.tsx", "delivery reports /workspace/reports")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "control-tower-live-metrics")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "control-tower-split-proof")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "/workspace/agents agent performance drilldown")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "control-tower-runtime-health")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "control-tower-openclaw-imports")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "control-tower-task-status")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "control-tower-cost-leaders")
            and file_contains("scripts/nextjs_control_tower_parity_smoke.py", "nextjs_control_tower_parity_v1")
            and file_contains("scripts/nextjs_control_tower_parity_smoke.py", "/api/mis/dashboard/metrics")
            and file_contains("scripts/nextjs_control_tower_parity_smoke.py", "/api/mis/agents")
            and file_contains("scripts/nextjs_control_tower_parity_smoke.py", "/api/mis/security/production-readiness")
            and file_contains("scripts/nextjs_control_tower_parity_smoke.py", "/api/mis/local/readiness")
            and file_contains("scripts/nextjs_control_tower_parity_smoke.py", "/api/mis/storage/backend-status")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-task/route.ts", "/workflows/customer-task")
            and file_contains("ui/next-app/app/workspace/dispatch/template-job/route.ts", "/workflows/customer-task-templates/submit")
            and file_contains("ui/next-app/app/workspace/dispatch/page.tsx", "loadServerAgents")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "Owner task composer")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "/workspace/dispatch/customer-task")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "/workspace/dispatch/template-job")
            and file_contains("ui/next-app/app/workspace/templates/page.tsx", "TemplateSwitchingPage")
            and file_contains("ui/next-app/app/workspace/templates/page.tsx", "loadServerTemplatePackages")
            and file_contains("ui/next-app/app/workspace/templates/page.tsx", "loadServerBases")
            and file_contains("ui/next-app/app/workspace/templates/migration-preview/route.ts", "/migration/preview")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "Template Switching")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "template-switching-live-read-model")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "template-base-switching-plan")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "template-core-ledger-protection")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "/template-packages")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "/bases")
            and file_contains("ui/next-app/src/components/TemplateSwitchingPage.tsx", "/migration/preview")
            and file_contains("ui/next-app/src/lib/mis.ts", "loadTemplatePackages")
            and file_contains("ui/next-app/src/lib/mis.ts", "loadTemplateBindings")
            and file_contains("ui/next-app/src/lib/mis.ts", "loadBases")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerTemplatePackages")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerTemplateBindings")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerBases")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", "/workspace/templates")
            and file_contains("scripts/nextjs_template_switching_smoke.py", "nextjs_template_switching_parity_v1")
            and file_contains("scripts/nextjs_template_switching_smoke.py", "/workspace/templates")
            and file_contains("scripts/nextjs_template_switching_smoke.py", "/api/mis/template-packages")
            and file_contains("scripts/nextjs_template_switching_smoke.py", "/api/mis/bases")
            and file_contains("scripts/nextjs_template_switching_smoke.py", "/api/mis/migration/preview")
            and file_contains("scripts/nextjs_pixel_office_dispatch_smoke.py", "nextjs_pixel_office_dispatch_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_pixel_office_dispatch_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_template_switching_parity_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_control_tower_parity_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "split-route control tower proof")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "GET /template-packages")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "GET /template-bindings")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "GET /bases")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "POST /migration/preview")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "pixel_office_dispatch_retirement_evidence_v1")
            and file_contains("scripts/local_brief_prepared_action_smoke.py", "local_brief_prepared_action_v1")
            and file_contains("scripts/nextjs_local_brief_smoke.py", "nextjs_local_brief_v1")
            and file_contains("scripts/nextjs_local_brief_smoke.py", "/api/mis/workflows/local-brief")
            and file_contains("scripts/nextjs_local_brief_smoke.py", "/workspace/pixel-office/local-brief")
            and file_contains("scripts/nextjs_local_brief_smoke.py", "prepared_action_exact_resume")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_pixel_office_floor_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_local_brief_v1")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-worker/route.ts", "/workflows/customer-worker-task")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-worker/route.ts", "prepared_action_id")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-worker/route.ts", "request_hash")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "Customer worker dispatch")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "Resume approved worker")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "/workspace/dispatch/customer-worker")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-worker-job/route.ts", "/workflows/customer-worker-task/submit")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-worker-job/route.ts", "prepared_action_id")
            and file_contains("ui/next-app/app/workspace/dispatch/customer-worker-job/route.ts", "request_hash")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "Async worker jobs")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "Resume approved job")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "Prepared worker actions")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "customer-worker-prepared-actions")
            and file_contains("ui/next-app/src/components/DispatchPage.tsx", "/workspace/dispatch/customer-worker-job")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerWorkflowJobs")
            and file_contains("ui/next-app/src/lib/misServer.ts", "/workflows/jobs?limit=")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerCustomerWorkerPreparedActions")
            and file_contains("ui/next-app/src/lib/misServer.ts", "/workflows/customer-worker-prepared-actions?limit=")
            and file_contains("ui/next-app/src/lib/mis.ts", "CustomerWorkerPreparedActionListPayload")
            and file_contains("ui/next-app/src/lib/mis.ts", "resume_form")
            and file_contains("scripts/nextjs_customer_worker_dispatch_smoke.py", "nextjs_customer_worker_dispatch_v1")
            and file_contains("scripts/nextjs_customer_worker_dispatch_smoke.py", "/api/mis/workflows/customer-worker-task")
            and file_contains("scripts/nextjs_customer_worker_dispatch_smoke.py", "/workspace/dispatch/customer-worker")
            and file_contains("scripts/nextjs_customer_worker_dispatch_smoke.py", "adapter_invalid")
            and file_contains("scripts/nextjs_customer_worker_dispatch_smoke.py", "plan-evidence-manifests/:id/verify")
            and file_contains("scripts/nextjs_customer_worker_async_job_smoke.py", "nextjs_customer_worker_async_job_v1")
            and file_contains("scripts/nextjs_customer_worker_async_job_smoke.py", "/api/mis/workflows/customer-worker-task/submit")
            and file_contains("scripts/nextjs_customer_worker_async_job_smoke.py", "/workspace/dispatch/customer-worker-job")
            and file_contains("scripts/nextjs_customer_worker_async_job_smoke.py", "/api/mis/workflows/jobs/:job_id")
            and file_contains("scripts/nextjs_customer_worker_async_job_smoke.py", "adapter_invalid")
            and file_contains("scripts/nextjs_customer_worker_prepared_action_smoke.py", "nextjs_customer_worker_prepared_action_v1")
            and file_contains("scripts/nextjs_customer_worker_prepared_action_smoke.py", "/api/mis/workflows/customer-worker-prepared-actions")
            and file_contains("scripts/nextjs_customer_worker_prepared_action_smoke.py", "resume_form")
            and file_contains("scripts/nextjs_customer_worker_prepared_action_smoke.py", "prepared_action_request_hash_mismatch")
            and file_contains("scripts/nextjs_customer_worker_prepared_action_smoke.py", "prepared_action_already_consumed")
            and file_contains("scripts/nextjs_worker_stuck_release_smoke.py", "nextjs_worker_stuck_release_v1")
            and file_contains("scripts/nextjs_worker_stuck_release_smoke.py", "/api/mis/workers/tasks/release")
            and file_contains("scripts/nextjs_worker_stuck_release_smoke.py", "force_release_not_allowed_next_parity")
            and file_contains("scripts/nextjs_worker_daemon_control_smoke.py", "nextjs_worker_daemon_control_v1")
            and file_contains("scripts/nextjs_worker_daemon_control_smoke.py", "/api/mis/workers/local/start")
            and file_contains("scripts/nextjs_worker_daemon_control_smoke.py", "mock_daemon_only_next_parity")
            and file_contains("scripts/nextjs_enrollment_request_smoke.py", "nextjs_enrollment_request_v1")
            and file_contains("scripts/nextjs_enrollment_request_smoke.py", "/api/mis/agent-gateway/enrollment/request")
            and file_contains("scripts/nextjs_enrollment_request_smoke.py", "enrollment_token_issue_not_allowed_next_parity")
            and file_contains("scripts/nextjs_worker_gateway_lifecycle_guard_smoke.py", "nextjs_worker_gateway_lifecycle_guard_v1")
            and file_contains("scripts/nextjs_worker_gateway_lifecycle_guard_smoke.py", "/api/mis/agent-gateway/session/create")
            and file_contains("scripts/nextjs_worker_gateway_lifecycle_guard_smoke.py", "gateway_lifecycle_write_not_allowed_next_parity")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "nextjs_worker_console_parity_v1")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "/workspace/workers")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "/api/mis/workers/fleet")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "/api/mis/workers/fleet/hygiene")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "/api/mis/operator/execution-mode")
            and file_contains("scripts/operator_execution_mode_smoke.py", "operator_execution_mode_v1")
            and file_contains("scripts/operator_execution_mode_smoke.py", "/api/operator/execution-mode")
            and file_contains("scripts/operator_execution_mode_smoke.py", "agentops operator execution-mode")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "isGatewayLifecycleWritePath")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "safeGatewaySessionsPayload")
            and file_contains("ui/next-app/src/components/AgentsParityPage.tsx", "agent-gateway-session-hygiene")
            and file_contains("ui/next-app/src/components/WorkerConsolePage.tsx", "worker_console_read_model_parity")
            and file_contains("ui/next-app/src/components/WorkerConsolePage.tsx", "worker-console-hygiene-plan")
            and file_contains("ui/next-app/src/components/WorkerConsolePage.tsx", "operator-execution-mode-readback")
            and file_contains("ui/next-app/src/components/WorkerConsolePage.tsx", "worker-console-coverage-boundary")
            and file_contains("ui/next-app/src/components/WorkerConsolePage.tsx", "Agent Gateway CLI/API/MCP canonical for token issue/rotate/revoke")
            and file_contains("ui/next-app/src/components/WorkerConsolePage.tsx", "live daemon lifecycle requires CLI/API operator lane")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "Worker Console coverage boundary")
            and file_contains("scripts/nextjs_worker_console_parity_smoke.py", "Agent Gateway CLI/API/MCP canonical for token issue/rotate/revoke")
            and file_contains("server.py", "def operator_execution_mode")
            and file_contains("server.py", "/api/operator/execution-mode")
            and file_contains("agentops_mis_cli/agentops.py", "operator_execution_mode")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerWorkerFleet")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerWorkerFleetHygiene")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerOperatorExecutionMode")
            and file_contains("ui/next-app/src/lib/misServer.ts", "safeGatewaySessionsPayload")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_dispatch_once_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_pixel_office_floor_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_local_brief_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_customer_worker_dispatch_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_customer_worker_async_job_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_stuck_release_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_daemon_control_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_enrollment_request_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_gateway_lifecycle_guard_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "nextjs_worker_console_parity_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "operator_execution_mode_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "Worker Console coverage boundary")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "Agent Gateway CLI/API/MCP remains canonical")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "verify_dispatch_template_run_success")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "/workspace/workers")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "/workspace/pixel-office")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", 'write_entitlement_fixture(entitlement_path, "pro_workspace")')
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Customer project started")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", 'counts.get("tasks") == 6')
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", 'counts.get("runs") == 6')
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", 'execution_evidence.get("agent_plans") == 6')
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", 'execution_evidence.get("verified_plan_evidence_manifests") == 5')
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "report_artifact_id")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Evidence Drilldown")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Run Detail")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Task Detail")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "leaked_secret")
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "tool-calls" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "pixel-office" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "pixel-office" / "local-brief" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "[agentId]" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "dispatch-once" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "dispatch" / "customer-task" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "dispatch" / "template-job" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "templates" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "templates" / "migration-preview" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "src" / "components" / "TemplateSwitchingPage.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "dispatch" / "customer-worker" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "dispatch" / "customer-worker-job" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "release-task" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "daemon-control" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "workers" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "src" / "components" / "WorkerConsolePage.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "agents" / "enrollment-request" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "evaluations" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "connectors" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "connectors" / "trust" / "route.ts").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "external-bases" / "notion" / "page.tsx").exists()
            and (ROOT / "ui" / "next-app" / "app" / "workspace" / "external-bases" / "notion" / "export" / "route.ts").exists()
            and (ROOT / "scripts" / "nextjs_parity_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_agent_gateway_task_proxy_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_agent_gateway_cli_worker_dogfood_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_dispatch_once_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_pixel_office_floor_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_pixel_office_dispatch_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_template_switching_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_control_tower_parity_smoke.py").exists()
            and (ROOT / "scripts" / "pixel_office_dispatch_retirement_evidence_smoke.py").exists()
            and (ROOT / "docs" / "PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json").exists()
            and (ROOT / "docs" / "PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.md").exists()
            and (ROOT / "scripts" / "local_brief_prepared_action_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_local_brief_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_customer_worker_dispatch_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_customer_worker_async_job_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_customer_worker_prepared_action_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_stuck_release_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_daemon_control_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_enrollment_request_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_gateway_lifecycle_guard_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_worker_console_parity_smoke.py").exists()
            and (ROOT / "scripts" / "operator_execution_mode_smoke.py").exists()
            and (ROOT / "scripts" / "nextjs_playwright_snapshot_smoke.py").exists(),
            "parallel Next.js App Router track has API proxy, Gateway task-create proxy, CLI worker dogfood proof through the Next proxy, read-only Pixel Operating Map parity, split-route Control Tower parity across workspace/agents/governance/deployment, template/base switching readback for /template-packages, /template-bindings, /bases, and /migration/preview, local brief prepared-action exact resume with approval/hash/replay guards, covered split-route Worker Console parity across /workspace/agents and /workspace/workers with fleet/hygiene/readiness/session safety, mock worker/daemon controls, stuck release, approval-gated enrollment, operator execution-mode readback, and Agent Gateway CLI/API/MCP canonical lifecycle boundary, customer-worker prepared-action exact resume for Hermes/OpenClaw plus ledger-derived safe resume readback, async customer-worker prepared-action submit/resume plus mock job status readback, Agent Gateway session/enrollment lifecycle writes blocked at the Next proxy with safe session hygiene readback, workspace/storage/tool-call/evaluation/runtime-connector/Notion external-base/agent-detail data contracts, deployment storage gate, and browser snapshot smoke including an isolated Pro template dispatch that creates the six-task KB bot package, six run rows, report artifact, six Agent Plans, and five verified manifests",
        ),
        check(
            "pixel_office_dispatch_retirement_evidence_surface_exists",
            file_contains("docs/PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json", "pixel_office_dispatch_retirement_evidence_v1")
            and file_contains("docs/PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json", '"retirement_action": "not_executed"')
            and file_contains("docs/PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json", '"retirement_allowed": false')
            and file_contains("docs/PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.json", "explicit_route_retirement_commit")
            and file_contains("docs/PIXEL_OFFICE_DISPATCH_RETIREMENT_EVIDENCE.md", "does not retire the Vite")
            and file_contains("scripts/pixel_office_dispatch_retirement_evidence_smoke.py", "pixel_office_dispatch_retirement_evidence_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "pixel_office_dispatch_retirement_evidence_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.md", "pixel_office_dispatch_retirement_evidence_v1")
            and (ROOT / "scripts" / "pixel_office_dispatch_retirement_evidence_smoke.py").exists(),
            "Pixel Office / Dispatch has explicit route retirement evidence while keeping Vite route retirement fail-closed",
        ),
        check(
            "nextjs_commercial_release_status_surface_exists",
            file_contains("server.py", "/api/commercial/release-status")
            and file_contains("server.py", "commercial_release_status_api_v1")
            and file_contains("server.py", "COMMERCIAL_RELEASE_PROMOTION_PACKET.json")
            and file_contains("server.py", "commercial_release_promotion_packet.py --include-external-ci-evidence")
            and file_contains("server.py", "COMMERCIAL_RELEASE_GRADE_RECEIPT_PLAN.json")
            and file_contains("server.py", "commercial_release_grade_receipt_plan.py --include-external-ci-evidence")
            and file_contains("server.py", "COMMERCIAL_RELEASE_GRADE_RERUN_BUNDLE.json")
            and file_contains("server.py", "commercial_release_grade_rerun_bundle.py --include-external-ci-evidence")
            and file_contains("server.py", "/api/commercial/release-grade-rerun-bundle")
            and file_contains("server.py", "commercial_release_grade_rerun_bundle_status")
            and file_contains("server.py", "phase_gate_rerun_bundles")
            and file_contains("server.py", "COMMERCIAL_RELEASE_GRADE_RECEIPT_RECORDING.json")
            and file_contains("server.py", "commercial_release_grade_receipt_recording.py --include-external-ci-evidence")
            and file_contains("server.py", "confirmed_release_grade_receipt_recording")
            and file_contains("server.py", "/api/commercial/release-grade-receipt-recording")
            and file_contains("server.py", "commercial_release_grade_receipt_recording_status")
            and file_contains("server.py", "phase_gate_recording_requests")
            and file_contains("server.py", "commercial_release_external_ci_evidence")
            and file_contains("server.py", "include_external_ci_evidence")
            and file_contains("server.py", "network_called")
            and file_contains("ui/next-app/src/lib/mis.ts", "CommercialReleaseStatusPayload")
            and file_contains("ui/next-app/src/lib/mis.ts", "CommercialReleaseGradeRerunBundlePayload")
            and file_contains("ui/next-app/src/lib/mis.ts", "CommercialReleaseGradeReceiptRecordingPayload")
            and file_contains("ui/next-app/src/lib/mis.ts", "/commercial/release-status")
            and file_contains("ui/next-app/src/lib/mis.ts", "/commercial/release-grade-rerun-bundle")
            and file_contains("ui/next-app/src/lib/mis.ts", "/commercial/release-grade-receipt-recording")
            and file_contains("ui/next-app/src/lib/mis.ts", "phase_gate_rerun_bundles")
            and file_contains("ui/next-app/src/lib/mis.ts", "phase_gate_recording_requests")
            and file_contains("ui/next-app/src/lib/mis.ts", "includeExternalCi")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerCommercialReleaseStatus")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerCommercialReleaseGradeRerunBundle")
            and file_contains("ui/next-app/src/lib/misServer.ts", "loadServerCommercialReleaseGradeReceiptRecording")
            and file_contains("ui/next-app/src/lib/misServer.ts", "includeExternalCi")
            and file_contains("ui/next-app/app/workspace/commercial/page.tsx", "loadServerCommercialReleaseStatus")
            and file_contains("ui/next-app/app/workspace/commercial/page.tsx", "loadServerCommercialReleaseGradeRerunBundle")
            and file_contains("ui/next-app/app/workspace/commercial/page.tsx", "loadServerCommercialReleaseGradeReceiptRecording")
            and file_contains("ui/next-app/app/workspace/commercial/page.tsx", "receiptRecording")
            and file_contains("ui/next-app/app/workspace/commercial/page.tsx", "exact_head_ci")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Release promotion")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Exact-head CI")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Promotion packet")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Receipt promotion plan")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Receipt rerun bundle")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Gate reruns")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "write previews")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Receipt recording preview")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Recording previews")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "patch previews")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Transaction preview")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "CLI confirm only")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "--confirm-recording")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Check exact-head CI")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "Current evidence")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-release-status")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-release-promotion-preflight")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-promotion-packet")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-release-grade-receipt-plan")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-release-grade-rerun-bundle")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-rerun-bundle-gate-detail")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-release-grade-receipt-recording")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-receipt-recording-gate-detail")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-receipt-recording-transaction")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-exact-head-ci-command")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-external-ci-readback-form")
            and file_contains("ui/next-app/src/components/CommercialPage.tsx", "commercial-current-evidence-gates")
            and file_contains("scripts/commercial_release_status_api_smoke.py", "commercial_release_status_api_v1")
            and file_contains("scripts/commercial_release_promotion_packet.py", "commercial_release_promotion_packet_v1")
            and file_contains("scripts/commercial_release_promotion_packet_smoke.py", "commercial_release_promotion_packet_v1")
            and file_contains("scripts/commercial_release_grade_receipt_plan.py", "commercial_release_grade_receipt_plan_v1")
            and file_contains("scripts/commercial_release_grade_receipt_plan_smoke.py", "commercial_release_grade_receipt_plan_v1")
            and file_contains("scripts/commercial_release_grade_rerun_bundle.py", "commercial_release_grade_rerun_bundle_v1")
            and file_contains("scripts/commercial_release_grade_rerun_bundle_smoke.py", "commercial_release_grade_rerun_bundle_v1")
            and file_contains("scripts/commercial_release_grade_rerun_bundle_api_smoke.py", "commercial_release_grade_rerun_bundle_v1")
            and file_contains("scripts/commercial_release_grade_receipt_recording.py", "commercial_release_grade_receipt_recording_v1")
            and file_contains("scripts/commercial_release_grade_receipt_recording.py", "--confirm-recording")
            and file_contains("scripts/commercial_release_grade_receipt_recording.py", "explicit_confirm_receipt_recording_transaction")
            and file_contains("scripts/commercial_release_grade_receipt_recording_smoke.py", "commercial_release_grade_receipt_recording_v1")
            and file_contains("scripts/commercial_release_grade_receipt_recording_smoke.py", "--confirm-recording")
            and file_contains("scripts/commercial_release_grade_receipt_recording_api_smoke.py", "commercial_release_grade_receipt_recording_v1")
            and file_contains("scripts/commercial_release_grade_receipt_recording_api_smoke.py", "applies_by_default")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "commercial_release_status_api_smoke.py")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "commercial_release_promotion_packet_smoke.py")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "commercial_release_grade_receipt_plan_smoke.py")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "commercial_release_grade_rerun_bundle_smoke.py")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "commercial_release_grade_rerun_bundle_api_smoke.py")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "commercial_release_grade_receipt_recording_smoke.py")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "commercial_release_grade_receipt_recording_api_smoke.py")
            and file_contains("scripts/nextjs_parity_smoke.py", "commercial_release_status_api_v1")
            and file_contains("scripts/nextjs_parity_smoke.py", "commercial_release_promotion_packet_v1")
            and file_contains("scripts/nextjs_parity_smoke.py", "commercial_release_grade_receipt_plan_v1")
            and file_contains("scripts/nextjs_parity_smoke.py", "commercial_release_grade_rerun_bundle_v1")
            and file_contains("scripts/nextjs_parity_smoke.py", "commercial_release_grade_receipt_recording_v1")
            and file_contains("scripts/nextjs_parity_smoke.py", "/commercial/release-grade-rerun-bundle")
            and file_contains("scripts/nextjs_parity_smoke.py", "/commercial/release-grade-receipt-recording")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Release promotion")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Receipt recording preview")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Transaction preview")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PACKET.json", "commercial_release_promotion_packet_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PACKET.md", "commercial_release_promotion_packet_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_GRADE_RECEIPT_PLAN.json", "commercial_release_grade_receipt_plan_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_GRADE_RECEIPT_PLAN.md", "commercial_release_grade_receipt_plan_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_GRADE_RERUN_BUNDLE.json", "commercial_release_grade_rerun_bundle_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_GRADE_RERUN_BUNDLE.md", "commercial_release_grade_rerun_bundle_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_GRADE_RECEIPT_RECORDING.json", "commercial_release_grade_receipt_recording_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_GRADE_RECEIPT_RECORDING.json", "explicit_confirm_receipt_recording_transaction")
            and file_contains("docs/COMMERCIAL_RELEASE_GRADE_RECEIPT_RECORDING.json", "--confirm-recording")
            and file_contains("docs/COMMERCIAL_RELEASE_GRADE_RECEIPT_RECORDING.md", "commercial_release_grade_receipt_recording_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_GRADE_RECEIPT_RECORDING.md", "explicit_confirm_receipt_recording_transaction")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_release_grade_receipt_recording_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "/api/commercial/release-status"),
            "Next commercial page renders read-only release promotion, exact-head CI command, promotion packet, release-grade receipt plan, rerun bundle, receipt recording preview, and current-evidence blockers from the MIS API without network/live execution",
        ),
        check(
            "vite_browser_snapshot_surface_exists",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "vite_playwright_snapshot_smoke.py")
            and file_contains("ui/start-building-app/vite.config.ts", "VITE_AGENTOPS_PROXY_TARGET")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "vite_browser_snapshot_parity_v1")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "/mis-api/dashboard/metrics")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "snapshot_vite_detail_routes")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "detail_snapshots = snapshot_vite_detail_routes")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "snapshots + detail_snapshots")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", '"detail_task_id"')
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", '"detail_run_id"')
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "/workspace/tasks/")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "/workspace/runs/")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "/admin/tasks/")
            and file_contains("scripts/vite_playwright_snapshot_smoke.py", "/admin/runs/")
            and (ROOT / "scripts" / "vite_playwright_snapshot_smoke.py").exists(),
            "canonical Vite UI browser snapshot smoke covers list/detail routes and configurable MIS proxy target is present",
        ),
        check(
            "ui_api_parity_matrix_surface_exists",
            file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_api_parity_matrix_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.md", "scripts/ui_api_parity_matrix_smoke.py")
            and file_contains("scripts/ui_api_parity_matrix_smoke.py", "ui_api_parity_matrix_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "UI_API_PARITY_MATRIX")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_covered_route_retirement_packet_v1")
            and (ROOT / "scripts" / "ui_api_parity_matrix_smoke.py").exists(),
            "Gate 4 page-by-page Vite/Next route and API parity matrix is present, machine-checkable, and references covered-route retirement candidates",
        ),
        check(
            "ui_task_run_route_parity_surface_exists",
            file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_task_run_route_parity_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_task_run_route_parity_smoke.py")
            and file_contains("scripts/ui_task_run_route_parity_smoke.py", "ui_task_run_route_parity_v1")
            and file_contains("ui/next-app/src/components/LedgerPages.tsx", "/workspace/tasks/${encodeURIComponent(task.task_id)}")
            and file_contains("ui/next-app/src/components/LedgerPages.tsx", "/workspace/runs/${encodeURIComponent(run.run_id)}")
            and (ROOT / "scripts" / "ui_task_run_route_parity_smoke.py").exists(),
            "Gate 4 task/run route-level read-model parity and Next list-to-detail links are present",
        ),
        check(
            "ui_route_naming_decision_surface_exists",
            route_naming_decision_semantics_ok()
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "ui_route_naming_decision_v1")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "/admin/tasks/:id")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "/workspace/tasks/:taskId")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "/admin/runs")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "/workspace/runs")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "backward_compatible_redirect_or_alias")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.md", "ui_route_naming_decision_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_route_naming_decision_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_route_naming_decision_smoke.py")
            and file_contains("scripts/ui_route_naming_decision_smoke.py", "ui_route_naming_decision_v1")
            and (ROOT / "scripts" / "ui_route_naming_decision_smoke.py").exists(),
            "Gate 4 task/run route naming decision records executed workspace redirect retirement for legacy admin task/run routes",
        ),
        check(
            "ui_legacy_route_alias_surface_exists",
            file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "ui_legacy_route_alias_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_legacy_route_alias_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_legacy_route_alias_smoke.py")
            and file_contains("scripts/ui_legacy_route_alias_smoke.py", "ui_legacy_route_alias_v1")
            and file_contains("ui/next-app/app/admin/tasks/[taskId]/page.tsx", "/workspace/tasks/")
            and file_contains("ui/next-app/app/admin/runs/page.tsx", "/workspace/runs")
            and file_contains("ui/next-app/app/admin/runs/[runId]/page.tsx", "/workspace/runs/")
            and (ROOT / "scripts" / "ui_legacy_route_alias_smoke.py").exists(),
            "Gate 4 Next.js legacy /admin task/run aliases redirect to /workspace targets while task/run Vite routes retire to workspace redirects",
        ),
        check(
            "ui_navigation_inventory_surface_exists",
            file_contains("docs/UI_NAVIGATION_INVENTORY.json", "ui_navigation_inventory_v1")
            and file_contains("docs/UI_NAVIGATION_INVENTORY.md", "ui_navigation_inventory_v1")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "canonical_navigation_inventory_verified")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_navigation_inventory_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_navigation_inventory_smoke.py")
            and file_contains("scripts/ui_navigation_inventory_smoke.py", "ui_navigation_inventory_v1")
            and file_contains("ui/next-app/src/components/AppFrame.tsx", 'href: "/workspace/tasks"')
            and file_contains("ui/next-app/src/components/AppFrame.tsx", 'href: "/workspace/runs"')
            and file_contains("ui/start-building-app/src/app/App.tsx", 'path="/workspace/runs"')
            and file_contains("ui/start-building-app/src/app/components/layout/Sidebar.tsx", 'path: "/workspace/runs"')
            and (ROOT / "scripts" / "ui_navigation_inventory_smoke.py").exists(),
            "Gate 4 Next.js and Vite task/run primary navigation is inventoried under /workspace; /admin remains redirect-alias only",
        ),
        check(
            "ui_route_retirement_packet_surface_exists",
            file_contains("docs/UI_ROUTE_RETIREMENT_PACKET.json", "ui_route_retirement_packet_v1")
            and file_contains("docs/UI_ROUTE_RETIREMENT_PACKET.md", "ui_route_retirement_packet_v1")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "retirement_packet_executed")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_route_retirement_packet_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_route_retirement_packet_smoke.py")
            and file_contains("scripts/ui_route_retirement_packet_smoke.py", "ui_route_retirement_packet_v1")
            and file_contains("docs/UI_ROUTE_RETIREMENT_PACKET.json", "\"retirement_action\": \"executed_workspace_redirect\"")
            and file_contains("docs/UI_ROUTE_RETIREMENT_PACKET.json", "\"retirement_allowed\": true")
            and (ROOT / "scripts" / "ui_route_retirement_packet_smoke.py").exists(),
            "Gate 4 task/run legacy route retirement packet executes workspace redirect retirement while preserving deep links",
        ),
        check(
            "ui_admin_operations_route_retirement_surface_exists",
            file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_admin_operations_route_retirement_v1")
            and file_contains("docs/UI_ROUTE_NAMING_DECISION.json", "ui_admin_operations_route_retirement_v1")
            and file_contains("docs/UI_NAVIGATION_INVENTORY.json", "ui_admin_operations_route_retirement_v1")
            and file_contains("docs/UI_ROUTE_RETIREMENT_PACKET.json", "ui_admin_operations_route_retirement_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_admin_operations_route_retirement_smoke.py")
            and file_contains("scripts/ui_admin_operations_route_retirement_smoke.py", "ui_admin_operations_route_retirement_v1")
            and file_contains("ui/start-building-app/src/app/App.tsx", 'path="/workspace/tool-calls"')
            and file_contains("ui/start-building-app/src/app/components/layout/Sidebar.tsx", 'path: "/workspace/tool-calls"')
            and (ROOT / "scripts" / "ui_admin_operations_route_retirement_smoke.py").exists(),
            "Gate 4 Vite admin operations routes execute workspace redirect retirement while preserving deep links and Agent Gateway CLI/API/MCP",
        ),
        check(
            "ui_covered_route_retirement_packet_surface_exists",
            file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", "ui_covered_route_retirement_packet_v1")
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", '"retirement_action": "not_executed"')
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", '"retirement_allowed": false')
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", "control_tower")
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", "worker_console")
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", "admin_deep_link_redirect_or_alias")
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", "same_path_ownership_cutover_commit")
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.json", "agent_gateway_cli_api_mcp_unchanged")
            and file_contains("docs/UI_COVERED_ROUTE_RETIREMENT_PACKET.md", "does not retire any Vite route")
            and file_contains("scripts/ui_covered_route_retirement_packet_smoke.py", "ui_covered_route_retirement_packet_v1")
            and file_contains("scripts/ui_covered_route_retirement_packet_smoke.py", "covered_split_next_routes_no_admin_alias")
            and file_contains("scripts/ui_covered_route_retirement_packet_smoke.py", "covered_same_path_plus_focused_worker_console")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "ui_covered_route_retirement_packet_v1")
            and file_contains("docs/UI_API_PARITY_MATRIX.md", "ui_covered_route_retirement_packet_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "ui_covered_route_retirement_packet_smoke.py")
            and file_contains("scripts/nextjs_parity_smoke.py", "ui_covered_route_retirement_packet_v1")
            and (ROOT / "scripts" / "ui_covered_route_retirement_packet_smoke.py").exists(),
            "Gate 4 covered Control Tower and Worker Console route retirement candidates are documented while Vite retirement stays fail-closed",
        ),
        check(
            "commercial_release_evidence_packet_surface_exists",
            file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "release_evidence_packet_v1")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "commercial_release_evidence_packet_v1")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "deployment_readiness_smoke.py --postgres-write-fixture")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "nextjs_playwright_snapshot_smoke.py --postgres-write-fixture")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "local_runtime_acceptance.py --live-openclaw --live-hermes")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "--openclaw-timeout 300 --hermes-timeout 600 --request-timeout 720")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "commercial_release_evidence_packet_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "deployment_readiness_postgres_runtime_write_fixture_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "nextjs_deployment_postgres_runtime_write_fixture_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "byoc_deployment_acceptance_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "real_hermes_openclaw_acceptance")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "HERMES_ALLOW_REAL_RUN=true")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "--openclaw-timeout 300 --hermes-timeout 600 --request-timeout 720")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.md", "mock evidence is CI/offline fallback only")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.md", "mock-only")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "release_evidence_packet_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_release_evidence_packet_smoke.py")
            and file_contains("scripts/release_evidence_packet_smoke.py", "release_evidence_packet_v1")
            and file_contains("scripts/commercial_release_evidence_packet_smoke.py", "commercial_release_evidence_packet_v1")
            and file_contains("scripts/commercial_release_evidence_packet_smoke.py", "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture")
            and (ROOT / "scripts" / "release_evidence_packet_smoke.py").exists()
            and (ROOT / "scripts" / "commercial_release_evidence_packet_smoke.py").exists(),
            "Commercial release evidence packet makes Gate 5 BYOC/Postgres and real Hermes/OpenClaw evidence machine-checkable",
        ),
        check(
            "commercial_handoff_status_surface_exists",
            file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_handoff_status_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_evidence_receipts_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_current_evidence_status_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_release_evidence_packet_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "release_evidence_packet_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "release_freeze_protocol_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "merge_readiness_status_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "phase_gate_statuses")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "current_evidence_status")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "gates_with_local_receipts")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "explicit_blockers")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "required_commands")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "python3 scripts/commercial_evidence_receipts.py")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "python3 scripts/commercial_evidence_receipts_smoke.py")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "python3 scripts/commercial_current_evidence_status.py")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "python3 scripts/commercial_current_evidence_status_smoke.py")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "python3 scripts/commercial_handoff_status.py")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "python3 scripts/commercial_handoff_status_smoke.py")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.md", "blocked_release_evidence_required")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "commercial_handoff_status_smoke.py")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "handoff_status_command")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "current_evidence_status_command")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_handoff_status_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_handoff_status_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_handoff_status_v1")
            and file_contains("scripts/commercial_handoff_status.py", "commercial_handoff_status_v1")
            and file_contains("scripts/commercial_handoff_status.py", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_handoff_status.py", "--require-handoff-ready")
            and file_contains("scripts/commercial_handoff_status_smoke.py", "commercial_handoff_status_v1")
            and file_contains("scripts/commercial_handoff_status_smoke.py", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_handoff_status_smoke.py", "phase_gate_statuses")
            and (ROOT / "scripts" / "commercial_handoff_status.py").exists()
            and (ROOT / "scripts" / "commercial_handoff_status_smoke.py").exists(),
            "Commercial handoff status gives operators one CI-safe command for current gate states, blockers, and required evidence",
        ),
        check(
            "commercial_evidence_receipts_surface_exists",
            file_contains("docs/COMMERCIAL_EVIDENCE_RECEIPTS.json", "commercial_evidence_receipts_v1")
            and file_contains("docs/COMMERCIAL_EVIDENCE_RECEIPTS.json", "partial_local_receipts_not_release_complete")
            and file_contains("docs/COMMERCIAL_EVIDENCE_RECEIPTS.json", "local_receipts_complete_exact_head_required")
            and file_contains("docs/COMMERCIAL_EVIDENCE_RECEIPTS.json", "gate_5_byoc_enterprise_deployment")
            and file_contains("docs/COMMERCIAL_EVIDENCE_RECEIPTS.md", "commercial_evidence_receipts_v1")
            and file_contains("docs/COMMERCIAL_EVIDENCE_RECEIPTS.md", "commercial_evidence_receipts_smoke.py")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "gates_with_local_receipts")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "release_grade_current")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "gates_with_local_receipts")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "evidence_receipts_contract_id")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_evidence_receipts_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_evidence_receipts_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_evidence_receipts.py", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_evidence_receipts.py", "--require-release-grade")
            and file_contains("scripts/commercial_evidence_receipts_smoke.py", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_evidence_receipts_smoke.py", "release_grade_current")
            and (ROOT / "scripts" / "commercial_evidence_receipts.py").exists()
            and (ROOT / "scripts" / "commercial_evidence_receipts_smoke.py").exists(),
            "Commercial evidence receipts record local hash/ref-only Gate 5 evidence while keeping release-grade, handoff, and merge states false",
        ),
        check(
            "commercial_current_evidence_status_surface_exists",
            file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "commercial_current_evidence_status_v1")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "commercial_evidence_receipts_v1")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "current_evidence_required")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "phase_gate_evidence_statuses")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "gates_requiring_current_evidence")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "gates_with_local_receipts")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "local_receipt_current")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "release_grade_current")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "heavy_evidence_not_executed_by_default")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.json", "gate_5_byoc_enterprise_deployment")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md", "commercial_current_evidence_status_v1")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md", "commercial_evidence_receipts_v1")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md", "commercial_evidence_receipts_smoke.py")
            and file_contains("docs/COMMERCIAL_CURRENT_EVIDENCE_STATUS.md", "commercial_current_evidence_status_smoke.py")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "commercial_current_evidence_status_smoke.py")
            and file_contains("docs/RELEASE_EVIDENCE_PACKET.json", "current_evidence_status_contract_id")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_current_evidence_status_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_current_evidence_status_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_current_evidence_status_v1")
            and file_contains("scripts/commercial_current_evidence_status.py", "commercial_current_evidence_status_v1")
            and file_contains("scripts/commercial_current_evidence_status.py", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_current_evidence_status.py", "local_receipt_current")
            and file_contains("scripts/commercial_current_evidence_status.py", "--require-current-evidence")
            and file_contains("scripts/commercial_current_evidence_status_smoke.py", "commercial_current_evidence_status_v1")
            and file_contains("scripts/commercial_current_evidence_status_smoke.py", "commercial_evidence_receipts_v1")
            and file_contains("scripts/commercial_current_evidence_status_smoke.py", "gates_requiring_current_evidence")
            and (ROOT / "scripts" / "commercial_current_evidence_status.py").exists()
            and (ROOT / "scripts" / "commercial_current_evidence_status_smoke.py").exists(),
            "Commercial current evidence status makes per-gate evidence freshness gaps machine-readable without executing heavy/live checks",
        ),
        check(
            "commercial_ci_receipt_surface_exists",
            (ROOT / "scripts" / "commercial_ci_receipt.py").exists()
            and (ROOT / "scripts" / "commercial_ci_receipt_smoke.py").exists()
            and file_contains("scripts/commercial_ci_receipt.py", "commercial_ci_command_receipt_v1")
            and file_contains("scripts/commercial_ci_receipt.py", "commercial_postgres_byoc_ci_receipt_v1")
            and file_contains("scripts/commercial_ci_receipt.py", "commercial_migration_ci_receipt_v1")
            and file_contains("scripts/commercial_ci_receipt.py", "payload_contains_skipped_evidence")
            and file_contains("scripts/commercial_ci_receipt.py", "stdout_sha256")
            and file_contains("scripts/commercial_ci_receipt.py", "repo_digests")
            and file_contains("scripts/commercial_ci_receipt.py", '"release_complete": False')
            and file_contains("scripts/commercial_ci_receipt_smoke.py", "commercial_ci_receipt_smoke_v1")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "byoc-postgres:")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "receipt-assemble:")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "commercial-gate-5-ci-receipt")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "commercial-migration-ci-receipt")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_ci_command_receipt_v1"),
            "Gate 3 and Gate 5 run independently and publish exact-head hash-only command, scope, and aggregate CI receipts without self-promoting release state",
        ),
        check(
            "commercial_ci_supply_chain_pins_exist",
            (ROOT / "scripts" / "commercial_ci_supply_chain_smoke.py").exists()
            and file_contains("scripts/commercial_ci_supply_chain_smoke.py", "commercial_ci_supply_chain_pins_v1")
            and file_contains("scripts/commercial_ci_supply_chain_smoke.py", "Postgres image is not tag-and-digest pinned")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "python3 scripts/commercial_ci_supply_chain_smoke.py")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "runs-on: ubuntu-24.04")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "@playwright/cli@0.1.17")
            and not file_contains(".github/workflows/commercial-migration-ci.yml", "ubuntu-latest")
            and not file_contains(".github/workflows/commercial-migration-ci.yml", "actions/checkout@v4"),
            "Commercial CI pins runner, first-party actions, language patch versions, Playwright CLI, and the Postgres tag plus digest",
            "python3 scripts/commercial_ci_supply_chain_smoke.py",
        ),
        check(
            "commercial_exact_head_ci_evidence_surface_exists",
            file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json", "commercial_exact_head_ci_evidence_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.md", "commercial_exact_head_ci_evidence.py --from-gh --require-current-head")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_exact_head_ci_evidence.py --from-gh --require-current-head")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_exact_head_ci_evidence_v1")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_exact_head_ci_evidence_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_exact_head_ci_evidence_v1")
            and file_contains("scripts/commercial_exact_head_ci_evidence.py", "commercial_exact_head_ci_evidence_v1")
            and file_contains("scripts/commercial_exact_head_ci_evidence.py", "commercial-migration-ci-receipt")
            and file_contains("scripts/commercial_exact_head_ci_evidence.py", "commercial_migration_ci_receipt_v1")
            and file_contains("scripts/commercial_exact_head_ci_evidence.py", "receipt_head_mismatch")
            and file_contains("scripts/commercial_exact_head_ci_evidence.py", "--require-current-head")
            and file_contains("scripts/commercial_exact_head_ci_evidence_smoke.py", "commercial_exact_head_ci_evidence_v1")
            and (ROOT / "scripts" / "commercial_exact_head_ci_evidence.py").exists()
            and (ROOT / "scripts" / "commercial_exact_head_ci_evidence_smoke.py").exists(),
            "Commercial exact-head CI evidence reader makes current-head GitHub Actions proof external to committed receipts",
        ),
        check(
            "commercial_release_promotion_preflight_surface_exists",
            file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json", "blocked_release_promotion_required")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json", "commercial_exact_head_ci_evidence_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json", "release_promotion_allowed")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.json", "release_grade_update_allowed")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.md", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/COMMERCIAL_RELEASE_PROMOTION_PREFLIGHT.md", "--include-external-ci-evidence --require-promotion-ready")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/COMMERCIAL_HANDOFF_STATUS.json", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_release_promotion_preflight_v1")
            and file_contains("scripts/commercial_release_promotion_preflight.py", "commercial_release_promotion_preflight_v1")
            and file_contains("scripts/commercial_release_promotion_preflight.py", "--include-external-ci-evidence")
            and file_contains("scripts/commercial_release_promotion_preflight_smoke.py", "commercial_release_promotion_preflight_v1")
            and file_contains("scripts/commercial_release_promotion_preflight_smoke.py", "release_grade_receipts_empty")
            and (ROOT / "scripts" / "commercial_release_promotion_preflight.py").exists()
            and (ROOT / "scripts" / "commercial_release_promotion_preflight_smoke.py").exists(),
            "Commercial release promotion preflight makes exact-head CI, remote sync, clean worktree, and release-grade receipt blockers machine-readable",
        ),
        check(
            "commercial_release_grade_promotion_static_surface_exists",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "commercial_release_grade_promotion_v1")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "commercial_release_grade_promotion_smoke.py")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "python3 -I -B -S scripts/commercial_release_grade_promotion_smoke.py")
            and (ROOT / "scripts" / "commercial_release_grade_promotion").exists()
            and (ROOT / "scripts" / "commercial_release_grade_promotion.py").exists()
            and (ROOT / "scripts" / "commercial_release_grade_promotion_smoke.py").exists()
            and file_contains("scripts/commercial_release_grade_promotion", "/usr/bin/python3")
            and file_contains("scripts/commercial_release_grade_promotion", "-I -B")
            and file_contains("scripts/commercial_release_grade_promotion.py", "runtime_acceptance_script_head_mismatch")
            and file_contains("scripts/commercial_release_grade_promotion.py", "independent_remote_branch_head_mismatch")
            and file_contains("scripts/commercial_release_grade_promotion_smoke.py", "global_sitecustomize_disabled")
            and file_contains("scripts/commercial_release_grade_promotion_smoke.py", "recording_receipt_derivation_verified")
            and file_contains("scripts/commercial_release_grade_promotion_smoke.py", "critical_execution_closure_matches_head_bytes")
            and file_contains("scripts/commercial_release_grade_promotion_smoke.py", "post_replace_fsync_warning_truthful"),
            "Static promotion implementation, documentation, smoke, and CI wiring are present; only CI execution of the smoke is the dynamic behavior gate",
        ),
        check(
            "release_freeze_protocol_surface_exists",
            file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "release_freeze_protocol_v1")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "freeze_active_not_release_complete")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "commercial_release_evidence_packet_v1")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "nextjs_playwright_snapshot_smoke.py --postgres-write-fixture")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "local_runtime_acceptance.py --live-openclaw --live-hermes")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "--openclaw-timeout 300 --hermes-timeout 600 --request-timeout 720")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.json", "sqlite_fallback_as_postgres_proof")
            and file_contains("docs/RELEASE_FREEZE_PROTOCOL.md", "freeze_active_not_release_complete")
            and file_contains("scripts/release_freeze_protocol_smoke.py", "release_freeze_protocol_v1")
            and file_contains("scripts/release_freeze_protocol_smoke.py", "freeze_active_not_release_complete")
            and file_contains("scripts/release_freeze_protocol_smoke.py", "release_evidence_packet_smoke.py")
            and (ROOT / "scripts" / "release_freeze_protocol_smoke.py").exists(),
            "Release freeze protocol keeps commercial handoff frozen until Gate 5 Postgres/BYOC and real runtime evidence are current",
        ),
        check(
            "merge_readiness_status_surface_exists",
            file_contains("docs/MERGE_READINESS_STATUS.json", "merge_readiness_status_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "blocked_release_evidence_required")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_release_promotion_preflight_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", '"merge_allowed": false')
            and file_contains("docs/MERGE_READINESS_STATUS.json", '"commercial_handoff_allowed": false')
            and file_contains("docs/MERGE_READINESS_STATUS.json", "release_freeze_protocol_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "commercial_release_evidence_packet_v1")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "local_runtime_acceptance.py --live-openclaw --live-hermes")
            and file_contains("docs/MERGE_READINESS_STATUS.json", "--openclaw-timeout 300 --hermes-timeout 600 --request-timeout 720")
            and file_contains("docs/MERGE_READINESS_STATUS.md", "blocked_release_evidence_required")
            and file_contains("scripts/merge_readiness_status_smoke.py", "merge_readiness_status_v1")
            and file_contains("scripts/merge_readiness_status_smoke.py", "blocked_release_evidence_required")
            and file_contains("scripts/merge_readiness_status_smoke.py", "release_freeze_protocol_smoke.py")
            and (ROOT / "scripts" / "merge_readiness_status_smoke.py").exists(),
            "Merge readiness remains explicitly blocked until release, freeze, Gate 5 BYOC/Postgres, and real runtime evidence are current",
        ),
        check(
            "postgres_is_gated_not_immediate",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "Storage Boundary Before Postgres"),
            "Postgres migration is behind a storage-boundary gate",
        ),
        check(
            "storage_boundary_surface_exists",
            file_contains("docs/STORAGE_BOUNDARY_MAP.md", "repo_list_workspace_tasks")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_parity_pre_container_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_container_parity_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_adapter_sql_contract_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_optional_psycopg_adapter_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "LIKE '%...%'")
            and file_contains("scripts/storage_postgres_optional_adapter_smoke.py", "literal_percent_like")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_boundary_fixture_parity_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_route_read_model_parity_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "storage_backend_selection_fail_closed_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_http_read_parity_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "storage_postgres_http_read_parity_smoke.py")
            and file_contains("server.py", "repo_list_workspace_tasks")
            and file_contains("server.py", "storage_backend_status")
            and file_contains("server.py", "postgres_read_only_backend")
            and (ROOT / "agentops_mis_storage" / "postgres.py").exists()
            and (ROOT / "agentops_mis_storage" / "parity_fixture.py").exists()
            and (ROOT / "scripts" / "storage_boundary_sqlite_smoke.py").exists()
            and (ROOT / "scripts" / "storage_postgres_boundary_parity_smoke.py").exists()
            and (ROOT / "scripts" / "storage_postgres_route_read_model_smoke.py").exists()
            and (ROOT / "scripts" / "storage_postgres_http_read_parity_smoke.py").exists()
            and (ROOT / "scripts" / "storage_backend_selection_smoke.py").exists(),
            "workspace-scoped helpers, isolated SQLite smoke, Postgres container parity, adapter SQL contract, optional psycopg adapter, shared boundary fixture parity, route read-model parity, fail-closed backend selection, and read-only Postgres HTTP parity are present",
        ),
        check(
            "postgres_cli_read_parity_surface_exists",
            file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_cli_read_parity_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "storage_postgres_cli_read_parity_smoke.py")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "storage_postgres_cli_read_parity_smoke.py")
            and file_contains("docs/AGENT_GATEWAY_CLI_SPEC.md", "storage_postgres_cli_read_parity_smoke.py")
            and file_contains("scripts/storage_postgres_cli_read_parity_smoke.py", "agent_plan_verify")
            and file_contains("scripts/storage_postgres_cli_read_parity_smoke.py", "plan_evidence_verify")
            and (ROOT / "scripts" / "storage_postgres_cli_read_parity_smoke.py").exists(),
            "read-only Postgres CLI/API parity smoke and docs include Agent Plan and plan-evidence reads",
        ),
        check(
            "postgres_write_helper_parity_surface_exists",
            file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_write_helper_parity_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "storage_postgres_write_helper_parity_smoke.py")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "storage_postgres_write_helper_parity_smoke.py")
            and file_contains("agentops_mis_storage/postgres.py", "translate_sqlite_insert_or_ignore")
            and file_contains("server.py", 'previous["tamper_chain_hash"]')
            and (ROOT / "scripts" / "storage_postgres_write_helper_parity_smoke.py").exists(),
            "Postgres write-helper parity smoke, INSERT OR IGNORE translation, and audit dict-row compatibility are present",
        ),
        check(
            "postgres_http_write_task_surface_exists",
            file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_http_write_task_parity_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "storage_postgres_http_write_task_smoke.py")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "storage_postgres_http_write_task_smoke.py")
            and file_contains("docs/AGENT_GATEWAY_CLI_SPEC.md", "Postgres routed task/execution/heartbeat/evidence/plan/memory/approval/audit helper")
            and file_contains("server.py", "AGENTOPS_POSTGRES_WRITE_HTTP")
            and file_contains("server.py", "POSTGRES_HTTP_WRITE_ALLOWED_ROUTES")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", 'method="POST"')
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/tasks")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/tasks")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/tasks/{GATEWAY_TASK_ID}/claim")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/runs/start")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/tool-calls")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/artifacts")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/evaluations/submit")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/agent-plans")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/plan-evidence-manifests")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/memories/propose")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/approvals/request")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/agent-gateway/audit")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/integrations/openclaw/probe")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "/api/integrations/hermes/run-task")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_openclaw_prepare_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_openclaw_approve_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_openclaw_resume_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_openclaw_concurrent_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_openclaw_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_openclaw_replay_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_hermes_prepare_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_hermes_approve_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_hermes_resume_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_hermes_concurrent_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_hermes_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_hermes_replay_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_cross_process_single_winner")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime.openclaw_probe.execution_claimed")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime.run_task.execution_claimed")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_non_prepared_approval_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_claim_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_run_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_tool_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_eval_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_artifact_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_plan_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_manifest_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_memory_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_approval_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_missing_audit_scope_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_plan_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_header_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_header_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_audit_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_heartbeat_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_header_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_other_agent_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_claim_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_run_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_tool_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_eval_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_artifact_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_plan_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_manifest_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_memory_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_approval_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_audit_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_intruder_audit_no_run_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_heartbeat_intruder_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_intruder_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_heartbeat_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_plan_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_audit_no_token_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_manifest_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_approved_overwrite_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_existing_cross_workspace_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_other_agent_overwrite_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_tool_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_approved_overwrite_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_other_agent_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_task_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_terminal_revival_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_completion_heartbeat_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_audit_mismatch_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_non_allowlisted_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_execution_start_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_evidence_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_plan_evidence_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_approval_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_audit_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_memory_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_heartbeat_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_run_heartbeat_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_gateway_run_completion_heartbeat_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_runtime_prepared_action_write_v1")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "postgres_http_runtime_approval_decision_write_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_http_gateway_run_completion_heartbeat_write_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_http_runtime_prepared_action_write_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "fixed Hermes/OpenClaw prepare")
            and file_contains("docs/AGENT_GATEWAY_CLI_SPEC.md", "complete a running run through heartbeat")
            and file_contains("server.py", '("POST", "/api/agent-gateway/tool-calls")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/artifacts")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/evaluations/submit")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/heartbeat")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/runs/:run_id/heartbeat")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/agent-plans")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/plan-evidence-manifests")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/memories/propose")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/approvals/request")')
            and file_contains("server.py", '("POST", "/api/agent-gateway/audit")')
            and file_contains("server.py", '("POST", "/api/integrations/openclaw/probe")')
            and file_contains("server.py", '("POST", "/api/integrations/hermes/run-task")')
            and file_contains("server.py", '("POST", "/api/approvals/:approval_id/approve")')
            and file_contains("server.py", "POSTGRES_HTTP_PREPARED_ACTION_DECISION_TYPES")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_heartbeat_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_completion_heartbeat_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_run_id")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_task_id")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_agent_id")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_run_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_task_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_agent_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_completion_run_ended")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_tool_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_eval_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_artifact_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_plan_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_manifest_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_manifest_verification_pass")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_audit_write_status")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_tool_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_eval_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_artifact_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_plan_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_manifest_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_memory_audit_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_audit_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_run_wait_audit_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_approval_task_wait_audit_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_heartbeat_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_heartbeat_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_completion_heartbeat_runtime_event_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_run_completion_heartbeat_audit_count")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_token_last_heartbeat")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "gateway_audit_runtime_event_count")
            and (ROOT / "scripts" / "storage_postgres_http_write_task_smoke.py").exists(),
            "experimental Postgres HTTP task, Agent Gateway task, claim, run-start, agent/run progress and completion heartbeat, tool/eval/artifact evidence, Agent Plan, plan-evidence manifest, memory candidate, approval request, and run-bound audit write routes are explicitly allowlisted, smoke-tested, and documented",
        ),
        check(
            "postgres_gateway_lifecycle_write_surface_exists",
            file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_http_gateway_lifecycle_write_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "storage_postgres_gateway_lifecycle_smoke.py")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "storage_postgres_gateway_lifecycle_smoke.py")
            and file_contains("docs/AGENT_GATEWAY_CLI_SPEC.md", "Postgres Agent Gateway lifecycle helper")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "storage_postgres_gateway_lifecycle")
            and file_contains("server.py", "repo_upsert_gateway_enrollment_request")
            and file_contains("scripts/storage_boundary_sqlite_smoke.py", "repo_upsert_gateway_enrollment_request")
            and file_contains("server.py", "/api/agent-gateway/enrollment/rotate")
            and file_contains("server.py", "/api/agent-gateway/session/revoke")
            and file_contains("server.py", "AGENTOPS_WORKSPACE_ADMIN_KEYS_JSON")
            and file_contains("server.py", "must use a distinct key for every workspace")
            and file_contains("server.py", "is required for workspace-scoped Agent Gateway administration in production mode")
            and file_contains("server.py", "request_id_server_generated")
            and file_contains("scripts/security_production_readiness_smoke.py", "production global-only admin key did not fail closed")
            and file_contains("scripts/security_production_readiness_smoke.py", "invalid workspace admin key map passed")
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", "postgres_http_gateway_lifecycle_write_v1")
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", "anonymous_approval_rejected")
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", "caller_request_id_rejected")
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", "concurrent_issue_single_winner")
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", "concurrent_rotation_single_winner")
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", "concurrent_approve_issue_deadlock_free")
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", '"database_concurrency_servers": 2')
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", "cross_workspace_admin_hidden")
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", "cross_workspace_rejected")
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", "repeated_revoke_idempotent")
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", "postgres_repeated_approval_idempotent")
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", "concurrent_token_session_revoke_single_winner")
            and file_contains("scripts/enrollment_approval_workflow_smoke.py", "reverse_decision_rejected")
            and file_contains("scripts/openclaw_probe_prepared_action_smoke.py", "approval_rebind_rejected")
            and file_contains("server.py", "PreparedActionImmutableConflict")
            and file_contains("server.py", "repo_claim_workspace_prepared_action")
            and file_contains("scripts/openclaw_probe_prepared_action_smoke.py", "prepared_action_rebind_rejected")
            and file_contains("scripts/openclaw_probe_prepared_action_smoke.py", "cross_workspace_prepared_action_hidden")
            and file_contains("scripts/openclaw_probe_prepared_action_smoke.py", "cross_workspace_prepare_ids_isolated")
            and file_contains("scripts/openclaw_probe_prepared_action_smoke.py", "cross_workspace_task_rebind_rejected")
            and file_contains("scripts/openclaw_probe_prepared_action_smoke.py", "concurrent_resume_single_winner")
            and file_contains("scripts/hermes_run_task_prepared_action_smoke.py", "cross_workspace_prepared_action_hidden")
            and file_contains("scripts/hermes_run_task_prepared_action_smoke.py", "cross_workspace_prepare_ids_isolated")
            and file_contains("scripts/hermes_run_task_prepared_action_smoke.py", "cross_workspace_task_rebind_rejected")
            and file_contains("scripts/hermes_run_task_prepared_action_smoke.py", "concurrent_resume_single_winner")
            and file_contains("server.py", "approval_immutable_binding_conflict")
            and file_contains("server.py", "approval_decision_transition_requires_decision_api")
            and file_contains("server.py", "approval_decision_conflict")
            and file_contains("server.py", "postgres_locking_rows")
            and file_contains("scripts/storage_postgres_gateway_lifecycle_smoke.py", "token_values_omitted_from_evidence")
            and (ROOT / "scripts" / "storage_postgres_gateway_lifecycle_smoke.py").exists(),
            "Static Gateway lifecycle and prepared-action claim/immutability smoke surfaces are present; CI execution remains the dynamic behavior gate",
        ),
        check(
            "prepared_action_side_effect_resume_contract_exists",
            all(
                file_contains(path, marker)
                for path in (
                    "docs/AGENT_GATEWAY_CLI_SPEC.md",
                    "docs/STORAGE_BOUNDARY_MAP.md",
                    "docs/POSTGRES_PARITY_CONTRACT.md",
                )
                for marker in (
                    "prepared_action_approval_single_binding_v1",
                    "prepared_action_cas_claim_v1",
                    "prepared_action_stale_unknown_outcome_v1",
                    "fixed_runtime_server_generated_identifiers_v1",
                    "legacy_prepared_action_lifecycle_migration_v1",
                )
            )
            and file_contains("server.py", "idx_prepared_actions_approval_unique")
            and file_contains("server.py", "prepared_action_approval_binding_conflict")
            and file_contains("server.py", "def claim_prepared_action_execution(")
            and file_contains("server.py", "WHERE workspace_id=? AND prepared_action_id=? AND status='approved'")
            and file_contains("server.py", "AGENTOPS_PREPARED_ACTION_STALE_SECONDS")
            and file_contains("server.py", "execution_outcome_unknown_after_stale_claim")
            and file_contains("server.py", '"provider_call_may_have_completed": True')
            and file_contains("server.py", "server_generated_runtime_identifiers_required")
            and file_contains("server.py", "def ensure_sqlite_prepared_action_lifecycle_schema(")
            and python_functions_call(
                "server.py",
                (
                    "openclaw_resume_probe",
                    "dify_resume_upload_text",
                    "agnesfallback_resume_probe",
                    "resume_local_ai_brief",
                    "resume_customer_worker_external_write",
                    "hermes_resume_run_task",
                    "notion_resume_prepared_export",
                ),
                "claim_prepared_action_execution",
            )
            and file_contains("scripts/storage_boundary_sqlite_smoke.py", "prepared_action_approval_binding_unique")
            and file_contains("scripts/storage_boundary_sqlite_smoke.py", "stale_executing_failed_unknown_outcome")
            and file_contains("scripts/storage_boundary_sqlite_smoke.py", "legacy_prepared_action_lifecycle_migrated")
            and file_contains("scripts/storage_postgres_write_helper_parity_smoke.py", "repo_upsert_prepared_action_approval_conflict")
            and file_contains("scripts/openclaw_probe_prepared_action_smoke.py", "caller_runtime_identifiers_rejected")
            and file_contains("scripts/openclaw_probe_prepared_action_smoke.py", "concurrent_resume_single_winner")
            and file_contains("scripts/hermes_run_task_prepared_action_smoke.py", "caller_runtime_identifiers_rejected")
            and file_contains("scripts/hermes_run_task_prepared_action_smoke.py", "concurrent_resume_single_winner")
            and file_contains("scripts/dify_upload_prepared_action_smoke.py", "concurrent_resume_single_winner")
            and file_contains("scripts/storage_postgres_http_write_task_smoke.py", "runtime_cross_process_single_winner"),
            "Prepared-action approval uniqueness, shared CAS claim-before-provider, stale unknown-outcome terminal failure, legacy SQLite lifecycle migration, and server-generated fixed-runtime identifiers are statically guarded; smoke execution remains the dynamic gate",
        ),
        check(
            "nextjs_postgres_control_plane_tasks_surface_exists",
            file_contains("ui/next-app/package.json", '"pg"')
            and file_contains("ui/next-app/src/server/controlPlane/config.ts", "AGENTOPS_CONTROL_PLANE_MODE")
            and file_contains("ui/next-app/src/server/controlPlane/config.ts", "AGENTOPS_TS_CONTROL_PLANE_MODE")
            and file_contains("ui/next-app/src/server/controlPlane/config.ts", "isProductionDeployment() ? \"postgres\" : \"proxy\"")
            and file_contains("ui/next-app/src/server/controlPlane/config.ts", "normalized(process.env.AGENTOPS_DEPLOYMENT_MODE)")
            and file_contains("ui/next-app/src/server/controlPlane/config.ts", 'normalized(process.env.NODE_ENV) === "production"')
            and file_contains("ui/next-app/src/server/controlPlane/config.ts", 'if (configured === "proxy") return isProductionDeployment() ? "postgres" : "proxy"')
            and file_contains("ui/next-app/src/server/controlPlane/config.ts", "FREE_LOCAL_DEPLOYMENT_MODES")
            and file_contains("ui/next-app/src/server/controlPlane/config.ts", "legacyPythonProxyAllowed")
            and file_contains("ui/next-app/src/server/controlPlane/config.ts", "AGENTOPS_DEPLOYMENT_MODE must be production")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "typescript_route_owner_required")
            and file_contains("ui/next-app/app/api/mis/[...path]/route.ts", "python_proxy_performed: false")
            and file_contains("scripts/nextjs_production_python_proxy_fail_closed_smoke.py", "nextjs_production_python_proxy_fail_closed_v2")
            and file_contains("scripts/nextjs_production_python_proxy_fail_closed_smoke.py", "EXPECTED_COMPILED_API_ROUTE_KEYS")
            and file_contains("scripts/nextjs_production_python_proxy_fail_closed_smoke.py", "EXPECTED_DIRECT_READ_ROUTE_COUNT = 10")
            and file_contains("scripts/nextjs_production_python_proxy_fail_closed_smoke.py", "EXPECTED_APPROVAL_DECISION_ROUTE_COUNT = 2")
            and file_contains("scripts/nextjs_production_python_proxy_fail_closed_smoke.py", "EXPECTED_WORKSPACE_PROXY_ROUTE_COUNT = 16")
            and file_contains("scripts/nextjs_production_python_proxy_fail_closed_smoke.py", '"compiled_api_route_count": len(compiled_api_routes)')
            and file_contains("scripts/nextjs_production_python_proxy_fail_closed_smoke.py", "upstream_request_count")
            and file_contains("ui/next-app/package.json", '"test:control-plane-mode-contract"')
            and file_contains("ui/next-app/scripts/control-plane-mode-contract.ts", "control_plane_production_fail_closed_v1")
            and file_contains("ui/next-app/scripts/control-plane-mode-contract.ts", "production_python_catch_all_blocked")
            and file_contains("ui/next-app/scripts/control-plane-mode-contract.ts", "production_proxy_helper_blocked")
            and file_contains("ui/next-app/scripts/control-plane-mode-contract.ts", "explicit_local_dns_rebinding_blocked")
            and file_contains("ui/next-app/scripts/control-plane-mode-contract.ts", "unknown_deployment_mode_rejected")
            and file_contains("ui/next-app/src/server/controlPlane/auth.ts", "authenticateAgentGateway")
            and file_contains("ui/next-app/src/server/controlPlane/auth.ts", "allowMissing")
            and file_contains("ui/next-app/scripts/human-session-timestamp-contract.ts", "missing_gateway_session_expiry_expires")
            and file_contains("ui/next-app/scripts/human-session-timestamp-contract.ts", "malformed_login_window_blocks")
            and file_contains("ui/next-app/src/server/controlPlane/auth.ts", "FROM agent_gateway_tokens WHERE token_id=$1 FOR UPDATE")
            and file_contains("ui/next-app/src/server/controlPlane/auth.ts", "WHERE session_id=$1 AND session_hash=$2 FOR UPDATE")
            and file_contains("ui/next-app/src/server/controlPlane/db.ts", "error.commitTransaction")
            and file_contains("ui/next-app/src/server/controlPlane/ledger.ts", "pg_advisory_xact_lock(1095779668)")
            and file_contains("server.py", "pg_advisory_xact_lock(?)")
            and file_contains("server.py", "1095779668")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayTasks.ts", "typescript_postgres")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayTasks.ts", "task_immutable_binding_conflict")
            and file_contains("ui/next-app/app/api/mis/agent-gateway/tasks/route.ts", "controlPlaneMode")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayRuns.ts", "run_immutable_binding_conflict")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayRuns.ts", "agent_gateway.task_run_start")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayRuns.ts", "heartbeatAgentGatewayRun")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayRuns.ts", "agent_gateway.task_run_heartbeat")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayRuns.ts", "run_terminal_conflict")
            and file_contains("ui/next-app/app/api/mis/agent-gateway/runs/start/route.ts", "startAgentGatewayRun")
            and file_contains("ui/next-app/app/api/mis/agent-gateway/runs/[runId]/heartbeat/route.ts", "heartbeatAgentGatewayRun")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayEvidence.ts", "recordAgentGatewayToolCall")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayEvidence.ts", "submitAgentGatewayEvaluation")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayEvidence.ts", "recordAgentGatewayArtifact")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayEvidence.ts", "tool_call_approval_required")
            and file_contains("ui/next-app/app/api/mis/agent-gateway/tool-calls/route.ts", "recordAgentGatewayToolCall")
            and file_contains("ui/next-app/app/api/mis/agent-gateway/evaluations/submit/route.ts", "submitAgentGatewayEvaluation")
            and file_contains("ui/next-app/app/api/mis/agent-gateway/artifacts/route.ts", "recordAgentGatewayArtifact")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayPlans.ts", "createAgentGatewayPlan")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayPlans.ts", "createAgentGatewayPlanEvidenceManifest")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayPlans.ts", "run.workspace_id=$2")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayRuns.ts", "verified_agent_plan_required")
            and file_contains("ui/next-app/app/api/mis/agent-gateway/agent-plans/route.ts", "createAgentGatewayPlan")
            and file_contains("ui/next-app/app/api/mis/agent-gateway/plan-evidence-manifests/route.ts", "createAgentGatewayPlanEvidenceManifest")
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", "nextjs_postgres_control_plane_tasks_v1")
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", "/api/mis/agent-gateway/agent-plans")
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", "/api/mis/agent-gateway/plan-evidence-manifests")
            and file_contains(
                "scripts/nextjs_postgres_control_plane_tasks_smoke.py",
                '"python_api_unreachable_before_and_after"',
            )
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"audit_chain_valid"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"cross_language_audit_chain_valid"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"typescript_audit_lock_waited"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"python_audit_lock_waited"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"expired_token_state_committed"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"orphan_session_state_committed"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"session_request_waited_for_parent_lock"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"session_parent_revoke_lock_order_consistent"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"session_rejected_after_parent_revoke"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"typescript_run_start_owned"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"run_repeat_idempotent"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"concurrent_run_start_single_winner"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"run_immutable_binding_enforced"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"typescript_run_heartbeat_owned"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"run_heartbeat_repeat_idempotent"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"concurrent_terminal_heartbeat_single_winner"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"conflicting_terminal_heartbeat_single_winner"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"typescript_agent_plan_owned"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"concurrent_agent_plan_single_winner"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"agent_plan_immutable"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"agent_plan_human_status_protected"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"non_mock_run_requires_agent_plan"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"approval_required_agent_plan_blocks_run"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"concurrent_tool_call_single_winner"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"concurrent_evaluation_single_winner"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"concurrent_artifact_single_winner"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"typescript_plan_evidence_owned"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"concurrent_manifest_single_winner"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"manifest_verification_passed"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"manifest_immutable"')
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayPlans.ts", "plan_evidence_expected_steps_conflict")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayPlans.ts", "expected_steps_match_plan")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayPlans.ts", "tool_evidence_complete")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayPlans.ts", "evaluation_evidence_complete")
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"manifest_expected_steps_server_derived"')
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"manifest_complete_run_evidence_enforced"')
            and file_contains("scripts/nextjs_postgres_real_worker_human_review_smoke.py", '"manifest_authority_guards_passed"')
            and file_contains(
                "scripts/nextjs_postgres_control_plane_tasks_smoke.py",
                '"manifest_cross_workspace_evidence_blocked"',
            )
            and file_contains("scripts/nextjs_postgres_control_plane_tasks_smoke.py", '"high_risk_tool_forced_waiting_approval"')
            and file_contains(".github/workflows/commercial-migration-ci.yml", "nextjs_postgres_control_plane_tasks")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "nextjs_postgres_control_plane_tasks_v1")
            and (ROOT / "scripts" / "nextjs_postgres_control_plane_tasks_smoke.py").exists(),
            "The TypeScript-owned Agent Gateway task/run lifecycle, Agent Plan, verified plan-evidence manifest, and immutable execution-evidence routes default to Postgres in production, retain local proxy rollback, use workspace-scoped complete-run evidence queries plus server-derived locked plan steps and consistent task/run, evidence-ID, and parent-token/session locking, force risky tools to approval, require verified plans for non-mock run start, and have no-Python dynamic and real-Runtime negative receipts",
        ),
        check(
            "nextjs_postgres_workspace_read_models_surface_exists",
            file_contains("ui/next-app/src/server/controlPlane/workspaceReadModels.ts", "authenticateHumanMember")
            and file_contains("ui/next-app/src/server/controlPlane/workspaceReadModels.ts", "audit.workspace_id=$1")
            and file_contains("ui/next-app/src/server/controlPlane/workspaceReadModels.ts", "metadata_json::jsonb ->> 'workspace_id'=$1")
            and file_contains("ui/next-app/src/server/controlPlane/workspaceReadModels.ts", "JOIN tasks task")
            and file_contains("ui/next-app/src/server/controlPlane/workspaceReadModels.ts", "JOIN runs run")
            and file_contains("ui/next-app/src/server/controlPlane/humanSession.ts", "membershipResult.rows.length !== 1")
            and file_contains("ui/next-app/src/lib/misServer.ts", "typescript_route_owner_required")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "Select workspace")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "loadHumanSession")
            and file_contains("ui/next-app/src/components/WorkspaceDashboard.tsx", "setActiveWorkspaceId")
            and file_contains("ui/next-app/src/lib/mis.ts", "agentops_active_workspace")
            and file_contains("ui/next-app/app/api/mis/tasks/route.ts", "listWorkspaceTasks")
            and file_contains("ui/next-app/app/api/mis/runs/route.ts", "listWorkspaceRuns")
            and file_contains("ui/next-app/app/api/mis/approvals/route.ts", "listWorkspaceApprovals")
            and file_contains("ui/next-app/app/api/mis/audit/route.ts", "listWorkspaceAudit")
            and file_contains("ui/next-app/app/api/mis/dashboard/metrics/route.ts", "workspaceDashboardMetrics")
            and file_contains("ui/next-app/app/api/mis/tasks/[taskId]/route.ts", "getWorkspaceTaskDetail")
            and file_contains("ui/next-app/app/api/mis/runs/[runId]/route.ts", "getWorkspaceRunDetail")
            and file_contains("ui/next-app/app/api/mis/runs/[runId]/graph/route.ts", "getWorkspaceRunGraph")
            and file_contains("ui/next-app/app/api/mis/tool-calls/route.ts", "listWorkspaceToolCalls")
            and file_contains("ui/next-app/app/api/mis/evaluations/route.ts", "listWorkspaceEvaluations")
            and file_contains("ui/next-app/app/api/mis/approvals/[approvalId]/[decision]/route.ts", "decideWorkspaceApproval")
            and file_contains("ui/next-app/src/server/controlPlane/approvalDecisions.ts", "prepared_action_required")
            and file_contains("ui/next-app/src/server/controlPlane/approvalDecisions.ts", "verifyLatestWorkspacePlanEvidence")
            and file_contains("ui/next-app/src/server/controlPlane/approvalDecisions.ts", "customer_delivery_run_incomplete")
            and file_contains("ui/next-app/src/server/controlPlane/approvalDecisions.ts", "approver_user_id=$2")
            and file_contains("migrations/postgres/20260719_workspace_read_models_v2.sql", "audit_logs_workspace_metadata_match")
            and file_contains("migrations/postgres/20260719_workspace_read_models_v2.sql", "SET LOCAL lock_timeout")
            and file_contains("migrations/postgres/20260719_workspace_read_models_v2_online_indexes.sql", "CREATE INDEX CONCURRENTLY")
            and file_contains("ui/next-app/src/server/controlPlane/ledger.ts", "workspaceId: string | null")
            and file_contains("ui/next-app/scripts/workspace-read-model-contract.ts", "nextjs_postgres_workspace_read_models_v1")
            and file_contains("ui/next-app/scripts/workspace-read-model-contract.ts", "authenticated_http_routes_return_private_200")
            and file_contains("ui/next-app/scripts/approval-decision-contract.ts", "nextjs_postgres_human_approval_decision_v1")
            and file_contains("ui/next-app/scripts/approval-decision-contract.ts", "concurrent_same_key_16_way_single_winner")
            and file_contains("ui/next-app/scripts/approval-decision-contract.ts", "customer_delivery_requires_completed_run")
            and file_contains("ui/next-app/scripts/approval-decision-contract.ts", "approval_kind_explicit_immutable_and_edge_bound")
            and file_contains("ui/next-app/scripts/approval-decision-contract.ts", "enrollment_approval_unique_binding")
            and file_contains("ui/next-app/scripts/approval-decision-contract.ts", "enrollment_approval_delete_must_not_orphan_child")
            and file_contains("ui/next-app/scripts/approval-decision-contract.ts", "parent_first_lock_order_deadlock_free")
            and file_contains("ui/next-app/scripts/approval-decision-contract.ts", "tool_before_approval")
            and file_contains("ui/next-app/scripts/approval-decision-contract.ts", "production_python_proxy_blocked")
            and file_contains("ui/next-app/app/api/mis/agent-gateway/approvals/request/route.ts", "requestCustomerDeliveryApproval")
            and file_contains("ui/next-app/app/api/mis/agent-gateway/approvals/request/route.ts", "explicitFreeLocalProxyMode")
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayApprovals.ts", '"approvals:request"')
            and file_contains("ui/next-app/src/server/controlPlane/agentGatewayApprovals.ts", "verifyLatestWorkspacePlanEvidence")
            and file_contains("ui/next-app/scripts/customer-delivery-approval-request-contract.ts", "nextjs_postgres_customer_delivery_approval_request_v1")
            and file_contains("ui/next-app/scripts/customer-delivery-approval-request-contract.ts", "concurrent_single_winner_no_duplicate_evidence")
            and file_contains("scripts/nextjs_postgres_real_worker_human_review_smoke.py", "real_run_bound_delivery_decisions_completed")
            and file_contains("scripts/nextjs_postgres_real_worker_human_review_smoke.py", '"worker_created_delivery_approvals": all(')
            and file_contains("scripts/nextjs_postgres_real_worker_human_review_smoke.py", '"delivery_approval_creation_source": "production_next_typescript_postgres_agent_gateway_route"')
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "nextjs_postgres_workspace_read_models_v1")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "nextjs_postgres_human_approval_decision_v1")
            and file_contains("ui/next-app/package.json", '"test:workspace-read-model-contract"')
            and file_contains("ui/next-app/package.json", '"test:approval-decision-contract"')
            and file_contains("ui/next-app/package.json", '"test:customer-delivery-approval-request-contract"')
            and file_contains("ui/next-app/package.json", '"test:human-schema-upgrade-contract"')
            and file_contains("ui/next-app/src/server/controlPlane/schemaReadiness.ts", 'HUMAN_MEMORY_SCHEMA_VERSION = "20260724_customer_delivery_run_unique_v5"')
            and file_contains("ui/next-app/src/server/controlPlane/schemaReadiness.ts", 'HUMAN_MEMORY_SCHEMA_V4_VERSION = "20260719_approval_kind_bindings_v4"')
            and file_contains("ui/next-app/src/server/controlPlane/schemaReadiness.ts", "idx_approvals_customer_delivery_run_unique")
            and file_contains("ui/next-app/scripts/schema-readiness-contract.ts", "human_memory_schema_readiness_v5")
            and file_contains("ui/next-app/scripts/schema-readiness-contract.ts", "customer_delivery_run_unique_predicate_drift_rejected")
            and file_contains("ui/next-app/scripts/schema-readiness-contract.ts", "non_deferred_binding_trigger_rejected")
            and file_contains("ui/next-app/scripts/schema-migration-upgrade-contract.ts", "human_memory_schema_v1_v2_v3_v4_to_v5_upgrade_v1")
            and file_contains("ui/next-app/scripts/schema-migration-upgrade-contract.ts", "exact_v4_receipt_upgraded")
            and file_contains("ui/next-app/scripts/schema-migration-upgrade-contract.ts", "duplicate_customer_delivery_preflight_failed_closed")
            and file_contains("ui/next-app/scripts/schema-migration-upgrade-contract.ts", "concurrent_customer_delivery_insert_database_enforced")
            and file_contains("ui/next-app/scripts/schema-migration-upgrade-contract.ts", "approval_kind_is_explicit_without_default")
            and file_contains("ui/next-app/scripts/schema-migration-upgrade-contract.ts", "five_approval_kinds_backfilled")
            and file_contains("ui/next-app/scripts/schema-migration-upgrade-contract.ts", "deferred_approval_binding_triggers_ready")
            and file_contains("ui/next-app/scripts/schema-migration-upgrade-contract.ts", "enrollment_approval_unique_binding_enforced")
            and file_contains("migrations/postgres/20260719_approval_kind_bindings_v4.sql", "ALTER COLUMN approval_kind DROP DEFAULT")
            and file_contains("migrations/postgres/20260719_approval_kind_bindings_v4.sql", "run_execution")
            and file_contains("migrations/postgres/20260719_approval_kind_bindings_v4.sql", "tool_execution")
            and file_contains("migrations/postgres/20260719_approval_kind_bindings_v4.sql", "prepared_action")
            and file_contains("migrations/postgres/20260719_approval_kind_bindings_v4.sql", "agent_enrollment")
            and file_contains("migrations/postgres/20260719_approval_kind_bindings_v4.sql", "customer_delivery")
            and file_contains("migrations/postgres/20260719_approval_kind_bindings_v4.sql", "agentops_enforce_approval_kind_immutable")
            and file_contains("migrations/postgres/20260719_approval_kind_bindings_v4.sql", "DEFERRABLE INITIALLY DEFERRED")
            and file_contains("migrations/postgres/20260719_approval_kind_bindings_v4.sql", "AFTER INSERT OR UPDATE OR DELETE")
            and file_contains("migrations/postgres/20260719_approval_kind_bindings_v4.sql", "idx_agent_gateway_enrollment_approval_unique")
            and file_contains("migrations/postgres/20260724_customer_delivery_run_unique_v5.sql", "customer_delivery_approval_run_duplicate")
            and file_contains("migrations/postgres/20260724_customer_delivery_run_unique_v5.sql", "idx_approvals_customer_delivery_run_unique")
            and file_contains("migrations/postgres/20260719_human_approval_decisions_v3.sql", "human_approval_decision_requests")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "nextjs_postgres_workspace_read_models")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "nextjs_postgres_human_approval_decision")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "nextjs_postgres_customer_delivery_approval_request")
            and file_contains(".github/workflows/commercial-migration-ci.yml", "human_schema_v1_v2_v3_v4_to_v5_upgrade"),
            "Human Session Workspace reads/decisions and Agent Gateway customer-delivery request creation are direct TypeScript/Postgres owners with exact v5 schema readiness, immutable edge-bound kinds, database-unique delivery binding, production Python blocking, concurrency evidence, and a real Hermes/OpenClaw Worker-to-Human acceptance; expiry reconciliation, policy, resume, enrollment issue, and release-grade execution receipts remain open",
        ),
        check(
            "postgres_cli_write_parity_surface_exists",
            file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_cli_write_parity_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "storage_postgres_cli_write_parity_smoke.py")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "storage_postgres_cli_write_parity_smoke.py")
            and file_contains("docs/AGENT_GATEWAY_CLI_SPEC.md", "Postgres CLI write parity helper")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "postgres_cli_write_parity_v1")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "run_cli(")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "http_write.server_env")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "agent_heartbeat")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "task_create")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "task_claim")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "run_start")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "run_heartbeat")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "toolcall_record")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "evaluation_submit")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "artifact_record")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "agent_plan_create")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "plan_evidence_create")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "memory_propose")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "approval_request")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "audit_emit")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "run_completion_heartbeat")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "cli_read_only_task_status")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "cli_missing_scope_status")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "cli_non_allowlisted_write_status")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "postgres_cli_gateway_run_completion_heartbeat_write_v1")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "gateway_manifest_status")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "gateway_token_last_heartbeat")
            and file_contains("scripts/storage_postgres_cli_write_parity_smoke.py", "gateway_run_completion_heartbeat_audit_count")
            and (ROOT / "scripts" / "storage_postgres_cli_write_parity_smoke.py").exists(),
            "Postgres-backed Agent Gateway CLI/API write parity smoke uses actual agentops commands for scoped task, run, heartbeat, evidence, Agent Plan, plan-evidence, memory, approval, audit, and completion heartbeat writes while checking fail-closed CLI guards",
        ),
        check(
            "byoc_deployment_acceptance_surface_exists",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "byoc_deployment_acceptance_v1")
            and file_contains("docs/CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md", "agentops_signed_audit_export.py")
            and file_contains("docs/CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md", "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture")
            and file_contains("docs/UI_API_PARITY_MATRIX.json", "byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "byoc_deployment_acceptance_v1")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "--postgres-readiness-fixture")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "deployment_readiness_postgres_runtime_write_fixture_v1")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "runtime_write_gate_status")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "experimental_write_http")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "postgres_read_only_backend")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "postgres_counts_unchanged")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "signed_audit_export")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "tamper_detected")
            and file_contains("scripts/agentops_signed_audit_export.py", "signed_audit_export_v1")
            and file_contains("scripts/agentops_signed_audit_export.py", "signing_key_required")
            and file_contains("scripts/local_readiness_smoke.py", "byoc_deployment_acceptance_smoke")
            and file_contains("server.py", "deployment_checks")
            and file_contains("server.py", "signed_export_tamper_detection")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "Recovery drill")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "Signed export")
            and file_contains("ui/next-app/README.md", "deployment_readiness_smoke.py --postgres-write-fixture")
            and file_contains("ui/next-app/README.md", "nextjs_playwright_snapshot_smoke.py --postgres-write-fixture")
            and (ROOT / "scripts" / "agentops_signed_audit_export.py").exists()
            and (ROOT / "scripts" / "byoc_deployment_acceptance_smoke.py").exists(),
            "Gate 5 BYOC deployment acceptance covers backup/restore confirmation, pre-restore safety copy, signed audit export key requirement, tamper detection, raw metadata omission, Postgres runtime write-gate readiness, and Next.js deployment readiness",
        ),
        check(
            "postgres_backup_restore_surface_exists",
            (ROOT / "scripts" / "agentops_postgres_backup.py").exists()
            and (ROOT / "scripts" / "agentops_postgres_backup_smoke.py").exists()
            and file_contains("scripts/agentops_postgres_backup.py", "postgres_backup_restore_v1")
            and file_contains("scripts/agentops_postgres_backup.py", "postgres_backup_manifest_v1")
            and file_contains("scripts/agentops_postgres_backup.py", "backup_manifest_not_found")
            and file_contains("scripts/agentops_postgres_backup.py", "target_state_confirmation_required")
            and file_contains("scripts/agentops_postgres_backup_smoke.py", '"skipped": False')
            and file_contains("scripts/agentops_postgres_backup_smoke.py", '"contract": "postgres_backup_restore_v1"')
            and file_contains("scripts/agentops_postgres_backup_smoke.py", '"manifest_contract": "postgres_backup_manifest_v1"')
            and file_contains("scripts/agentops_postgres_backup_smoke.py", "source_counts")
            and file_contains("scripts/agentops_postgres_backup_smoke.py", "restored_counts")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "POSTGRES_BACKUP_SMOKE")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", 'recovery.get("skipped") is not True')
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "postgres_backup_restore_v1")
            and file_contains("scripts/byoc_deployment_acceptance_smoke.py", "postgres_backup_manifest_v1")
            and file_contains("server.py", "def postgres_backup_restore_receipt")
            and file_contains("server.py", '"postgres_file_presence_is_acceptance": False')
            and file_contains("server.py", '"postgres_acceptance_requires_non_skipped": True')
            and file_contains("server.py", '"postgres_acceptance_head_current"')
            and file_contains("server.py", "AGENTOPS_BUILD_SHA")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "pg recovery")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "pg non-skipped")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "pg current head")
            and file_contains("docs/CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md", "python3 scripts/agentops_postgres_backup_smoke.py")
            and file_contains("docs/CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md", "AGENTOPS_BUILD_SHA")
            and file_contains("docs/POSTGRES_PARITY_CONTRACT.md", "postgres_backup_restore_v1")
            and file_contains("docs/STORAGE_BOUNDARY_MAP.md", "Postgres BYOC backup/restore")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "skipped=true")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "postgres_backup_restore_requires_non_skipped_evidence")
            and file_contains("docs/COMMERCIAL_RELEASE_EVIDENCE_PACKET.json", "postgres_backup_manifest_v1")
            and file_contains("scripts/commercial_release_evidence_packet_smoke.py", "Postgres recovery non-skipped evidence policy missing"),
            "Gate 5 exposes Postgres archive/manifest recovery contracts, requires a non-skipped container receipt, and keeps utility file presence separate from real acceptance in API and Next.js",
        ),
        check(
            "deployment_readiness_surface_exists",
            file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "deployment_readiness_v1")
            and file_contains("docs/COMMERCIAL_MIGRATION_CLOSED_LOOP.md", "enterprise_byoc_controls_v1")
            and file_contains("server.py", "def deployment_readiness")
            and file_contains("server.py", "def enterprise_byoc_controls")
            and file_contains("server.py", "/api/deployment/readiness")
            and file_contains("server.py", "/api/deployment/enterprise-controls")
            and file_contains("server.py", "AGENTOPS_ENTERPRISE_CONTROLS_PATH")
            and file_contains("agentops_mis_cli/agentops.py", "cmd_deployment_readiness")
            and file_contains("agentops_mis_cli/agentops.py", "cmd_deployment_enterprise_controls")
            and file_contains("agentops_mis_cli/agentops.py", 'sub.add_parser("deployment"')
            and file_contains("scripts/deployment_readiness_smoke.py", "deployment_readiness_v1")
            and file_contains("scripts/deployment_readiness_smoke.py", "enterprise_byoc_controls_v1")
            and file_contains("scripts/deployment_readiness_smoke.py", "audit_retention_policy_v1")
            and file_contains("scripts/deployment_readiness_smoke.py", "audit_retention_controls_v1")
            and file_contains("scripts/deployment_readiness_smoke.py", "--configured-retention-fixture")
            and file_contains("scripts/deployment_readiness_smoke.py", "--configured-enterprise-fixture")
            and file_contains("scripts/deployment_readiness_smoke.py", "--postgres-write-fixture")
            and file_contains("scripts/deployment_readiness_smoke.py", "deployment_readiness_postgres_runtime_write_fixture_v1")
            and file_contains("scripts/deployment_readiness_smoke.py", "validate_postgres_write_readiness")
            and file_contains("scripts/deployment_readiness_smoke.py", "runtime_write_gate")
            and file_contains("scripts/deployment_readiness_smoke.py", "POST /api/integrations/openclaw/probe")
            and file_contains("scripts/deployment_readiness_smoke.py", "POST /api/integrations/hermes/run-task")
            and file_contains("scripts/deployment_readiness_smoke.py", "POST /api/approvals/:approval_id/approve")
            and file_contains("docs/CUSTOMER_LOCAL_DEPLOYMENT_RUNBOOK.md", "deployment_readiness_smoke.py --postgres-write-fixture")
            and file_contains("ui/next-app/README.md", "fixed Postgres runtime write-gate readiness")
            and file_contains("scripts/deployment_readiness_smoke.py", "validate_configured_retention")
            and file_contains("scripts/deployment_readiness_smoke.py", "validate_configured_enterprise")
            and file_contains("scripts/deployment_readiness_smoke.py", "AGENTOPS_RETENTION_CONTROLS_PATH")
            and file_contains("scripts/deployment_readiness_smoke.py", "pro_workspace")
            and file_contains("scripts/deployment_readiness_smoke.py", "enterprise_byoc")
            and file_contains("scripts/deployment_readiness_smoke.py", "write_enterprise_controls_fixture")
            and file_contains("scripts/deployment_readiness_smoke.py", "sso_connector_policy")
            and file_contains("scripts/deployment_readiness_smoke.py", "custom_connector_sdk")
            and file_contains("scripts/deployment_readiness_smoke.py", "private_connector_total")
            and file_contains("scripts/deployment_readiness_smoke.py", "raw-private-connector-token")
            and file_contains("scripts/deployment_readiness_smoke.py", "legal_hold_registry_configured")
            and file_contains("scripts/deployment_readiness_smoke.py", "active_legal_holds")
            and file_contains("scripts/deployment_readiness_smoke.py", "cleanup_approval_required")
            and file_contains("scripts/deployment_readiness_smoke.py", "legal_hold_required_before_cleanup")
            and file_contains("scripts/deployment_readiness_smoke.py", "cleanup_endpoint_exposed")
            and file_contains("scripts/deployment_readiness_smoke.py", "destructive_cleanup_supported")
            and file_contains("scripts/deployment_readiness_smoke.py", "db_dump_hash")
            and file_contains("scripts/deployment_readiness_smoke.py", "agentops-deployment")
            and file_contains("scripts/audit_retention_policy_smoke.py", "audit_retention_policy_v1")
            and file_contains("scripts/audit_retention_policy_smoke.py", "delete_performed")
            and file_contains("scripts/audit_retention_policy_smoke.py", "db_dump_hash")
            and file_contains("scripts/audit_retention_controls_smoke.py", "audit_retention_controls_v1")
            and file_contains("scripts/audit_retention_controls_smoke.py", "cleanup_approval_required")
            and file_contains("scripts/audit_retention_controls_smoke.py", "--configured-fixture")
            and file_contains("scripts/audit_retention_controls_smoke.py", "validate_configured_registry")
            and file_contains("scripts/audit_retention_controls_smoke.py", "cannot_assert_no_holds")
            and file_contains("scripts/audit_retention_controls_smoke.py", "Highly confidential subject")
            and file_contains("config/retention-controls.example.json", '"legal_hold_registry_configured": true')
            and file_contains("config/retention-controls.example.json", '"legal_holds"')
            and file_contains("config/retention-controls.example.json", '"status": "active"')
            and file_contains("config/enterprise-controls.example.json", '"registry_configured": true')
            and file_contains("config/enterprise-controls.example.json", '"trust_policy_configured": true')
            and file_contains("scripts/audit_retention_controls_smoke.py", "db_dump_hash")
            and file_contains("server.py", "def audit_retention_policy")
            and file_contains("server.py", "def audit_retention_controls")
            and file_contains("server.py", "/api/audit/retention-policy")
            and file_contains("server.py", "/api/audit/retention-controls")
            and file_contains("agentops_mis_cli/agentops.py", "cmd_audit_retention_policy")
            and file_contains("agentops_mis_cli/agentops.py", "cmd_audit_retention_controls")
            and file_contains("scripts/nextjs_parity_smoke.py", "loadServerDeploymentReadiness")
            and file_contains("ui/next-app/src/lib/misServer.ts", "/deployment/readiness")
            and file_contains("ui/next-app/src/lib/misServer.ts", "/deployment/enterprise-controls")
            and file_contains("ui/next-app/src/lib/misServer.ts", "/audit/retention-policy")
            and file_contains("ui/next-app/src/lib/misServer.ts", "/audit/retention-controls")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "Deployment readiness verdict")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "audit_retention_policy_v1")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "audit_retention_controls_v1")
            and file_contains("ui/next-app/src/components/DeploymentPage.tsx", "private connectors")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "verify_deployment_configured_retention")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "deployment_configured_retention_controls")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "--configured-retention-fixture")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "nextjs_deployment_configured_retention_fixture_v1")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "--postgres-write-fixture")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "nextjs_deployment_postgres_runtime_write_fixture_v1")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "verify_deployment_postgres_write_gate")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "runtime_write_gate")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "POST /api/integrations/openclaw/probe")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "POST /api/integrations/hermes/run-task")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "POST /api/approvals/:approval_id/approve")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "enterprise_byoc_controls_v1")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "enterprise_byoc")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "sso_connector_policy")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "connector sdk true")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "private connectors 1/2")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "AGENTOPS_RETENTION_CONTROLS_PATH")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "AGENTOPS_ENTERPRISE_CONTROLS_PATH")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "active_legal_holds")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "cleanup_endpoint_exposed")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "destructive_cleanup_supported")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "retention-controls?cleanup=true")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "dangerous_cleanup_parameter_rejected")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "Raw Next deployment legal hold reason")
            and file_contains("scripts/nextjs_playwright_snapshot_smoke.py", "db_dump_hash")
            and (ROOT / "scripts" / "deployment_readiness_smoke.py").exists(),
            "Gate 5 deployment readiness API, CLI, smoke, audit retention policy/controls previews, configured Enterprise SSO/private connector proof, and configured Next.js verdict panel are present",
        ),
        check(
            "blocked_generated_or_runtime_artifacts_absent",
            not blocked_paths,
            "blocked_paths=" + json.dumps(blocked_paths, ensure_ascii=False),
            "git status --short",
        ),
    ]

    gates = [
        {
            "id": "gate_0",
            "name": "Isolated Commercial Track",
            "status": "ready" if checks[0]["ok"] and checks[1]["ok"] and checks[-1]["ok"] else "blocked",
            "verify": ["python3 scripts/commercial_migration_readiness.py", "git diff --check"],
        },
        {
            "id": "gate_1",
            "name": "Product Packaging and Entitlement",
            "status": "next",
            "verify": ["entitlement smoke test", "token omission check"],
        },
        {
            "id": "gate_2",
            "name": "Production Safety Baseline",
            "status": "next",
            "verify": [
                "python3 scripts/production_auth_fail_closed_smoke.py --configured-production-fixture",
                "python3 scripts/security_production_readiness_smoke.py --configured-production-fixture",
                "python3 scripts/agent_gateway_scope_matrix_smoke.py --isolated-fixture",
                "python3 scripts/workspace_isolation_smoke.py --isolated-fixture",
                "python3 scripts/workspace_rbac_governance_smoke.py --isolated-fixture",
                "python3 scripts/workspace_memory_session_governance_smoke.py --isolated-fixture",
            ],
        },
        {
            "id": "gate_3",
            "name": "Storage Boundary Before Postgres",
            "status": "next",
            "verify": [
                "python3 scripts/storage_boundary_sqlite_smoke.py",
                "python3 scripts/storage_postgres_contract_smoke.py",
                "python3 scripts/storage_postgres_container_smoke.py",
                "python3 scripts/storage_postgres_adapter_contract_smoke.py",
                "python3 scripts/storage_postgres_optional_adapter_smoke.py",
                "python3 scripts/storage_postgres_boundary_parity_smoke.py",
                "python3 scripts/storage_postgres_route_read_model_smoke.py",
                "python3 scripts/storage_backend_selection_smoke.py",
                "python3 scripts/storage_postgres_http_read_parity_smoke.py",
                "python3 scripts/storage_postgres_cli_read_parity_smoke.py",
                "python3 scripts/storage_postgres_write_helper_parity_smoke.py",
                "python3 scripts/storage_postgres_http_write_task_smoke.py",
                "python3 scripts/storage_postgres_gateway_lifecycle_smoke.py",
                "python3 scripts/storage_postgres_cli_write_parity_smoke.py",
            ],
        },
        {
            "id": "gate_4",
            "name": "UI/API Parity Before Next.js",
            "status": "started",
            "verify": [
                "python3 scripts/nextjs_parity_smoke.py",
                "python3 scripts/commercial_evidence_receipts_smoke.py",
                "python3 scripts/commercial_current_evidence_status_smoke.py",
                "python3 scripts/commercial_handoff_status_smoke.py",
                "python3 scripts/release_evidence_packet_smoke.py",
                "python3 scripts/commercial_release_evidence_packet_smoke.py",
                "python3 scripts/release_freeze_protocol_smoke.py",
                "python3 scripts/merge_readiness_status_smoke.py",
                "cd ui/start-building-app && npm run build",
                "cd ui/next-app && npm run build",
                "python3 scripts/ui_api_parity_matrix_smoke.py",
                "python3 scripts/ui_task_run_route_parity_smoke.py",
                "python3 scripts/ui_route_naming_decision_smoke.py",
                "python3 scripts/ui_legacy_route_alias_smoke.py",
                "python3 scripts/ui_navigation_inventory_smoke.py",
                "python3 scripts/ui_route_retirement_packet_smoke.py",
                "python3 scripts/ui_admin_operations_route_retirement_smoke.py",
                "python3 scripts/ui_covered_route_retirement_packet_smoke.py",
                "python3 scripts/pixel_office_dispatch_retirement_evidence_smoke.py",
                "python3 scripts/nextjs_agent_gateway_task_proxy_smoke.py",
                "python3 scripts/nextjs_agent_gateway_cli_worker_dogfood_smoke.py",
                "python3 scripts/nextjs_worker_dispatch_once_smoke.py",
                "python3 scripts/nextjs_pixel_office_floor_smoke.py",
                "python3 scripts/nextjs_pixel_office_dispatch_smoke.py",
                "python3 scripts/nextjs_control_tower_parity_smoke.py",
                "python3 scripts/nextjs_template_switching_smoke.py",
                "python3 scripts/local_brief_prepared_action_smoke.py",
                "python3 scripts/nextjs_local_brief_smoke.py",
                "python3 scripts/nextjs_customer_worker_dispatch_smoke.py",
                "python3 scripts/nextjs_customer_worker_async_job_smoke.py",
                "python3 scripts/nextjs_customer_worker_prepared_action_smoke.py",
                "python3 scripts/nextjs_worker_stuck_release_smoke.py",
                "python3 scripts/nextjs_worker_daemon_control_smoke.py",
                "python3 scripts/nextjs_enrollment_request_smoke.py",
                "python3 scripts/nextjs_worker_gateway_lifecycle_guard_smoke.py",
                "python3 scripts/nextjs_worker_console_parity_smoke.py",
                "python3 scripts/operator_execution_mode_smoke.py",
                "python3 scripts/vite_playwright_snapshot_smoke.py",
                "python3 scripts/nextjs_playwright_snapshot_smoke.py",
            ],
        },
        {
            "id": "gate_5",
            "name": "BYOC / Enterprise Deployment",
            "status": "planned",
            "verify": [
                "Postgres container parity smoke",
                "Postgres ledger acceptance",
                "python3 scripts/commercial_evidence_receipts_smoke.py",
                "python3 scripts/commercial_current_evidence_status_smoke.py",
                "python3 scripts/commercial_handoff_status_smoke.py",
                "python3 scripts/release_evidence_packet_smoke.py",
                "python3 scripts/commercial_release_evidence_packet_smoke.py",
                "python3 scripts/release_freeze_protocol_smoke.py",
                "python3 scripts/merge_readiness_status_smoke.py",
                "python3 scripts/audit_retention_policy_smoke.py --isolated-fixture",
                "python3 scripts/audit_retention_controls_smoke.py --configured-fixture",
                "python3 scripts/deployment_readiness_smoke.py --configured-retention-fixture --configured-enterprise-fixture",
                "python3 scripts/deployment_readiness_smoke.py --postgres-write-fixture",
                "python3 scripts/nextjs_playwright_snapshot_smoke.py --configured-retention-fixture",
                "python3 scripts/nextjs_playwright_snapshot_smoke.py --postgres-write-fixture",
                "python3 scripts/nextjs_postgres_control_plane_tasks_smoke.py",
                "npm --prefix ui/next-app run test:workspace-read-model-contract",
                "npm --prefix ui/next-app run test:approval-decision-contract",
                "npm --prefix ui/next-app run test:human-schema-upgrade-contract",
                "python3 scripts/nextjs_postgres_human_memory_review_smoke.py --postgres-dsn postgresql://...",
                "python3 scripts/byoc_deployment_acceptance_smoke.py --postgres-readiness-fixture",
                "backup/restore and signed export checks",
            ],
        },
    ]

    engineering_surface_ready = all(item["ok"] for item in checks)
    declared_release_blocked = bool(human_memory_open_blockers)
    release_blocked_by_contract = bool(human_memory_effective_open_blockers)
    expected_blocker_status = "blocked" if declared_release_blocked else "ready"
    blocker_contract_truthful = (
        human_memory_blockers.get("status") == expected_blocker_status
        and human_memory_blockers.get("release_claim_allowed") == (not declared_release_blocked)
        and human_memory_blockers.get("closed_loop_claim_allowed") == (not declared_release_blocked)
    )
    command_ok = engineering_surface_ready and blocker_contract_truthful
    release_ready = command_ok and not release_blocked_by_contract
    payload = {
        "overall_status": "ready" if release_ready else "blocked",
        "engineering_surface_status": "ready" if engineering_surface_ready else "blocked",
        "release_status": "ready" if release_ready else "blocked",
        "release_claim_allowed": release_ready,
        "closed_loop_claim_allowed": release_ready,
        "readiness_contract_valid": command_ok,
        "open_release_blocker_ids": sorted(human_memory_blocker_ids),
        "declared_open_release_blocker_ids": sorted(human_memory_declared_blocker_ids),
        "external_real_runtime_receipt": runtime_receipt,
        "branch": branch,
        "worktree": str(ROOT),
        "strategy": {
            "rewrite_policy": "no_big_bang",
            "backend": "typescript_postgres_production_python_free_local_rollback_until_full_api_parity",
            "database": "postgres_default_for_commercial_control_plane_sqlite_free_local_only",
            "frontend": "nextjs_canonical_migration_track_with_vite_rollback_until_route_retirement",
            "agent_contract": "agent_gateway_cli_api_mcp_remains_durable",
        },
        "checks": checks,
        "phase_gates": gates,
        "pending_paths": paths,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    # Exit success means the checker and blocker contract are internally valid;
    # release eligibility is expressed only by the fail-closed payload fields.
    return 0 if command_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
