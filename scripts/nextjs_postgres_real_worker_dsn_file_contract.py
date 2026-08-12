#!/usr/bin/env python3
"""Behavioral contract for credential-safe real Worker Postgres input."""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts" / "nextjs_postgres_real_worker_human_review_smoke.py"
FIXTURE_DSN = "postgresql://acceptance:fixture@127.0.0.1:5432/agentops"


def load_harness():
    spec = importlib.util.spec_from_file_location("real_worker_harness", HARNESS)
    if spec is None or spec.loader is None:
        raise RuntimeError("harness_import_failed")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require_rejected(reader, path: Path, expected: str) -> None:
    try:
        reader(str(path))
    except (OSError, UnicodeError, ValueError) as exc:
        if str(exc) != expected:
            raise AssertionError(f"expected {expected}, received {exc}") from exc
    else:
        raise AssertionError(f"unsafe fixture accepted: {expected}")


def write_fixture(path: Path, contents: bytes, mode: int = 0o600) -> None:
    path.write_bytes(contents)
    path.chmod(mode)


def main() -> int:
    harness = load_harness()
    reader = harness.read_postgres_dsn_file
    with tempfile.TemporaryDirectory(prefix="agentops-dsn-file-contract-") as value:
        root = Path(value)

        valid = root / "valid.dsn"
        write_fixture(valid, f"{FIXTURE_DSN}\n".encode())
        assert reader(str(valid)) == FIXTURE_DSN
        valid.chmod(0o400)
        assert reader(str(valid)) == FIXTURE_DSN
        unchanged_dsn, unchanged_identity = (
            harness._read_postgres_dsn_file_with_identity(str(valid))
        )
        harness.assert_postgres_dsn_file_unchanged(
            str(valid), unchanged_dsn, unchanged_identity
        )
        valid.chmod(0o600)
        require_rejected(
            lambda value: harness.assert_postgres_dsn_file_unchanged(
                value, unchanged_dsn, unchanged_identity
            ),
            valid,
            "postgres_dsn_file_changed_during_acceptance",
        )

        relative = Path("relative.dsn")
        require_rejected(reader, relative, "postgres_dsn_file_absolute_path_required")

        symlink = root / "symlink.dsn"
        symlink.symlink_to(valid)
        require_rejected(reader, symlink, "postgres_dsn_file_regular_file_required")

        public = root / "public.dsn"
        write_fixture(public, FIXTURE_DSN.encode(), 0o644)
        require_rejected(reader, public, "postgres_dsn_file_permissions_invalid")

        insecure_parent = root / "insecure"
        insecure_parent.mkdir(mode=0o777)
        insecure_parent.chmod(0o777)
        insecure = insecure_parent / "postgres.dsn"
        write_fixture(insecure, FIXTURE_DSN.encode())
        require_rejected(
            reader,
            insecure,
            "postgres_dsn_file_parent_security_invalid",
        )

        fifo = root / "fifo.dsn"
        os.mkfifo(fifo, mode=0o600)
        require_rejected(reader, fifo, "postgres_dsn_file_regular_file_required")

        linked = root / "linked.dsn"
        linked_alias = root / "linked-alias.dsn"
        write_fixture(linked, FIXTURE_DSN.encode())
        os.link(linked, linked_alias)
        require_rejected(reader, linked, "postgres_dsn_file_link_count_invalid")

        invalid_cases = {
            "empty.dsn": (b"", "postgres_dsn_file_size_invalid"),
            "multiline.dsn": (
                f"{FIXTURE_DSN}\npostgresql://second@127.0.0.1/db".encode(),
                "postgres_dsn_file_contents_invalid",
            ),
            "nul.dsn": (f"{FIXTURE_DSN}\x00".encode(), "postgres_dsn_file_contents_invalid"),
            "scheme.dsn": (b"https://127.0.0.1/database", "postgres_dsn_file_url_invalid"),
            "host.dsn": (b"postgresql:///database", "postgres_dsn_file_url_invalid"),
            "credentials.dsn": (
                b"postgresql://127.0.0.1/database",
                "postgres_dsn_file_url_invalid",
            ),
            "remote.dsn": (
                b"postgresql://acceptance:fixture@example.invalid/database",
                "postgres_dsn_file_loopback_required",
            ),
            "utf8.dsn": (b"\xff", "'utf-8' codec can't decode byte 0xff in position 0: invalid start byte"),
        }
        for name, (contents, expected) in invalid_cases.items():
            path = root / name
            write_fixture(path, contents)
            require_rejected(reader, path, expected)

        oversized = root / "oversized.dsn"
        write_fixture(oversized, b"x" * (harness.MAX_POSTGRES_DSN_FILE_BYTES + 1))
        require_rejected(reader, oversized, "postgres_dsn_file_size_invalid")

    help_result = subprocess.run(
        [os.environ.get("PYTHON", "python3"), str(HARNESS), "--help"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "--postgres-dsn-file" in help_result.stdout
    assert "--postgres-dsn " not in help_result.stdout

    leader_source = """
import signal
import subprocess
import sys
import time

child = subprocess.Popen([
    sys.executable,
    "-c",
    "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)",
])
print(child.pid, flush=True)
signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
time.sleep(60)
"""
    leader = subprocess.Popen(
        [sys.executable, "-c", leader_source],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
    )
    try:
        assert leader.stdout is not None
        descendant_pid = int(leader.stdout.readline().strip())
        stop_receipt = harness.stop_process(leader, timeout=1)
        assert stop_receipt == {
            "stopped": True,
            "process_group_empty": True,
            "errors": [],
        }
        try:
            os.kill(descendant_pid, 0)
        except ProcessLookupError:
            pass
        else:
            raise AssertionError("descendant_process_survived_group_shutdown")
    finally:
        if leader.poll() is None:
            harness.stop_process(leader, timeout=1)

    print(json.dumps({
        "ok": True,
        "contract": "nextjs_postgres_real_worker_dsn_file_contract_v1",
        "argv_credential_option_omitted": True,
        "absolute_owner_only_regular_file_required": True,
        "single_link_required": True,
        "nofollow_required": True,
        "nonblocking_open_required": True,
        "secure_parent_required": True,
        "stable_identity_required": True,
        "end_to_end_source_stability_required": True,
        "bounded_read_required": True,
        "loopback_required": True,
        "descendant_process_group_shutdown_required": True,
        "postgres_url_required": True,
        "credentials_omitted": True,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
