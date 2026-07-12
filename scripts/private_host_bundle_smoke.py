#!/usr/bin/env python3
"""Build, scan, install, exercise, and uninstall a private-host bundle offline."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import socket
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

        extract = temp / "extract"
        extract.mkdir()
        with tarfile.open(tar_path, "r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                if member.issym() or member.islnk() or forbidden(member.name):
                    fail(f"forbidden archive member: {member.name}")
                target = (extract / member.name).resolve()
                if extract.resolve() not in target.parents and target != extract.resolve():
                    fail(f"archive traversal path: {member.name}")
            archive.extractall(extract, filter="data")

        bundle = next(extract.iterdir())
        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        if manifest["version"] != version or manifest["git_commit"] != subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip():
            fail("manifest version or commit mismatch")
        for record in manifest["files"]:
            path = bundle / record["path"]
            if not path.is_file() or digest(path) != record["sha256"]:
                fail(f"manifest file checksum mismatch: {record['path']}")

        home = temp / "home"
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
        help_result = run([str(bin_dir / "agentops"), "host", "--help"], env=env)
        if help_result.returncode != 0 or "Manage the private local AgentOps MIS host" not in help_result.stdout:
            fail("installed agentops host --help failed", help_result)
        for command in ("backup", "backup-verify", "restore"):
            command_help = run([str(bin_dir / "agentops"), "host", command, "--help"], env=env)
            if command_help.returncode != 0:
                fail(f"installed agentops host {command} --help failed", command_help)
        if not (install_root / "current" / "ui" / "start-building-app" / "dist" / "index.html").is_file():
            fail("installed production UI missing")
        initialized = run([str(bin_dir / "agentops"), "host", "init", "--port", str(free_port())], env=env)
        if initialized.returncode != 0:
            fail("installed agentops host init failed", initialized)
        doctor = run([str(bin_dir / "agentops"), "host", "doctor"], env=env)
        if doctor.returncode != 0 or not json.loads(doctor.stdout).get("ok"):
            fail("installed agentops host doctor failed", doctor)

        uninstalled = run(["sh", str(bundle / "uninstall.sh")], env=env)
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
            "tampered_payload_rejected": True,
            "installed_host_help": "passed",
            "installed_backup_restore_commands": "passed",
            "installed_host_init_and_doctor": "passed",
            "uninstall_preserved_user_data": True,
            "network_used": False,
        }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
