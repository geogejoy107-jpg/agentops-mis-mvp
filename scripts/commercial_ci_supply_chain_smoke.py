#!/usr/bin/env python3
"""Fail closed when commercial CI execution inputs are movable."""
from __future__ import annotations

import copy
import datetime as dt
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from types import ModuleType
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "commercial-migration-ci.yml"
REAL_RUNTIME_WORKFLOW = ROOT / ".github" / "workflows" / "commercial-real-runtime-acceptance.yml"
CONTRACT = "commercial_ci_supply_chain_pins_v1"
EXPECTED_ACTION_PINS = {
    "actions/checkout": "11bd71901bbe5b1630ceea73d27597364c9af683",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/setup-node": "49933ea5288caeca8642d1e84afbd3f7d6820020",
    "actions/attest": "f7c74d28b9d84cb8768d0b8ca14a4bac6ef463e6",
    "actions/upload-artifact": "ea165f8d65b6e75b540449e92b4886f43607fa02",
    "actions/download-artifact": "d3f86a106a0bac45b974a628896c90dbdf5c8093",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load_script_module(name: str, path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot load script module: {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def valid_runtime_payload() -> dict:
    guard = {
        "complete_run_tool_evidence_enforced": True,
        "complete_run_evaluation_evidence_enforced": True,
        "complete_run_artifact_evidence_enforced": True,
        "audit_evidence_server_derived": True,
        "customer_delivery_revalidation_blocked": True,
        "blocked_customer_delivery_request_persisted": False,
        "approved_customer_delivery_evidence_sealed": True,
    }
    return {
        "contract": "nextjs_postgres_real_worker_human_review_v1",
        "control_plane": "typescript_postgres",
        "adapters": ["hermes", "openclaw"],
        "workers": {
            adapter: {
                "provider_call_performed": True,
                "dry_run": False,
                "delivery_approval_creation_source": "production_next_typescript_postgres_agent_gateway_route",
                "delivery_approval_request_outcome": "created",
                "delivery_approval_runtime_event_count": 1,
                "delivery_approval_audit_count": 1,
            }
            for adapter in ("hermes", "openclaw")
        },
        "manifest_authority_guards": {
            adapter: dict(guard)
            for adapter in ("hermes", "openclaw")
        },
        "human_reviews": {
            adapter: {
                "delivery_approval_first_outcome": "updated",
                "delivery_approval_replay_outcome": "unchanged",
            }
            for adapter in ("hermes", "openclaw")
        },
        "runtime_dependency_identity": {
            "hermes_endpoint_sha256": "a" * 64,
            "openclaw_binary_sha256": "b" * 64,
        },
        "real_runtime_execution_performed": True,
        "manifest_authority_guards_passed": True,
        "real_run_bound_delivery_decisions_completed": True,
        "python_api_started": False,
        "python_or_sqlite_commercial_default": False,
        "worker_created_delivery_approvals": True,
        "delivery_approval_creation_source": "production_next_typescript_postgres_agent_gateway_route",
    }


def verify_runtime_claim_fail_closed(receipt: ModuleType, readiness: ModuleType) -> int:
    required_adapters = {"hermes", "openclaw"}
    fixture = valid_runtime_payload()
    claims = receipt.real_runtime_security_claims(fixture)
    require(receipt.real_runtime_security_claims_complete(claims), "valid Runtime claims were rejected")
    require(readiness.runtime_security_claims_valid(claims, required_adapters), "valid external Runtime claims were rejected")

    negative_root_claims = (
        "python_api_started",
        "python_or_sqlite_commercial_default",
        "worker_created_delivery_approvals",
    )
    cases = 1
    for claim_name in negative_root_claims:
        missing = copy.deepcopy(fixture)
        missing.pop(claim_name)
        missing_claims = receipt.real_runtime_security_claims(missing)
        require(missing_claims.get(claim_name) is None, f"missing {claim_name} was normalized to false")
        require(
            not receipt.real_runtime_security_claims_complete(missing_claims)
            and not readiness.runtime_security_claims_valid(missing_claims, required_adapters),
            f"missing {claim_name} was accepted",
        )

        string_false = copy.deepcopy(fixture)
        string_false[claim_name] = "false"
        string_claims = receipt.real_runtime_security_claims(string_false)
        require(string_claims.get(claim_name) is None, f"string {claim_name} was normalized to false")
        require(
            not receipt.real_runtime_security_claims_complete(string_claims)
            and not readiness.runtime_security_claims_valid(string_claims, required_adapters),
            f"string false {claim_name} was accepted",
        )
        cases += 2

    for adapter in required_adapters:
        for invalid_value in (None, "false"):
            invalid = copy.deepcopy(fixture)
            if invalid_value is None:
                invalid["workers"][adapter].pop("dry_run")
            else:
                invalid["workers"][adapter]["dry_run"] = invalid_value
            invalid_claims = receipt.real_runtime_security_claims(invalid)
            require(
                invalid_claims["adapter_claims"][adapter].get("dry_run") is None,
                f"invalid {adapter} dry_run was normalized to false",
            )
            require(
                not receipt.real_runtime_security_claims_complete(invalid_claims)
                and not readiness.runtime_security_claims_valid(invalid_claims, required_adapters),
                f"invalid {adapter} dry_run was accepted",
            )
            cases += 1

        missing_owner = copy.deepcopy(fixture)
        missing_owner["workers"][adapter].pop("delivery_approval_request_outcome")
        missing_owner_claims = receipt.real_runtime_security_claims(missing_owner)
        require(
            missing_owner_claims["adapter_claims"][adapter].get(
                "delivery_approval_created_through_production_owner"
            ) is None
            and not receipt.real_runtime_security_claims_complete(missing_owner_claims)
            and not readiness.runtime_security_claims_valid(
                missing_owner_claims,
                required_adapters,
            ),
            f"missing {adapter} production approval owner evidence was accepted",
        )
        cases += 1

        persisted_blocked_request = copy.deepcopy(fixture)
        persisted_blocked_request["manifest_authority_guards"][adapter][
            "blocked_customer_delivery_request_persisted"
        ] = True
        persisted_claims = receipt.real_runtime_security_claims(
            persisted_blocked_request
        )
        require(
            persisted_claims["adapter_claims"][adapter].get(
                "blocked_customer_delivery_request_persisted"
            ) is True
            and not receipt.real_runtime_security_claims_complete(persisted_claims)
            and not readiness.runtime_security_claims_valid(
                persisted_claims,
                required_adapters,
            ),
            f"persisted blocked {adapter} delivery request was accepted",
        )
        cases += 1

    string_true = copy.deepcopy(fixture)
    string_true["real_runtime_execution_performed"] = "true"
    string_true_claims = receipt.real_runtime_security_claims(string_true)
    require(
        string_true_claims.get("real_runtime_execution_performed") is None
        and not receipt.real_runtime_security_claims_complete(string_true_claims)
        and not readiness.runtime_security_claims_valid(string_true_claims, required_adapters),
        "string true Runtime claim was accepted",
    )
    return cases + 1


def verify_command_redaction(receipt: ModuleType, readiness: ModuleType) -> int:
    sensitive_names = ("token", "key", "secret", "password", "dsn", "url", "path", "bin")

    equals_command = ["tool", *[f"--fixture-{name}=synthetic-value" for name in sensitive_names]]
    equals_safe = receipt.safe_command(equals_command)
    require(
        equals_safe == ["tool", *[f"--fixture-{name}=[REDACTED]" for name in sensitive_names]],
        "equals-form sensitive arguments were not generically redacted",
    )

    split_command = ["tool"]
    split_expected = ["tool"]
    for name in sensitive_names:
        split_command.extend([f"--fixture-{name}", "synthetic-value"])
        split_expected.extend([f"--fixture-{name}", "[REDACTED]"])
    require(receipt.safe_command(split_command) == split_expected, "split sensitive arguments were not generically redacted")
    require(
        receipt.safe_command(["tool", "--fixture-token", "--value-shaped-like-an-option"])
        == ["tool", "--fixture-token", "[REDACTED]"],
        "split sensitive value beginning with dashes was not redacted",
    )

    assignment_safe = receipt.safe_command(
        ["/usr/bin/env", "API_TOKEN=synthetic-value", "SIGNING_KEY=synthetic-value", "PUBLIC_MODE=test"]
    )
    require(
        assignment_safe == ["env", "API_TOKEN=[REDACTED]", "SIGNING_KEY=[REDACTED]", "PUBLIC_MODE=test"],
        "environment assignment redaction or executable basename normalization failed",
    )

    script = ROOT / "scripts" / "nextjs_postgres_real_worker_human_review_smoke.py"
    private_root = "/Users/example/customer-private"
    runtime_command = [
        "/private/runtime/python/bin/python3.11",
        "-B",
        str(script),
        "--adapter",
        "hermes",
        "--postgres-dsn",
        "synthetic-dsn",
        "--hermes-gateway-url=https://example.invalid/private",
        "--openclaw-bin",
        "/opt/private/openclaw",
        "--config",
        f"{private_root}/config.json",
        "-c",
        f'print("{private_root}/embedded.json")',
    ]
    runtime_safe = receipt.safe_command(runtime_command)
    require(runtime_safe[0] == "python3.11", "interpreter path was not reduced to its basename")
    require(
        runtime_safe[2] == "scripts/nextjs_postgres_real_worker_human_review_smoke.py",
        "known script path was not normalized relative to the repository",
    )
    require(
        all(fragment not in json.dumps(runtime_safe) for fragment in ("/Users/", "/private/", "/opt/private")),
        "an absolute private path survived command normalization",
    )
    require(readiness.external_runtime_command_valid(runtime_safe), "safe external Runtime command shape was rejected")

    unsafe_shapes = [
        ["/private/runtime/python3", "scripts/nextjs_postgres_real_worker_human_review_smoke.py"],
        ["python3", str(script)],
        ["python3", "scripts/nextjs_postgres_real_worker_human_review_smoke.py", "--postgres-dsn=synthetic-dsn"],
        ["python3", "scripts/nextjs_postgres_real_worker_human_review_smoke.py", "--postgres-dsn", "synthetic-dsn"],
        ["python3", "scripts/nextjs_postgres_real_worker_human_review_smoke.py", f"{private_root}/input.json"],
    ]
    require(
        all(not readiness.external_runtime_command_valid(command) for command in unsafe_shapes),
        "unsafe external Runtime command shape was accepted",
    )
    windows_safe = receipt.safe_command([r"C:\private\python\python.exe", str(script)])
    require(windows_safe[0] == "python.exe", "Windows interpreter path was not reduced to its basename")
    return 5


def run_receipt_command(args: list[str]) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "commercial_ci_receipt.py"), "command", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {}
    return proc.returncode, payload


def verify_source_root_binding(receipt: ModuleType) -> int:
    subject_sha = "1" * 40
    explicit_builder_sha = receipt.git_head(ROOT)
    require(bool(explicit_builder_sha), "trusted checkout HEAD is unavailable")
    require(receipt.exact_sha("A" * 40) == "a" * 40, "uppercase full SHA was not normalized")
    require(
        all(not receipt.exact_sha(value) for value in ("a" * 39, "a" * 41, "g" * 40, f" {'a' * 40}")),
        "non-exact subject SHA was accepted",
    )
    with tempfile.TemporaryDirectory(prefix="agentops-ci-source-root-") as tmp:
        temp_root = Path(tmp)
        source_root = temp_root / "source"
        scripts = source_root / "scripts"
        scripts.mkdir(parents=True)
        dependency_bytes = b"[build-system]\nrequires = []\n"
        (source_root / "pyproject.toml").write_bytes(dependency_bytes)
        probe = scripts / "probe.py"
        probe.write_text(
            "import json\n"
            "from pathlib import Path\n"
            "root = Path(__file__).resolve().parents[1]\n"
            "print(json.dumps({\n"
            "    'ok': Path.cwd() == root and Path('pyproject.toml').is_file(),\n"
            "    'contract': 'source_root_binding_fixture_v1',\n"
            "}))\n",
            encoding="utf-8",
        )

        output = temp_root / "explicit.json"
        code, payload = run_receipt_command([
            "--gate-id",
            "gate_source_root_test",
            "--command-id",
            "explicit_binding",
            "--expected-contract",
            "source_root_binding_fixture_v1",
            "--subject-sha",
            subject_sha,
            "--builder-sha",
            explicit_builder_sha,
            "--source-root",
            str(source_root),
            "--output",
            str(output),
            "--",
            sys.executable,
            str(probe),
        ])
        serialized = json.dumps(payload, sort_keys=True)
        require(code == 0 and payload.get("evidence_complete") is True, "explicit source-root receipt failed")
        require(payload.get("subject_sha") == subject_sha, "explicit subject SHA was not preserved")
        require(payload.get("builder_sha") == explicit_builder_sha, "explicit builder SHA was not preserved")
        require(payload.get("command", [None, None])[1] == "scripts/probe.py", "source-root script was not normalized")
        require(
            (payload.get("dependency_inputs") or {}).get("lockfile_sha256") == {
                "pyproject.toml": hashlib.sha256(dependency_bytes).hexdigest()
            },
            "dependency inputs were not bound to source-root",
        )
        require(str(source_root) not in serialized and str(temp_root) not in serialized, "source-root leaked into receipt")
        trusted_harness_safe = receipt.safe_command(
            [sys.executable, str(ROOT / "scripts" / "nextjs_postgres_real_worker_human_review_smoke.py")],
            source_root,
        )
        require(
            trusted_harness_safe[1] == "scripts/nextjs_postgres_real_worker_human_review_smoke.py",
            "trusted harness script was not normalized while executing against source-root",
        )

        default_builder_output = temp_root / "default-builder.json"
        code, default_builder = run_receipt_command([
            "--gate-id",
            "gate_source_root_test",
            "--command-id",
            "default_builder",
            "--expected-contract",
            "source_root_binding_fixture_v1",
            "--subject-sha",
            subject_sha,
            "--source-root",
            str(source_root),
            "--output",
            str(default_builder_output),
            "--",
            sys.executable,
            str(probe),
        ])
        require(code == 0, "default builder receipt failed")
        require(default_builder.get("builder_sha") == receipt.git_head(ROOT), "builder did not default to trusted checkout HEAD")

        blocked_marker = source_root / "must-not-run"
        invalid_cases = (
            ("invalid_subject", ["--subject-sha", "abc"], "subject_sha_invalid"),
            ("invalid_builder", ["--subject-sha", subject_sha, "--builder-sha", "not-a-sha"], "builder_sha_invalid"),
            ("mismatched_builder", ["--subject-sha", subject_sha, "--builder-sha", "2" * 40], "builder_sha_mismatch"),
        )
        for command_id, sha_args, expected_failure in invalid_cases:
            invalid_output = temp_root / f"{command_id}.json"
            code, invalid = run_receipt_command([
                "--gate-id",
                "gate_source_root_test",
                "--command-id",
                command_id,
                *sha_args,
                "--source-root",
                str(source_root),
                "--output",
                str(invalid_output),
                "--",
                sys.executable,
                "-c",
                "from pathlib import Path; Path('must-not-run').write_text('blocked')",
            ])
            require(code == 1 and expected_failure in (invalid.get("failures") or []), f"{command_id} was accepted")
            require(not blocked_marker.exists(), f"{command_id} executed despite invalid context")
            require(str(source_root) not in json.dumps(invalid, sort_keys=True), f"{command_id} leaked source-root")

        missing_root = temp_root / "missing-source-root"
        missing_root_output = temp_root / "missing-root.json"
        code, invalid_root = run_receipt_command([
            "--gate-id",
            "gate_source_root_test",
            "--command-id",
            "invalid_source_root",
            "--subject-sha",
            subject_sha,
            "--source-root",
            str(missing_root),
            "--output",
            str(missing_root_output),
            "--",
            sys.executable,
            "-c",
            "print('must not run')",
        ])
        require(code == 1 and "source_root_invalid" in (invalid_root.get("failures") or []), "invalid source-root was accepted")
        require(str(missing_root) not in json.dumps(invalid_root, sort_keys=True), "invalid source-root leaked into receipt")

        parser = receipt.build_parser()
        legacy = parser.parse_args([
            "command",
            "--gate-id",
            "legacy",
            "--command-id",
            "legacy",
            "--output",
            str(temp_root / "legacy.json"),
            "--",
            sys.executable,
            "-c",
            "print('{}')",
        ])
        require(
            legacy.subject_sha == "" and legacy.builder_sha == "" and legacy.source_root == "",
            "legacy command defaults changed",
        )
    return 7


def verify_external_receipt_builder_binding(receipt: ModuleType, readiness: ModuleType) -> int:
    subject_sha = "1" * 40
    builder_sha = "2" * 40
    repository = "example/agentops"
    workflow = "commercial-real-runtime-acceptance"
    predicate_type = "https://example.invalid/attestation/v1"
    claims = receipt.real_runtime_security_claims(valid_runtime_payload())
    command = [
        "python3",
        "scripts/nextjs_postgres_real_worker_human_review_smoke.py",
        "--adapter",
        "hermes",
        "--adapter",
        "openclaw",
        "--postgres-dsn",
        "[REDACTED]",
    ]
    generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
    run_started_at = generated_at - dt.timedelta(minutes=1)
    run_updated_at = generated_at + dt.timedelta(minutes=1)
    payload = {
        "contract_id": "commercial_ci_command_receipt_v1",
        "generated_at": generated_at.isoformat().replace("+00:00", "Z"),
        "subject_sha": subject_sha,
        "builder_sha": builder_sha,
        "github_run": {
            "run_id": "12345",
            "run_attempt": "1",
            "workflow": workflow,
            "repository": repository,
            "ref": "refs/heads/main",
        },
        "gate_id": "gate_runtime",
        "command_id": "trusted_runtime",
        "command": command,
        "exit_code": 0,
        "payload_ok": True,
        "skipped_evidence": False,
        "expected_contracts": ["nextjs_postgres_real_worker_human_review_v1"],
        "missing_contracts": [],
        "payload_diagnostics": {"failure_count": 0, "failure_hashes": [], "error_codes": []},
        "runtime_security_claims": claims,
        "stdout_sha256": "c" * 64,
        "stderr_sha256": "d" * 64,
        "dependency_inputs": {"inputs_sha256": "e" * 64},
        "evidence_complete": True,
        "failures": [],
        "raw_output_stored": False,
        "credentials_stored": False,
    }
    requirement = {
        "gate_id": "gate_runtime",
        "command_id": "trusted_runtime",
        "repository": repository,
        "workflow": workflow,
        "signer_workflow": "example/agentops/.github/workflows/commercial-real-runtime-acceptance.yml",
        "required_adapters": ["hermes", "openclaw"],
        "allowed_refs": ["refs/heads/main"],
        "expected_contract": "nextjs_postgres_real_worker_human_review_v1",
        "predicate_type": predicate_type,
        "max_age_hours": 24,
    }
    calls: list[list[str]] = []
    original_paths: set[str] = set()
    expected_receipt_sha256 = ""
    statement_digest_override = ""

    def fake_run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        calls.append(args)
        if args[:3] == ["gh", "attestation", "verify"]:
            receipt_snapshot = Path(args[3])
            attestation_snapshot = Path(args[args.index("--bundle") + 1])
            require(
                str(receipt_snapshot) not in original_paths
                and str(attestation_snapshot) not in original_paths,
                "gh verified original evidence path instead of owner-only snapshot",
            )
            require(
                receipt_snapshot.stat().st_mode & 0o077 == 0
                and attestation_snapshot.stat().st_mode & 0o077 == 0
                and receipt_snapshot.parent.stat().st_mode & 0o077 == 0,
                "attestation snapshot permissions are not owner-only",
            )
            stdout = json.dumps([
                {
                    "verificationResult": {
                        "statement": {
                            "predicateType": predicate_type,
                            "subject": [
                                {
                                    "name": "receipt.json",
                                    "digest": {
                                        "sha256": statement_digest_override or expected_receipt_sha256
                                    },
                                }
                            ],
                        }
                    }
                }
            ])
            return subprocess.CompletedProcess(args, 0, stdout, "")
        if args[:2] == ["gh", "api"]:
            stdout = json.dumps({
                "status": "completed",
                "conclusion": "success",
                "head_sha": builder_sha,
                "run_attempt": 1,
                "event": "workflow_dispatch",
                "head_branch": "main",
                "name": workflow,
                "run_started_at": run_started_at.isoformat().replace("+00:00", "Z"),
                "updated_at": run_updated_at.isoformat().replace("+00:00", "Z"),
                "path": ".github/workflows/commercial-real-runtime-acceptance.yml@refs/heads/main",
                "head_repository": {"full_name": repository},
            })
            return subprocess.CompletedProcess(args, 0, stdout, "")
        raise AssertionError("unexpected external verification command")

    with tempfile.TemporaryDirectory(prefix="agentops-external-receipt-") as tmp:
        tmp_path = Path(tmp)
        receipt_path = tmp_path / "receipt.json"
        attestation_path = tmp_path / "attestation.json"
        receipt_bytes = json.dumps(payload).encode("utf-8")
        receipt_path.write_bytes(receipt_bytes)
        attestation_path.write_text("{}", encoding="utf-8")
        original_paths.update({str(receipt_path), str(attestation_path)})
        expected_receipt_sha256 = hashlib.sha256(receipt_bytes).hexdigest()
        with mock.patch.object(readiness.subprocess, "run", side_effect=fake_run):
            result = readiness.validate_external_runtime_receipt(
                str(receipt_path),
                str(attestation_path),
                subject_sha,
                True,
                requirement,
            )
        require(result.get("valid") is True, "different subject and trusted builder SHAs were not accepted")
        attestation_command = next(args for args in calls if args[:3] == ["gh", "attestation", "verify"])
        require(
            attestation_command[attestation_command.index("--signer-digest") + 1] == builder_sha
            and attestation_command[attestation_command.index("--source-digest") + 1] == builder_sha
            and attestation_command[attestation_command.index("--source-ref") + 1] == "refs/heads/main",
            "attestation provenance was not bound to builder SHA",
        )

        invalid_payload = dict(payload)
        invalid_payload["builder_sha"] = "false"
        receipt_path.write_text(json.dumps(invalid_payload), encoding="utf-8")
        calls.clear()
        with mock.patch.object(readiness.subprocess, "run", side_effect=fake_run):
            invalid = readiness.validate_external_runtime_receipt(
                str(receipt_path),
                str(attestation_path),
                subject_sha,
                True,
                requirement,
            )
        require(
            invalid.get("valid") is False and "builder_sha" in (invalid.get("failures") or []),
            "malformed external builder SHA was accepted",
        )

        receipt_path.write_bytes(receipt_bytes)
        statement_digest_override = "f" * 64
        calls.clear()
        with mock.patch.object(readiness.subprocess, "run", side_effect=fake_run):
            digest_mismatch = readiness.validate_external_runtime_receipt(
                str(receipt_path),
                str(attestation_path),
                subject_sha,
                True,
                requirement,
            )
        require(
            digest_mismatch.get("valid") is False
            and "attestation_verification_failed" in (digest_mismatch.get("failures") or []),
            "attestation statement with a different receipt digest was accepted",
        )

        statement_digest_override = ""
        run_started_at = generated_at - dt.timedelta(hours=2)
        run_updated_at = generated_at - dt.timedelta(hours=1)
        calls.clear()
        with mock.patch.object(readiness.subprocess, "run", side_effect=fake_run):
            stale_run_time = readiness.validate_external_runtime_receipt(
                str(receipt_path),
                str(attestation_path),
                subject_sha,
                True,
                requirement,
            )
        require(
            stale_run_time.get("valid") is False
            and "github_run_time_binding_failed" in (stale_run_time.get("failures") or []),
            "receipt generated outside the GitHub run interval was accepted",
        )

        run_started_at = generated_at - dt.timedelta(minutes=1)
        run_updated_at = generated_at + dt.timedelta(minutes=1)
        receipt_link = tmp_path / "receipt-link.json"
        receipt_link.symlink_to(receipt_path)
        calls.clear()
        with mock.patch.object(readiness.subprocess, "run", side_effect=fake_run):
            symlink_receipt = readiness.validate_external_runtime_receipt(
                str(receipt_link),
                str(attestation_path),
                subject_sha,
                True,
                requirement,
            )
        require(
            "receipt_not_regular" in (symlink_receipt.get("failures") or []) and not calls,
            "symlink receipt was accepted or triggered gh",
        )

        attestation_link = tmp_path / "attestation-link.json"
        attestation_link.symlink_to(attestation_path)
        calls.clear()
        with mock.patch.object(readiness.subprocess, "run", side_effect=fake_run):
            symlink_attestation = readiness.validate_external_runtime_receipt(
                str(receipt_path),
                str(attestation_link),
                subject_sha,
                True,
                requirement,
            )
        require(
            "attestation_bundle_not_regular" in (symlink_attestation.get("failures") or [])
            and not calls,
            "symlink attestation was accepted or triggered gh",
        )
    return 6


def main() -> int:
    receipt = load_script_module("commercial_ci_receipt", ROOT / "scripts" / "commercial_ci_receipt.py")
    readiness = load_script_module(
        "commercial_migration_readiness",
        ROOT / "scripts" / "commercial_migration_readiness.py",
    )
    runtime_claim_case_count = verify_runtime_claim_fail_closed(receipt, readiness)
    command_redaction_case_count = verify_command_redaction(receipt, readiness)
    source_root_binding_case_count = verify_source_root_binding(receipt)
    external_receipt_builder_case_count = verify_external_receipt_builder_binding(receipt, readiness)

    text = WORKFLOW.read_text(encoding="utf-8")
    real_runtime_text = REAL_RUNTIME_WORKFLOW.read_text(encoding="utf-8")
    action_refs = re.findall(r"uses:\s+(actions/[a-z-]+)@([^\s#]+)", text + "\n" + real_runtime_text)
    require(action_refs, "commercial workflow has no first-party action references")
    for action, ref in action_refs:
        require(action in EXPECTED_ACTION_PINS, f"unexpected first-party action: {action}")
        require(ref == EXPECTED_ACTION_PINS[action], f"movable or unexpected action ref: {action}@{ref}")
        require(bool(re.fullmatch(r"[0-9a-f]{40}", ref)), f"action is not commit pinned: {action}")

    require("ubuntu-latest" not in text, "commercial workflow runner is movable")
    require(text.count("runs-on: ubuntu-24.04") == 5, "commercial workflow runner coverage changed")
    require('python-version: "3.11.9"' in text, "Python patch version is not pinned")
    require('node-version: "20.19.4"' in text, "Node patch version is not pinned")
    require("@playwright/cli@0.1.17" in text, "Playwright CLI version is not pinned")
    require("--package @playwright/cli playwright-cli" not in text, "movable Playwright CLI package remains")
    require(
        bool(re.search(r'AGENTOPS_POSTGRES_IMAGE:\s+"postgres:16\.14-alpine3\.23@sha256:[0-9a-f]{64}"', text)),
        "Postgres image is not tag-and-digest pinned",
    )
    require(
        "runs-on: [self-hosted, agentops-real-runtime]" in real_runtime_text,
        "real Runtime workflow lost its dedicated self-hosted runner label",
    )
    require(
        "environment: commercial-real-runtime" in real_runtime_text,
        "real Runtime workflow lost its protected environment boundary",
    )
    require(
        "persist-credentials: false" in real_runtime_text,
        "real Runtime checkout persists repository credentials",
    )
    require(
        "npm --prefix candidate/ui/next-app ci --ignore-scripts" in real_runtime_text,
        "real Runtime dependency install permits lifecycle scripts",
    )
    require(
        "github.ref == 'refs/heads/main'" in real_runtime_text
        and "Checkout trusted default-branch harness" in real_runtime_text
        and "Checkout candidate source" in real_runtime_text,
        "real Runtime workflow lost its trusted-default-branch harness boundary",
    )
    require(
        "--subject-sha \"$EXPECTED_SHA\"" in real_runtime_text
        and "--builder-sha \"$GITHUB_SHA\"" in real_runtime_text
        and '--source-root "$GITHUB_WORKSPACE/candidate"' in real_runtime_text,
        "real Runtime workflow lost candidate subject, trusted builder, or source-root binding",
    )
    require(
        "--command-id trusted_main_real_runtime_human_review" in real_runtime_text,
        "real Runtime workflow command id no longer identifies the trusted-main harness",
    )
    require("workflow_dispatch:" in real_runtime_text, "real Runtime workflow lost explicit candidate dispatch")
    require(
        not re.search(r"(?m)^  (?:push|pull_request):", real_runtime_text),
        "real Runtime workflow gained a non-dispatch trigger",
    )
    require("continue-on-error:" not in real_runtime_text, "real Runtime evidence step can continue after failure")

    print(json.dumps({
        "ok": True,
        "contract": CONTRACT,
        "workflows": [
            str(WORKFLOW.relative_to(ROOT)),
            str(REAL_RUNTIME_WORKFLOW.relative_to(ROOT)),
        ],
        "action_pin_count": len(action_refs),
        "unique_action_count": len(set(action for action, _ref in action_refs)),
        "runner": "ubuntu-24.04",
        "python": "3.11.9",
        "node": "20.19.4",
        "playwright_cli": "0.1.17",
        "postgres_tag_and_digest_required": True,
        "real_runtime_protected_environment_required": True,
        "real_runtime_checkout_credentials_persisted": False,
        "real_runtime_npm_lifecycle_scripts_enabled": False,
        "runtime_claim_case_count": runtime_claim_case_count,
        "command_redaction_case_count": command_redaction_case_count,
        "source_root_binding_case_count": source_root_binding_case_count,
        "external_receipt_builder_case_count": external_receipt_builder_case_count,
    }, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
