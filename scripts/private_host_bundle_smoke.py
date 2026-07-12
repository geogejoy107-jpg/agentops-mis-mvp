#!/usr/bin/env python3
"""Build, scan, install, exercise, and uninstall a private-host bundle offline."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_private_host_bundle.py"
FORBIDDEN_NAMES = {".git", ".agentops_runtime", "__pycache__", "artifacts", "node_modules", "logs"}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".pyc", ".pyo"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def run(command: list[str], *, env: dict | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, timeout=120, check=False)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def fail(message: str, process: subprocess.CompletedProcess | None = None) -> None:
    detail = ""
    if process:
        detail = f"\nstdout:\n{process.stdout[-2000:]}\nstderr:\n{process.stderr[-2000:]}"
    raise RuntimeError(message + detail)


def forbidden(path: str) -> bool:
    rel = PurePosixPath(path)
    lower = [part.lower() for part in rel.parts]
    return (
        any(part in FORBIDDEN_NAMES or part.startswith(".env") or "token" in part for part in lower)
        or rel.suffix.lower() in FORBIDDEN_SUFFIXES
        or "sample_export" in rel.name.lower()
    )


def extract_bundle(tar_path: Path, destination: Path) -> Path:
    destination.mkdir()
    with tarfile.open(tar_path, "r:gz") as archive:
        members = archive.getmembers()
        for member in members:
            if member.issym() or member.islnk() or forbidden(member.name):
                fail(f"forbidden archive member: {member.name}")
            target = (destination / member.name).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                fail(f"archive traversal path: {member.name}")
        archive.extractall(destination, filter="data")
    return next(destination.iterdir())


def main() -> int:
    ui = ROOT / "ui" / "start-building-app" / "dist" / "index.html"
    if not ui.is_file():
        fail("production UI dist is required; run npm run build first")

    with tempfile.TemporaryDirectory(prefix="agentops-private-host-smoke-") as temporary:
        temp = Path(temporary)
        output = temp / "out"
        version = "0.0.0-smoke"
        built = run([sys.executable, str(BUILDER), "--output-dir", str(output), "--version", version])
        if built.returncode != 0:
            fail("bundle build failed", built)
        build_result = json.loads(built.stdout)
        tar_path = next(Path(path) for path in build_result["artifacts"] if path.endswith(".tar.gz"))
        zip_path = next(Path(path) for path in build_result["artifacts"] if path.endswith(".zip"))
        checksum_path = Path(build_result["checksums"])
        checksums = json.loads(checksum_path.read_text(encoding="utf-8"))
        for archive_path in (tar_path, zip_path):
            if checksums.get(archive_path.name) != digest(archive_path):
                fail(f"archive checksum mismatch: {archive_path.name}")

        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                if forbidden(info.filename):
                    fail(f"forbidden zip member: {info.filename}")
                target = (temp / "zip-scan" / info.filename).resolve()
                zip_root = (temp / "zip-scan").resolve()
                if zip_root not in target.parents and target != zip_root:
                    fail(f"zip traversal path: {info.filename}")

        bundle = extract_bundle(tar_path, temp / "extract")
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        if manifest["version"] != version or manifest["git_commit"] != subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip():
            fail("manifest version or commit mismatch")
        for record in manifest["files"]:
            path = bundle / record["path"]
            if not path.is_file() or digest(path) != record["sha256"]:
                fail(f"manifest file checksum mismatch: {record['path']}")

        home = temp / "home with $shell ' quote"
        install_root = home / ".local" / "share" / "agentops-mis"
        bin_dir = home / ".local" / "bin"
        host_data = home / ".agentops" / "host"
        host_data.mkdir(parents=True)
        sentinel = host_data / "preserve-me"
        sentinel.write_text("user data", encoding="utf-8")
        env = {
            **os.environ,
            "HOME": str(home),
            "AGENTOPS_INSTALL_ROOT": str(install_root),
            "AGENTOPS_BIN_DIR": str(bin_dir),
            "AGENTOPS_HOST_HOME": str(host_data),
        }
        tampered = temp / "tampered"
        shutil.copytree(bundle, tampered)
        with (tampered / "payload" / "LICENSE").open("a", encoding="utf-8") as handle:
            handle.write("tampered\n")
        rejected = run(["sh", str(tampered / "install.sh")], env=env)
        if rejected.returncode == 0 or install_root.exists():
            fail("installer accepted a payload that did not match its manifest", rejected)

        installed = run(["sh", str(bundle / "install.sh")], env=env)
        if installed.returncode != 0:
            fail("bundle install failed", installed)
        version_status = run(
            [str(bin_dir / "agentops"), "host", "version"],
            env={**env, "PYTHONPATH": str(ROOT)},
            cwd=ROOT,
        )
        version_payload = json.loads(version_status.stdout)
        if (
            version_status.returncode != 0
            or version_payload.get("packaged_install") is not True
            or version_payload.get("version") != version
            or version_payload.get("git_commit") != manifest["git_commit"]
        ):
            fail("installed shim was shadowed by source checkout or PYTHONPATH", version_status)
        help_result = run([str(bin_dir / "agentops"), "host", "--help"], env=env)
        if help_result.returncode != 0 or "Manage the private local AgentOps MIS host" not in help_result.stdout:
            fail("installed agentops host --help failed", help_result)
        for command in ("backup", "backup-verify", "restore"):
            command_help = run([str(bin_dir / "agentops"), "host", command, "--help"], env=env)
            if command_help.returncode != 0:
                fail(f"installed agentops host {command} --help failed", command_help)
        if not (install_root / "current" / "ui" / "start-building-app" / "dist" / "index.html").is_file():
            fail("installed production UI missing")
        if not (install_root / "current" / "scripts" / "v1_5_live_product_readiness_smoke.py").is_file():
            fail("installed real-runtime ledger readback client missing")
        for release_doc in (
            "docs/PRIVATE_HOST_OPERATOR_RUNBOOK.md",
            "docs/RELEASE_PROVENANCE.md",
            "docs/SBOM_MINIMAL.md",
            "docs/THIRD_PARTY_NOTICES.md",
        ):
            if not (install_root / "current" / release_doc).is_file():
                fail(f"installed release evidence missing: {release_doc}")
        initialized = run([str(bin_dir / "agentops"), "host", "init", "--port", str(free_port())], env=env)
        if initialized.returncode != 0:
            fail("installed agentops host init failed", initialized)
        doctor = run([str(bin_dir / "agentops"), "host", "doctor"], env=env)
        if doctor.returncode != 0 or not json.loads(doctor.stdout).get("ok"):
            fail("installed agentops host doctor failed", doctor)

        config = json.loads((host_data / "config.json").read_text(encoding="utf-8"))
        database = Path(config["database_path"])
        with sqlite3.connect(database) as conn:
            conn.execute("CREATE TABLE product_upgrade_smoke(marker TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO product_upgrade_smoke VALUES('preserved-across-binary-switch')")

        version_two = "0.0.1-smoke"
        output_two = temp / "out-two"
        built_two = run([sys.executable, str(BUILDER), "--output-dir", str(output_two), "--version", version_two])
        if built_two.returncode != 0:
            fail("second bundle build failed", built_two)
        build_two_result = json.loads(built_two.stdout)
        tar_two = next(Path(path) for path in build_two_result["artifacts"] if path.endswith(".tar.gz"))
        bundle_two = extract_bundle(tar_two, temp / "extract-two")

        pid_path = host_data / "run" / "host.pid.json"
        pid_path.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
        running_rejected = run(["sh", str(bundle_two / "install.sh")], env=env)
        pid_path.unlink()
        if running_rejected.returncode == 0 or (install_root / "versions" / version_two).exists():
            fail("installer did not reject an update while the managed Host PID was alive", running_rejected)

        upgraded = run(["sh", str(bundle_two / "install.sh")], env=env)
        if upgraded.returncode != 0:
            fail("second bundle install failed", upgraded)
        upgraded_payload = json.loads(upgraded.stdout)
        if upgraded_payload.get("previous_version") != version:
            fail("upgrade did not retain the previous version pointer", upgraded)
        if not Path(str(upgraded_payload.get("pre_update_backup_path") or "")).is_file():
            fail("upgrade did not create a verified pre-update ledger backup", upgraded)
        version_status = run([str(bin_dir / "agentops"), "host", "version"], env=env)
        version_payload = json.loads(version_status.stdout)
        if version_status.returncode != 0 or version_payload.get("version") != version_two or version_payload.get("previous_version") != version:
            fail("installed version provenance is incorrect after upgrade", version_status)
        update_check = run([str(bin_dir / "agentops"), "host", "update", "--check"], env=env)
        if update_check.returncode != 0 or json.loads(update_check.stdout).get("check_only") is not True:
            fail("side-effect-free update check failed", update_check)

        rollback_dry = run([str(bin_dir / "agentops"), "host", "rollback"], env=env)
        if rollback_dry.returncode != 2 or json.loads(rollback_dry.stdout).get("dry_run") is not True:
            fail("binary rollback did not require explicit confirmation", rollback_dry)
        rolled_back = run([str(bin_dir / "agentops"), "host", "rollback", "--confirm-rollback"], env=env)
        if rolled_back.returncode != 0:
            fail("binary rollback failed", rolled_back)
        rollback_payload = json.loads(rolled_back.stdout)
        if rollback_payload.get("to_version") != version or not Path(str(rollback_payload.get("pre_rollback_backup_path") or "")).is_file():
            fail("binary rollback lacked target version or verified pre-rollback backup", rolled_back)
        rolled_back_status = run([str(bin_dir / "agentops"), "host", "version"], env=env)
        rolled_back_payload = json.loads(rolled_back_status.stdout)
        if rolled_back_payload.get("version") != version or rolled_back_payload.get("previous_version") != version_two:
            fail("rollback did not atomically swap current and previous versions", rolled_back_status)
        with sqlite3.connect(database) as conn:
            marker = conn.execute("SELECT marker FROM product_upgrade_smoke").fetchone()
        if not marker or marker[0] != "preserved-across-binary-switch" or not sentinel.is_file():
            fail("upgrade or rollback changed Host product data")

        uninstalled = run(["sh", str(bundle_two / "uninstall.sh")], env=env)
        if uninstalled.returncode != 0:
            fail("bundle uninstall failed", uninstalled)
        if install_root.exists() or (bin_dir / "agentops").exists():
            fail("uninstall left product files behind")
        if not sentinel.is_file():
            fail("uninstall removed user data without explicit purge")

        print(json.dumps({
            "ok": True,
            "operation": "private_host_bundle_smoke",
            "archive_forbidden_scan": "tar_and_zip_passed",
            "manifest_checksums": "passed",
            "installed_sbom_notices_and_runbook": "passed",
            "tampered_payload_rejected": True,
            "installed_host_help": "passed",
            "installed_shim_source_shadowing": "rejected",
            "installed_backup_restore_commands": "passed",
            "installed_host_init_and_doctor": "passed",
            "installed_live_readback_client": "passed",
            "running_host_update_rejected": True,
            "two_version_upgrade_and_rollback": "passed",
            "pre_rollback_backup": "passed",
            "pre_update_backup": "passed",
            "upgrade_data_preserved": True,
            "uninstall_preserved_user_data": True,
            "network_used": False,
        }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
