#!/usr/bin/env python3
"""Exercise the fail-closed stopped-Host log-rotation contract."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentops_mis_cli import host, host_log, runtime_lock  # noqa: E402


MIB = 1024 * 1024
DEFAULT_MAX_BYTES = 8 * MIB
MINIMUM_MAX_BYTES = MIB
DEFAULT_BACKUPS = 5
MINIMUM_BACKUPS = 2
MAXIMUM_BACKUPS = 20
PLAN_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
LOG_MARKER_PREFIX = "fixture-log-content-must-not-print"
PROTECTED_MARKER = "fixture-protected-state-must-not-print"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_private(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(value)
    path.chmod(0o600)


def write_sparse_log(path: Path, marker: str, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    encoded = marker.encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(descriptor, encoded[: max(0, size)])
        os.ftruncate(descriptor, max(size, len(encoded)))
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)


def fingerprint(path: Path) -> tuple:
    metadata = path.lstat()
    common = (
        stat.S_IFMT(metadata.st_mode),
        stat.S_IMODE(metadata.st_mode),
        int(metadata.st_uid),
        int(metadata.st_nlink),
        int(metadata.st_size),
    )
    if stat.S_ISLNK(metadata.st_mode):
        return (*common, "symlink", os.readlink(path))
    if stat.S_ISREG(metadata.st_mode):
        return (*common, "file", sha256(path))
    if stat.S_ISDIR(metadata.st_mode):
        return (*common, "directory")
    return (*common, "other")


def snapshot_directory(path: Path) -> dict:
    if path.is_symlink():
        return {"@root": fingerprint(path)}
    if not path.exists():
        return {"@missing": True}
    result = {"@root": fingerprint(path)}
    for entry in sorted(path.iterdir(), key=lambda item: item.name):
        result[entry.name] = fingerprint(entry)
    return result


def snapshot_protected(fixture: dict) -> dict:
    return {
        label: fingerprint(path) if path.exists() or path.is_symlink() else ("missing",)
        for label, path in fixture["protected"].items()
    }


def run_host(env: dict[str, str], *arguments: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    process = subprocess.run(
        [sys.executable, "-m", "agentops_mis_cli.cli", "host", *arguments],
        cwd=ROOT,
        env=env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    try:
        payload = json.loads(process.stdout)
    except (TypeError, ValueError):
        payload = {}
    return process, payload if isinstance(payload, dict) else {}


def create_fixture(
    root: Path,
    name: str,
    *,
    active_size: int | None = MINIMUM_MAX_BYTES + 1,
    backup_count: int = 0,
    create_logs: bool = True,
) -> dict:
    fixture_root = root / name
    home = fixture_root / "home"
    host_home = home / ".agentops" / "host"
    logs = host_home / "logs"
    data = host_home / "data"
    run = host_home / "run"
    for directory in (host_home, data, run):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        directory.chmod(0o700)

    config = host_home / "config.json"
    secrets = host_home / "secrets.json"
    version = host_home / "version.json"
    database = data / "agentops_mis.db"
    lifecycle_lock = host_home.parent / ".agentops-mis-host-lifecycle.lock"
    host_runtime_lock = run / "host.runtime.lock"
    write_private(config, b'{"initialized_fixture":true}\n')
    write_private(secrets, b'{"private_fixture_only":true}\n')
    write_private(version, (PROTECTED_MARKER + ":version\n").encode("utf-8"))
    write_private(database, (PROTECTED_MARKER + ":database\n").encode("utf-8"))
    write_private(lifecycle_lock, b"")
    write_private(host_runtime_lock, b"")

    markers: list[str] = []
    launchd_log = logs / "launchd.log"
    active = logs / "host.log"
    if create_logs:
        logs.mkdir(mode=0o700)
        logs.chmod(0o700)
        write_private(launchd_log, (PROTECTED_MARKER + ":launchd\n").encode("utf-8"))
        if active_size is not None:
            marker = f"{LOG_MARKER_PREFIX}:active"
            write_sparse_log(active, marker, active_size)
            markers.append(marker)
        for suffix in range(1, backup_count + 1):
            marker = f"{LOG_MARKER_PREFIX}:backup-{suffix}"
            write_sparse_log(logs / f"host.log.{suffix}", marker, 128 + suffix)
            markers.append(marker)

    env = {
        "AGENTOPS_HOST_HOME": str(host_home),
        "HOME": str(home),
        "LANG": "C.UTF-8",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT),
        "TMPDIR": str(fixture_root),
    }
    protected = {
        "config": config,
        "secrets": secrets,
        "version": version,
        "database": database,
        "launchd_log": launchd_log,
        "pid": run / "host.pid.json",
        "runtime_lock": host_runtime_lock,
    }
    return {
        "root": fixture_root,
        "home": host_home,
        "logs": logs,
        "active": active,
        "launchd_log": launchd_log,
        "env": env,
        "markers": markers,
        "protected": protected,
    }


def output_is_safe(output: str, fixture: dict) -> bool:
    forbidden = [
        str(fixture["root"]),
        str(fixture["home"]),
        PROTECTED_MARKER,
        LOG_MARKER_PREFIX,
        *fixture["markers"],
    ]
    return not any(value and value in output for value in forbidden)


def is_rotation_payload(payload: dict, *, ok: bool) -> bool:
    return payload.get("operation") == "host_log_rotate" and payload.get("ok") is ok


def record(failures: list[str], evidence: dict[str, bool], name: str, passed: bool) -> None:
    evidence[name] = bool(passed)
    if not passed:
        failures.append(f"{name} failed")


def expect_cli_rejection(
    fixture: dict,
    failures: list[str],
    evidence: dict[str, bool],
    name: str,
    expected_error: str,
    *arguments: str,
    extra_snapshot=None,
) -> None:
    logs_before = snapshot_directory(fixture["logs"])
    protected_before = snapshot_protected(fixture)
    external_before = extra_snapshot() if extra_snapshot else None
    process, payload = run_host(fixture["env"], "log-rotate", *arguments)
    external_after = extra_snapshot() if extra_snapshot else None
    output = (process.stdout or "") + (process.stderr or "")
    record(
        failures,
        evidence,
        name,
        process.returncode != 0
        and is_rotation_payload(payload, ok=False)
        and payload.get("error") == expected_error
        and snapshot_directory(fixture["logs"]) == logs_before
        and snapshot_protected(fixture) == protected_before
        and external_before == external_after
        and output_is_safe(output, fixture),
    )


def exercise_cli_contract(root: Path, failures: list[str], evidence: dict[str, bool]) -> None:
    parsed = host.build_parser().parse_args(["log-rotate"])
    record(
        failures,
        evidence,
        "cli_route_and_defaults",
        parsed.handler is host.cmd_log_rotate
        and parsed.max_bytes == DEFAULT_MAX_BYTES
        and parsed.backups == DEFAULT_BACKUPS
        and parsed.confirm_rotate is False
        and parsed.plan_hash == ""
        and host_log.HOST_LOG_ROTATE_DEFAULT_MAX_BYTES == DEFAULT_MAX_BYTES
        and host_log.HOST_LOG_ROTATE_MIN_MAX_BYTES == MINIMUM_MAX_BYTES
        and host_log.HOST_LOG_ROTATE_DEFAULT_BACKUPS == DEFAULT_BACKUPS
        and host_log.HOST_LOG_ROTATE_MIN_BACKUPS == MINIMUM_BACKUPS
        and host_log.HOST_LOG_ROTATE_MAX_BACKUPS == MAXIMUM_BACKUPS,
    )

    fixture = create_fixture(root, "cli-contract", active_size=DEFAULT_MAX_BYTES + 1)
    logs_before = snapshot_directory(fixture["logs"])
    protected_before = snapshot_protected(fixture)
    first_process, first = run_host(fixture["env"], "log-rotate")
    second_process, second = run_host(fixture["env"], "log-rotate")
    combined_output = first_process.stdout + first_process.stderr + second_process.stdout + second_process.stderr
    record(
        failures,
        evidence,
        "default_dry_run_is_deterministic_and_zero_write",
        first_process.returncode == 0
        and second_process.returncode == 0
        and is_rotation_payload(first, ok=True)
        and first.get("dry_run") is True
        and first.get("max_bytes") == DEFAULT_MAX_BYTES
        and first.get("backups") == DEFAULT_BACKUPS
        and first.get("rotation_required") is True
        and first.get("host_running") is False
        and PLAN_HASH_PATTERN.fullmatch(str(first.get("plan_hash") or "")) is not None
        and first.get("plan_hash") == second.get("plan_hash")
        and snapshot_directory(fixture["logs"]) == logs_before
        and snapshot_protected(fixture) == protected_before
        and output_is_safe(combined_output, fixture),
    )

    minimum_process, minimum = run_host(
        fixture["env"],
        "log-rotate",
        "--max-bytes",
        str(MINIMUM_MAX_BYTES),
        "--backups",
        str(MINIMUM_BACKUPS),
    )
    maximum_process, maximum = run_host(
        fixture["env"],
        "log-rotate",
        "--max-bytes",
        str(MINIMUM_MAX_BYTES),
        "--backups",
        str(MAXIMUM_BACKUPS),
    )
    record(
        failures,
        evidence,
        "threshold_and_backup_boundaries_are_accepted",
        minimum_process.returncode == 0
        and maximum_process.returncode == 0
        and minimum.get("max_bytes") == MINIMUM_MAX_BYTES
        and minimum.get("backups") == MINIMUM_BACKUPS
        and maximum.get("backups") == MAXIMUM_BACKUPS
        and minimum.get("rotation_required") is True
        and snapshot_directory(fixture["logs"]) == logs_before,
    )
    record(
        failures,
        evidence,
        "plan_hash_binds_rotation_configuration",
        len({first.get("plan_hash"), minimum.get("plan_hash"), maximum.get("plan_hash")}) == 3,
    )

    expect_cli_rejection(
        fixture,
        failures,
        evidence,
        "max_bytes_below_one_mib_fails_closed",
        "host_log_max_bytes_below_minimum",
        "--max-bytes",
        str(MINIMUM_MAX_BYTES - 1),
    )
    expect_cli_rejection(
        fixture,
        failures,
        evidence,
        "backup_count_below_two_fails_closed",
        "host_log_backups_out_of_range",
        "--backups",
        str(MINIMUM_BACKUPS - 1),
    )
    expect_cli_rejection(
        fixture,
        failures,
        evidence,
        "backup_count_above_twenty_fails_closed",
        "host_log_backups_out_of_range",
        "--backups",
        str(MAXIMUM_BACKUPS + 1),
    )
    expect_cli_rejection(
        fixture,
        failures,
        evidence,
        "confirm_without_plan_hash_fails_closed",
        "host_log_plan_hash_required",
        "--confirm-rotate",
    )
    expect_cli_rejection(
        fixture,
        failures,
        evidence,
        "plan_hash_without_confirm_fails_closed",
        "host_log_confirmation_required",
        "--plan-hash",
        str(first.get("plan_hash") or "0" * 64),
    )
    expect_cli_rejection(
        fixture,
        failures,
        evidence,
        "invalid_plan_hash_fails_closed",
        "host_log_plan_hash_invalid",
        "--confirm-rotate",
        "--plan-hash",
        "not-a-plan-hash",
    )
    expect_cli_rejection(
        fixture,
        failures,
        evidence,
        "wrong_plan_hash_fails_closed",
        "host_log_plan_mismatch",
        "--confirm-rotate",
        "--plan-hash",
        "f" * 64,
    )

    old_hash = str(first.get("plan_hash") or "0" * 64)
    with fixture["active"].open("ab") as handle:
        handle.write(b"x")
    expect_cli_rejection(
        fixture,
        failures,
        evidence,
        "stale_inventory_invalidates_plan_hash",
        "host_log_plan_mismatch",
        "--confirm-rotate",
        "--plan-hash",
        old_hash,
    )

    fresh_process, fresh = run_host(fixture["env"], "log-rotate")
    expect_cli_rejection(
        fixture,
        failures,
        evidence,
        "changed_configuration_invalidates_plan_hash",
        "host_log_plan_mismatch",
        "--max-bytes",
        str(MINIMUM_MAX_BYTES),
        "--confirm-rotate",
        "--plan-hash",
        str(fresh.get("plan_hash") or "0" * 64),
    )
    record(
        failures,
        evidence,
        "fresh_plan_after_stale_change_is_available",
        fresh_process.returncode == 0 and PLAN_HASH_PATTERN.fullmatch(str(fresh.get("plan_hash") or "")) is not None,
    )


def exercise_running_and_noop(root: Path, failures: list[str], evidence: dict[str, bool]) -> None:
    running = create_fixture(root, "running", active_size=MINIMUM_MAX_BYTES + 1)
    plan_process, plan = run_host(
        running["env"], "log-rotate", "--max-bytes", str(MINIMUM_MAX_BYTES)
    )
    write_private(running["protected"]["pid"], json.dumps({"pid": os.getpid()}).encode("utf-8"))
    expect_cli_rejection(
        running,
        failures,
        evidence,
        "running_host_confirmation_is_zero_write",
        "host_running",
        "--max-bytes",
        str(MINIMUM_MAX_BYTES),
        "--confirm-rotate",
        "--plan-hash",
        str(plan.get("plan_hash") or "0" * 64),
    )
    record(
        failures,
        evidence,
        "running_host_plan_was_valid",
        plan_process.returncode == 0 and plan.get("rotation_required") is True,
    )

    lock_only_running = create_fixture(root, "runtime-lock-running", active_size=MINIMUM_MAX_BYTES + 1)
    lock_plan_process, lock_plan = run_host(
        lock_only_running["env"], "log-rotate", "--max-bytes", str(MINIMUM_MAX_BYTES)
    )
    held_runtime_lock = runtime_lock.acquire_runtime_lock(lock_only_running["protected"]["runtime_lock"])
    try:
        expect_cli_rejection(
            lock_only_running,
            failures,
            evidence,
            "runtime_lock_blocks_confirmation_without_pid_record",
            "host_running",
            "--max-bytes",
            str(MINIMUM_MAX_BYTES),
            "--confirm-rotate",
            "--plan-hash",
            str(lock_plan.get("plan_hash") or "0" * 64),
        )
    finally:
        runtime_lock.release_runtime_lock(held_runtime_lock)
    if lock_plan_process.returncode != 0:
        failures.append("runtime-lock fixture could not prepare a valid plan")

    invalid_pid = create_fixture(root, "invalid-pid", active_size=MINIMUM_MAX_BYTES + 1)
    invalid_plan_process, invalid_plan = run_host(
        invalid_pid["env"], "log-rotate", "--max-bytes", str(MINIMUM_MAX_BYTES)
    )
    write_private(invalid_pid["protected"]["pid"], b'{"pid":"unverifiable"}\n')
    expect_cli_rejection(
        invalid_pid,
        failures,
        evidence,
        "unverifiable_pid_record_confirmation_is_zero_write",
        "host_pid_record_unverifiable",
        "--max-bytes",
        str(MINIMUM_MAX_BYTES),
        "--confirm-rotate",
        "--plan-hash",
        str(invalid_plan.get("plan_hash") or "0" * 64),
    )
    if invalid_plan_process.returncode != 0:
        failures.append("invalid-pid fixture could not prepare a valid plan")

    below = create_fixture(root, "below-threshold", active_size=MINIMUM_MAX_BYTES)
    before_logs = snapshot_directory(below["logs"])
    before_protected = snapshot_protected(below)
    dry_process, dry = run_host(
        below["env"], "log-rotate", "--max-bytes", str(MINIMUM_MAX_BYTES)
    )
    confirmed_process, confirmed = run_host(
        below["env"],
        "log-rotate",
        "--max-bytes",
        str(MINIMUM_MAX_BYTES),
        "--confirm-rotate",
        "--plan-hash",
        str(dry.get("plan_hash") or "0" * 64),
    )
    record(
        failures,
        evidence,
        "at_threshold_confirm_is_a_zero_write_noop",
        dry_process.returncode == 0
        and confirmed_process.returncode == 0
        and dry.get("rotation_required") is False
        and confirmed.get("dry_run") is False
        and confirmed.get("rotated") is False
        and confirmed.get("written_file_count") == 0
        and confirmed.get("deleted_file_count") == 0
        and snapshot_directory(below["logs"]) == before_logs
        and snapshot_protected(below) == before_protected
        and output_is_safe(dry_process.stdout + confirmed_process.stdout, below),
    )


def exercise_fresh_hosts(root: Path, failures: list[str], evidence: dict[str, bool]) -> None:
    missing_directory = create_fixture(root, "missing-directory", create_logs=False)
    protected_before = snapshot_protected(missing_directory)
    process, payload = run_host(missing_directory["env"], "log-rotate")
    record(
        failures,
        evidence,
        "fresh_host_missing_logs_directory_returns_empty_plan",
        process.returncode == 0
        and is_rotation_payload(payload, ok=True)
        and payload.get("dry_run") is True
        and payload.get("directory_present") is False
        and payload.get("host_log_present") is False
        and payload.get("inventory_count") == 0
        and payload.get("rotation_required") is False
        and not missing_directory["logs"].exists()
        and snapshot_protected(missing_directory) == protected_before
        and output_is_safe(process.stdout + process.stderr, missing_directory),
    )

    missing_active = create_fixture(root, "missing-active", active_size=None)
    logs_before = snapshot_directory(missing_active["logs"])
    protected_before = snapshot_protected(missing_active)
    dry_process, dry = run_host(missing_active["env"], "log-rotate")
    confirmed_process, confirmed = run_host(
        missing_active["env"],
        "log-rotate",
        "--confirm-rotate",
        "--plan-hash",
        str(dry.get("plan_hash") or "0" * 64),
    )
    record(
        failures,
        evidence,
        "missing_active_log_confirm_remains_zero_write",
        dry_process.returncode == 0
        and confirmed_process.returncode == 0
        and dry.get("directory_present") is True
        and dry.get("host_log_present") is False
        and confirmed.get("rotated") is False
        and confirmed.get("written_file_count") == 0
        and not missing_active["active"].exists()
        and snapshot_directory(missing_active["logs"]) == logs_before
        and snapshot_protected(missing_active) == protected_before
        and output_is_safe(dry_process.stdout + confirmed_process.stdout, missing_active),
    )


def exercise_valid_rotation(root: Path, failures: list[str], evidence: dict[str, bool]) -> None:
    fixture = create_fixture(
        root,
        "valid-rotation",
        active_size=MINIMUM_MAX_BYTES + 1,
        backup_count=4,
    )
    protected_before = snapshot_protected(fixture)
    plan_process, plan = run_host(
        fixture["env"],
        "log-rotate",
        "--max-bytes",
        str(MINIMUM_MAX_BYTES),
        "--backups",
        "3",
    )
    process, payload = run_host(
        fixture["env"],
        "log-rotate",
        "--max-bytes",
        str(MINIMUM_MAX_BYTES),
        "--backups",
        "3",
        "--confirm-rotate",
        "--plan-hash",
        str(plan.get("plan_hash") or "0" * 64),
    )
    output = plan_process.stdout + plan_process.stderr + process.stdout + process.stderr
    expected_prefixes = {
        "host.log.1": f"{LOG_MARKER_PREFIX}:active",
        "host.log.2": f"{LOG_MARKER_PREFIX}:backup-1",
        "host.log.3": f"{LOG_MARKER_PREFIX}:backup-2",
    }
    actual_prefixes = {
        name: (fixture["logs"] / name).read_bytes()[:80].decode("utf-8", errors="replace")
        for name in expected_prefixes
        if (fixture["logs"] / name).is_file()
    }
    record(
        failures,
        evidence,
        "confirmed_rotation_orders_and_retires_oldest_logs",
        plan_process.returncode == 0
        and process.returncode == 0
        and is_rotation_payload(payload, ok=True)
        and payload.get("dry_run") is False
        and payload.get("rotated") is True
        and payload.get("confirmation_applied") is True
        and payload.get("deleted_file_count") == 2
        and fixture["active"].stat().st_size == 0
        and set(path.name for path in fixture["logs"].glob("host.log.*")) == set(expected_prefixes)
        and all(actual_prefixes.get(name, "").startswith(marker) for name, marker in expected_prefixes.items())
        and not any(path.name.startswith(".agentops-log-rotate-quarantine-") for path in fixture["logs"].iterdir()),
    )
    rotated_paths = [fixture["active"], *(fixture["logs"] / name for name in expected_prefixes)]
    directory_metadata = fixture["logs"].lstat()
    record(
        failures,
        evidence,
        "rotated_logs_remain_private_owned_regular_single_link_files",
        stat.S_ISDIR(directory_metadata.st_mode)
        and stat.S_IMODE(directory_metadata.st_mode) == 0o700
        and directory_metadata.st_uid == os.getuid()
        and all(
            stat.S_ISREG(path.lstat().st_mode)
            and stat.S_IMODE(path.lstat().st_mode) == 0o600
            and path.lstat().st_uid == os.getuid()
            and path.lstat().st_nlink == 1
            for path in rotated_paths
        ),
    )
    record(
        failures,
        evidence,
        "rotation_preserves_ledger_secrets_config_version_and_launchd_log",
        snapshot_protected(fixture) == protected_before
        and payload.get("authority_ledger_unchanged") is True
        and payload.get("secret_store_unchanged") is True
        and payload.get("launchd_log_content_identity_preserved") is True,
    )
    record(
        failures,
        evidence,
        "rotation_output_omits_content_paths_and_private_values",
        payload.get("content_omitted") is True
        and payload.get("paths_omitted") is True
        and payload.get("token_omitted") is True
        and output_is_safe(output, fixture),
    )


def exercise_invalid_inventory(root: Path, failures: list[str], evidence: dict[str, bool]) -> None:
    unsafe_directory = create_fixture(root, "unsafe-directory")
    unsafe_directory["logs"].chmod(0o755)
    expect_cli_rejection(
        unsafe_directory,
        failures,
        evidence,
        "unsafe_log_directory_permissions_fail_closed",
        "host_log_directory_permissions_unsafe",
    )

    unsafe_file = create_fixture(root, "unsafe-file")
    unsafe_file["active"].chmod(0o644)
    expect_cli_rejection(
        unsafe_file,
        failures,
        evidence,
        "unsafe_log_file_permissions_fail_closed",
        "host_log_inventory_permissions_unsafe",
    )

    unknown = create_fixture(root, "unknown-entry")
    write_private(unknown["logs"] / "host.log.unexpected", b"fixture\n")
    expect_cli_rejection(
        unknown,
        failures,
        evidence,
        "unknown_host_log_entry_fails_closed",
        "host_log_inventory_unknown_entry",
    )

    gap = create_fixture(root, "backup-gap", backup_count=3)
    (gap["logs"] / "host.log.2").unlink()
    expect_cli_rejection(
        gap,
        failures,
        evidence,
        "backup_suffix_gap_fails_closed",
        "host_log_inventory_gap",
    )

    symlink = create_fixture(root, "symlink-entry", backup_count=0)
    external_symlink = symlink["root"] / "external-symlink-target.log"
    write_private(external_symlink, b"fixture external symlink target\n")
    (symlink["logs"] / "host.log.1").symlink_to(external_symlink)
    expect_cli_rejection(
        symlink,
        failures,
        evidence,
        "symlink_log_member_fails_closed",
        "host_log_inventory_symlink",
        extra_snapshot=lambda: fingerprint(external_symlink),
    )

    hardlink = create_fixture(root, "hardlink-entry", backup_count=0)
    external_hardlink = hardlink["root"] / "external-hardlink-target.log"
    write_private(external_hardlink, b"fixture external hardlink target\n")
    os.link(external_hardlink, hardlink["logs"] / "host.log.1")
    expect_cli_rejection(
        hardlink,
        failures,
        evidence,
        "hardlink_log_member_fails_closed",
        "host_log_inventory_hardlink",
        extra_snapshot=lambda: fingerprint(external_hardlink),
    )

    non_regular = create_fixture(root, "non-regular-entry", backup_count=0)
    os.mkfifo(non_regular["logs"] / "host.log.1", mode=0o600)
    expect_cli_rejection(
        non_regular,
        failures,
        evidence,
        "non_regular_log_member_fails_closed",
        "host_log_inventory_not_regular",
    )


def exercise_fault_rollback(root: Path, failures: list[str], evidence: dict[str, bool]) -> None:
    fixture = create_fixture(
        root,
        "pre-exchange-fault-rollback",
        active_size=MINIMUM_MAX_BYTES + 1,
        backup_count=4,
    )
    plan, plan_error = host_log.build_rotation_plan(
        fixture["logs"], max_bytes=MINIMUM_MAX_BYTES, backups=3
    )
    logs_before = snapshot_directory(fixture["logs"])
    protected_before = snapshot_protected(fixture)
    with mock.patch.object(
        host_log,
        "_atomic_exchange",
        side_effect=OSError("injected pre-exchange failure"),
    ):
        payload, status_code = host_log.rotate_logs(
            fixture["logs"],
            max_bytes=MINIMUM_MAX_BYTES,
            backups=3,
            confirm_rotate=True,
            plan_hash=str(plan.get("public", {}).get("plan_hash") or ""),
        )
    record(
        failures,
        evidence,
        "pre_exchange_failure_rolls_back_staging_and_journal",
        plan_error is None
        and status_code == 1
        and payload.get("ok") is False
        and payload.get("error") == "host_log_rotation_failed"
        and payload.get("state_rolled_back") is True
        and payload.get("replan_required") is True
        and snapshot_directory(fixture["logs"]) == logs_before
        and snapshot_protected(fixture) == protected_before
        and not any(path.name.startswith(".agentops-log-rotate-") for path in fixture["home"].iterdir())
        and output_is_safe(json.dumps(payload, sort_keys=True), fixture),
    )

    rollback_cleanup_failure = create_fixture(
        root,
        "rollback-cleanup-failure",
        active_size=MINIMUM_MAX_BYTES + 1,
        backup_count=2,
    )
    rollback_cleanup_plan, rollback_cleanup_plan_error = host_log.build_rotation_plan(
        rollback_cleanup_failure["logs"], max_bytes=MINIMUM_MAX_BYTES, backups=2
    )
    with (
        mock.patch.object(host_log, "_atomic_exchange", side_effect=OSError("injected exchange failure")),
        mock.patch.object(host_log, "_cleanup_stage", side_effect=OSError("injected rollback cleanup failure")),
    ):
        rollback_cleanup_payload, rollback_cleanup_status = host_log.rotate_logs(
            rollback_cleanup_failure["logs"],
            max_bytes=MINIMUM_MAX_BYTES,
            backups=2,
            confirm_rotate=True,
            plan_hash=str(rollback_cleanup_plan.get("public", {}).get("plan_hash") or ""),
        )
    rollback_pending, rollback_pending_status = host_log.rotate_logs(
        rollback_cleanup_failure["logs"], max_bytes=MINIMUM_MAX_BYTES, backups=2
    )
    rollback_recovered, rollback_recovered_status = host_log.rotate_logs(
        rollback_cleanup_failure["logs"],
        max_bytes=MINIMUM_MAX_BYTES,
        backups=2,
        confirm_rotate=True,
    )
    record(
        failures,
        evidence,
        "failed_pre_exchange_cleanup_retains_recoverable_journal",
        rollback_cleanup_plan_error is None
        and rollback_cleanup_status == 1
        and rollback_cleanup_payload.get("state_rolled_back") is False
        and rollback_cleanup_payload.get("recovery_required") is True
        and rollback_pending_status == 1
        and rollback_pending.get("error") == "host_log_recovery_required"
        and rollback_recovered_status == 2
        and rollback_recovered.get("recovery_completed") is True
        and rollback_recovered.get("recovery_state") == "rolled_back"
        and host_log.start_gate(rollback_cleanup_failure["logs"]).get("ok") is True
        and not any(
            path.name.startswith(".agentops-log-rotate-")
            for path in rollback_cleanup_failure["home"].iterdir()
        ),
    )

    interrupted_before = create_fixture(
        root,
        "interrupted-before-exchange",
        active_size=MINIMUM_MAX_BYTES + 1,
        backup_count=2,
    )
    interrupted_before_plan, interrupted_before_error = host_log.build_rotation_plan(
        interrupted_before["logs"], max_bytes=MINIMUM_MAX_BYTES, backups=2
    )
    interrupted_before_logs = snapshot_directory(interrupted_before["logs"])
    interrupted_before_protected = snapshot_protected(interrupted_before)
    interrupted_before_raised = False
    try:
        with mock.patch.object(host_log, "_atomic_exchange", side_effect=KeyboardInterrupt):
            host_log.rotate_logs(
                interrupted_before["logs"],
                max_bytes=MINIMUM_MAX_BYTES,
                backups=2,
                confirm_rotate=True,
                plan_hash=str(interrupted_before_plan.get("public", {}).get("plan_hash") or ""),
            )
    except KeyboardInterrupt:
        interrupted_before_raised = True
    pending_before, pending_before_status = host_log.rotate_logs(
        interrupted_before["logs"], max_bytes=MINIMUM_MAX_BYTES, backups=2
    )
    with mock.patch.object(host, "emit") as blocked_start_emit:
        blocked_start = host._host_log_start_preflight({"logs": interrupted_before["logs"]})
    launchd_before_retry = interrupted_before["launchd_log"].lstat()
    with interrupted_before["launchd_log"].open("ab") as launchd_handle:
        launchd_handle.write(b"launchd retry during pending recovery\n")
        launchd_handle.flush()
        os.fsync(launchd_handle.fileno())
    launchd_after_retry = interrupted_before["launchd_log"].lstat()
    launchd_retry_digest = sha256(interrupted_before["launchd_log"])
    recovered_before, recovered_before_status = host_log.rotate_logs(
        interrupted_before["logs"],
        max_bytes=MINIMUM_MAX_BYTES,
        backups=2,
        confirm_rotate=True,
        plan_hash=str(interrupted_before_plan.get("public", {}).get("plan_hash") or ""),
    )
    launchd_after_recovery = interrupted_before["launchd_log"].lstat()
    interrupted_before_logs["launchd.log"] = fingerprint(interrupted_before["launchd_log"])
    interrupted_before_protected["launchd_log"] = fingerprint(interrupted_before["launchd_log"])
    record(
        failures,
        evidence,
        "pre_exchange_process_interruption_recovers_original_state",
        interrupted_before_error is None
        and interrupted_before_raised
        and pending_before_status == 1
        and pending_before.get("error") == "host_log_recovery_required"
        and blocked_start is False
        and blocked_start_emit.call_args.args[0].get("error") == "host_log_recovery_required"
        and recovered_before_status == 2
        and recovered_before.get("recovery_completed") is True
        and recovered_before.get("recovery_state") == "rolled_back"
        and snapshot_directory(interrupted_before["logs"]) == interrupted_before_logs
        and snapshot_protected(interrupted_before) == interrupted_before_protected
        and not any(path.name.startswith(".agentops-log-rotate-") for path in interrupted_before["home"].iterdir()),
    )
    record(
        failures,
        evidence,
        "launchd_retry_append_survives_pending_rotation_recovery",
        (launchd_before_retry.st_dev, launchd_before_retry.st_ino)
        == (launchd_after_retry.st_dev, launchd_after_retry.st_ino)
        == (launchd_after_recovery.st_dev, launchd_after_recovery.st_ino)
        and launchd_after_recovery.st_nlink == 1
        and launchd_after_recovery.st_size == launchd_after_retry.st_size
        and sha256(interrupted_before["launchd_log"]) == launchd_retry_digest,
    )

    interrupted_after = create_fixture(
        root,
        "interrupted-after-exchange",
        active_size=MINIMUM_MAX_BYTES + 1,
        backup_count=2,
    )
    interrupted_after_plan, interrupted_after_error = host_log.build_rotation_plan(
        interrupted_after["logs"], max_bytes=MINIMUM_MAX_BYTES, backups=2
    )
    interrupted_after_protected = snapshot_protected(interrupted_after)
    interrupted_after_raised = False
    try:
        with mock.patch.object(host_log, "_cleanup_stage", side_effect=KeyboardInterrupt):
            host_log.rotate_logs(
                interrupted_after["logs"],
                max_bytes=MINIMUM_MAX_BYTES,
                backups=2,
                confirm_rotate=True,
                plan_hash=str(interrupted_after_plan.get("public", {}).get("plan_hash") or ""),
            )
    except KeyboardInterrupt:
        interrupted_after_raised = True
    pending_after, pending_after_status = host_log.rotate_logs(
        interrupted_after["logs"], max_bytes=MINIMUM_MAX_BYTES, backups=2
    )
    recovered_after, recovered_after_status = host_log.rotate_logs(
        interrupted_after["logs"],
        max_bytes=MINIMUM_MAX_BYTES,
        backups=2,
        confirm_rotate=True,
        plan_hash=str(interrupted_after_plan.get("public", {}).get("plan_hash") or ""),
    )
    record(
        failures,
        evidence,
        "post_exchange_process_interruption_recovers_committed_state",
        interrupted_after_error is None
        and interrupted_after_raised
        and pending_after_status == 1
        and pending_after.get("error") == "host_log_recovery_required"
        and recovered_after_status == 2
        and recovered_after.get("recovery_completed") is True
        and recovered_after.get("recovery_state") == "committed"
        and interrupted_after["active"].stat().st_size == 0
        and (interrupted_after["logs"] / "host.log.1").read_bytes()[:80].decode("utf-8").startswith(
            f"{LOG_MARKER_PREFIX}:active"
        )
        and (interrupted_after["logs"] / "host.log.2").read_bytes()[:80].decode("utf-8").startswith(
            f"{LOG_MARKER_PREFIX}:backup-1"
        )
        and snapshot_protected(interrupted_after) == interrupted_after_protected
        and not any(path.name.startswith(".agentops-log-rotate-") for path in interrupted_after["home"].iterdir()),
    )

    interrupted_mid_cleanup = create_fixture(
        root,
        "interrupted-mid-cleanup",
        active_size=MINIMUM_MAX_BYTES + 1,
        backup_count=3,
    )
    mid_cleanup_plan, mid_cleanup_error = host_log.build_rotation_plan(
        interrupted_mid_cleanup["logs"], max_bytes=MINIMUM_MAX_BYTES, backups=2
    )
    mid_cleanup_raised = False

    def interrupt_after_one_cleanup(parent_fd: int, stage_label: str) -> None:
        stage_fd = host_log._open_directory_at(parent_fd, stage_label)
        try:
            snapshot = host_log._snapshot_directory_fd(stage_fd, allow_partial=True)
            first = sorted(snapshot["entries"])[0]
            os.unlink(first, dir_fd=stage_fd)
            os.fsync(stage_fd)
        finally:
            os.close(stage_fd)
        raise KeyboardInterrupt

    try:
        with mock.patch.object(host_log, "_cleanup_stage", side_effect=interrupt_after_one_cleanup):
            host_log.rotate_logs(
                interrupted_mid_cleanup["logs"],
                max_bytes=MINIMUM_MAX_BYTES,
                backups=2,
                confirm_rotate=True,
                plan_hash=str(mid_cleanup_plan.get("public", {}).get("plan_hash") or ""),
            )
    except KeyboardInterrupt:
        mid_cleanup_raised = True
    mid_cleanup_pending, mid_cleanup_pending_status = host_log.rotate_logs(
        interrupted_mid_cleanup["logs"], max_bytes=MINIMUM_MAX_BYTES, backups=2
    )
    mid_cleanup_recovered, mid_cleanup_recovered_status = host_log.rotate_logs(
        interrupted_mid_cleanup["logs"],
        max_bytes=MINIMUM_MAX_BYTES,
        backups=2,
        confirm_rotate=True,
    )
    record(
        failures,
        evidence,
        "post_exchange_mid_cleanup_interruption_recovers_committed_state",
        mid_cleanup_error is None
        and mid_cleanup_raised
        and mid_cleanup_pending_status == 1
        and mid_cleanup_pending.get("error") == "host_log_recovery_required"
        and mid_cleanup_recovered_status == 2
        and mid_cleanup_recovered.get("recovery_completed") is True
        and mid_cleanup_recovered.get("recovery_state") == "committed"
        and interrupted_mid_cleanup["active"].stat().st_size == 0
        and (interrupted_mid_cleanup["logs"] / "host.log.1").is_file()
        and (interrupted_mid_cleanup["logs"] / "host.log.2").is_file()
        and not any(
            path.name.startswith(".agentops-log-rotate-")
            for path in interrupted_mid_cleanup["home"].iterdir()
        ),
    )
    record(
        failures,
        evidence,
        "host_start_gate_reopens_only_after_rotation_recovery",
        host_log.start_gate(interrupted_before["logs"]).get("ok") is True
        and host_log.start_gate(interrupted_after["logs"]).get("ok") is True
        and host_log.start_gate(interrupted_mid_cleanup["logs"]).get("ok") is True,
    )

    orphan_temporary = create_fixture(
        root,
        "orphan-journal-temporary",
        active_size=MINIMUM_MAX_BYTES + 1,
    )
    orphan_label = ".agentops-log-rotate-journal.json.tmp-0123456789abcdef"
    orphan_path = orphan_temporary["home"] / orphan_label
    write_private(orphan_path, b"interrupted private metadata fixture\n")
    pending_temp, pending_temp_status = host_log.rotate_logs(
        orphan_temporary["logs"], max_bytes=MINIMUM_MAX_BYTES, backups=2
    )
    recovered_temp, recovered_temp_status = host_log.rotate_logs(
        orphan_temporary["logs"],
        max_bytes=MINIMUM_MAX_BYTES,
        backups=2,
        confirm_rotate=True,
    )
    record(
        failures,
        evidence,
        "orphan_journal_temporary_requires_confirmation_and_recovers",
        pending_temp_status == 1
        and pending_temp.get("error") == "host_log_recovery_required"
        and recovered_temp_status == 2
        and recovered_temp.get("recovery_completed") is True
        and recovered_temp.get("recovery_state") == "journal_temporary_removed"
        and not orphan_path.exists()
        and output_is_safe(json.dumps(pending_temp) + json.dumps(recovered_temp), orphan_temporary),
    )

    unsafe_temporary = create_fixture(
        root,
        "unsafe-journal-temporary",
        active_size=MINIMUM_MAX_BYTES + 1,
    )
    unsafe_path = unsafe_temporary["home"] / ".agentops-log-rotate-journal.json.tmp-fedcba9876543210"
    write_private(unsafe_path, b"unsafe private metadata fixture\n")
    unsafe_path.chmod(0o640)
    unsafe_before = fingerprint(unsafe_path)
    unsafe_payload, unsafe_status = host_log.rotate_logs(
        unsafe_temporary["logs"], max_bytes=MINIMUM_MAX_BYTES, backups=2
    )
    record(
        failures,
        evidence,
        "unsafe_journal_temporary_fails_closed_without_cleanup",
        unsafe_status == 1
        and unsafe_payload.get("error") == "host_log_recovery_metadata_unverifiable"
        and unsafe_path.exists()
        and fingerprint(unsafe_path) == unsafe_before
        and output_is_safe(json.dumps(unsafe_payload), unsafe_temporary),
    )


def main() -> int:
    failures: list[str] = []
    evidence: dict[str, bool] = {}
    try:
        with tempfile.TemporaryDirectory(prefix="agentops-host-log-rotation-") as temporary:
            root = Path(temporary)
            exercise_cli_contract(root, failures, evidence)
            exercise_running_and_noop(root, failures, evidence)
            exercise_fresh_hosts(root, failures, evidence)
            exercise_valid_rotation(root, failures, evidence)
            exercise_invalid_inventory(root, failures, evidence)
            exercise_fault_rollback(root, failures, evidence)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        failures.append(f"fixture_exception:{type(exc).__name__}")

    print(
        json.dumps(
            {
                "ok": not failures,
                "operation": "private_host_log_rotation_smoke",
                "checks": len(evidence),
                "evidence": evidence,
                "temporary_host_home": True,
                "real_host_logs_read": False,
                "real_user_database_used": False,
                "network_used": False,
                "raw_log_content_printed": False,
                "credential_values_omitted": True,
                "failures": failures,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
