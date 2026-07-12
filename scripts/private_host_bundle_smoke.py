#!/usr/bin/env python3
"""Build, scan, install, exercise, and uninstall a private-host bundle offline."""
from __future__ import annotations

import hashlib
import http.cookiejar
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
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_private_host_bundle.py"
FORBIDDEN_NAMES = {".git", ".agentops_runtime", "__pycache__", "artifacts", "node_modules", "logs"}
FORBIDDEN_SUFFIXES = {".db", ".sqlite", ".sqlite3", ".log", ".pyc", ".pyo"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    value.update(path.read_bytes())
    return value.hexdigest()


def run(command: list[str], *, env: dict | None = None, cwd: Path | None = None, input_text: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, env=env, input=input_text, capture_output=True, text=True, timeout=120, check=False)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def http_json(opener, method: str, url: str, body: dict | None = None, headers: dict | None = None) -> tuple[int, dict]:
    request = Request(
        url,
        data=None if body is None else json.dumps(body).encode("utf-8"),
        method=method,
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with (opener.open(request, timeout=30) if opener else urlopen(request, timeout=30)) as response:
            raw = response.read().decode("utf-8")
            return response.status, json.loads(raw) if raw else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except ValueError:
            return exc.code, {"error": "non_json_error"}


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
        release_env_probe = run(
            [
                sys.executable,
                "-c",
                (
                    "import json; from agentops_mis_cli.host import host_env; "
                    "value=host_env({'database_path':'/tmp/omitted.db','cookie_secure':False,"
                    "'allowed_origins':[],'workspace_id':'local-demo'},"
                    "{'api_key':'omitted','admin_key':'omitted','owner_setup_code':'omitted'}); "
                    "print(json.dumps({'version':value.get('AGENTOPS_HOST_VERSION'),"
                    "'git_commit':value.get('AGENTOPS_GIT_COMMIT')}))"
                ),
            ],
            env={**env, "PYTHONPATH": str(install_root / "current")},
            cwd=install_root / "current",
        )
        release_env = json.loads(release_env_probe.stdout)
        if (
            release_env_probe.returncode != 0
            or release_env.get("version") != version
            or release_env.get("git_commit") != manifest["git_commit"]
        ):
            fail("packaged Host environment omitted release provenance", release_env_probe)
        help_result = run([str(bin_dir / "agentops"), "host", "--help"], env=env)
        if help_result.returncode != 0 or "Manage the private local AgentOps MIS host" not in help_result.stdout:
            fail("installed agentops host --help failed", help_result)
        for command in ("bootstrap-owner", "configure-cli", "backup", "backup-verify", "restore"):
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
        for plan_spec in (
            "PROJECT_SPEC.md",
            "AGENT_WORKFLOW.md",
            "BASE_INDEX.md",
            "docs/AGENT_WORK_METHOD_BLOCK.md",
        ):
            if not (install_root / "current" / plan_spec).is_file():
                fail(f"installed Agent Plan spec missing: {plan_spec}")
        initialized = run([str(bin_dir / "agentops"), "host", "init", "--port", str(free_port())], env=env)
        if initialized.returncode != 0:
            fail("installed agentops host init failed", initialized)
        doctor = run([str(bin_dir / "agentops"), "host", "doctor"], env=env)
        if doctor.returncode != 0 or not json.loads(doctor.stdout).get("ok"):
            fail("installed agentops host doctor failed", doctor)

        init_payload = json.loads(initialized.stdout)
        config = json.loads((host_data / "config.json").read_text(encoding="utf-8"))
        base_url = f"http://127.0.0.1:{config['port']}"
        started = run([str(bin_dir / "agentops"), "host", "start", "--no-workers"], env=env)
        if started.returncode != 0 or not json.loads(started.stdout).get("ok"):
            fail("installed Host failed to start for Agent Plan verification", started)
        configure_cli = run([str(bin_dir / "agentops"), "host", "configure-cli", "--confirm"], env=env)
        configure_cli_payload = json.loads(configure_cli.stdout or "{}")
        configured_machine_key = str(json.loads((host_data / "secrets.json").read_text(encoding="utf-8")).get("api_key") or "")
        worker_preflight = run([str(bin_dir / "agentops"), "worker", "preflight", "--adapter", "mock"], env=env)
        worker_preflight_payload = json.loads(worker_preflight.stdout or "{}")
        bootstrap_password = "fixture-bundle-smoke-password"
        bootstrap_cli = run(
            [
                str(bin_dir / "agentops"),
                "host",
                "bootstrap-owner",
                "--username",
                "bundle-smoke-owner",
                "--display-name",
                "Bundle Smoke Owner",
                "--password-stdin",
                "--confirm",
            ],
            env=env,
            input_text=bootstrap_password + "\n",
        )
        bootstrap_payload = json.loads(bootstrap_cli.stdout or "{}")
        opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        auth_status, authenticated = http_json(
            opener,
            "POST",
            base_url + "/api/human-auth/login",
            {
                "username": "bundle-smoke-owner",
                "password": bootstrap_password,
            },
            {"Origin": base_url},
        )
        csrf = str(authenticated.get("csrf_token") or "")
        workflow_status, workflow = http_json(
            opener,
            "POST",
            base_url + "/api/workflows/customer-worker-task",
            {
                "adapter": "mock",
                "confirm_run": True,
                "title": "Installed bundle Agent Plan verification",
                "description": "Verify the installed runtime can read its packaged authority specs.",
                "acceptance_criteria": "Mock run writes bounded plan, run, evaluation, artifact, and audit evidence.",
                "priority": "high",
                "risk_level": "low",
            },
            {"Origin": base_url, "X-AgentOps-CSRF": csrf},
        )
        stopped = run([str(bin_dir / "agentops"), "host", "stop"], env=env)
        evidence = workflow.get("evidence") or {}
        if (
            configure_cli.returncode != 0
            or configure_cli_payload.get("machine_credential_configured") is not True
            or configure_cli_payload.get("browser_session_reused") is not False
            or not configured_machine_key
            or configured_machine_key in ((configure_cli.stdout or "") + (configure_cli.stderr or "") + (worker_preflight.stdout or "") + (worker_preflight.stderr or ""))
            or worker_preflight.returncode != 0
            or worker_preflight_payload.get("ok") is not True
            or bootstrap_cli.returncode != 0
            or bootstrap_payload.get("owner_created") is not True
            or bootstrap_password in ((bootstrap_cli.stdout or "") + (bootstrap_cli.stderr or ""))
            or auth_status != 200
            or not csrf
            or workflow_status != 201
            or workflow.get("ok") is not True
            or not workflow.get("run_id")
            or workflow.get("plan_evidence_pass") is not True
            or int(evidence.get("evaluations") or 0) < 1
            or int(evidence.get("artifacts") or 0) < 1
            or stopped.returncode != 0
        ):
            fail(
                "installed Host could not complete Agent Plan verification",
                subprocess.CompletedProcess(
                    args=["installed-host-agent-plan"],
                    returncode=1,
                    stdout=json.dumps({
                        "auth_status": auth_status,
                        "configure_cli_ok": configure_cli.returncode == 0,
                        "worker_preflight_ok": worker_preflight_payload.get("ok"),
                        "bootstrap_cli_ok": bootstrap_cli.returncode == 0,
                        "bootstrap_owner_created": bootstrap_payload.get("owner_created"),
                        "workflow_status": workflow_status,
                        "workflow_ok": workflow.get("ok"),
                        "run_id_present": bool(workflow.get("run_id")),
                        "plan_evidence_pass": workflow.get("plan_evidence_pass"),
                        "evidence": evidence,
                        "host_stopped": stopped.returncode == 0,
                    }, sort_keys=True),
                    stderr="",
                ),
            )

        database = Path(config["database_path"])
        with sqlite3.connect(database) as conn:
            conn.execute("CREATE TABLE product_upgrade_smoke(marker TEXT PRIMARY KEY)")
            conn.execute("INSERT INTO product_upgrade_smoke VALUES('preserved-across-binary-switch')")

        custom_ui = install_root / "versions" / "custom-ui-fixture" / "dist"
        custom_ui.mkdir(parents=True)
        (custom_ui / "index.html").write_text("CUSTOM_UI_FIXTURE\n", encoding="utf-8")
        config["ui_dist"] = str(custom_ui)
        (host_data / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        custom_status = run([str(bin_dir / "agentops"), "host", "status"], env=env)
        custom_status_payload = json.loads(custom_status.stdout)
        if custom_status_payload.get("ui_dist") != str(custom_ui.resolve()) or custom_status_payload.get("ui_dist_managed") is not False:
            fail("custom UI below the versions directory was incorrectly replaced", custom_status)
        config["ui_dist"] = str((install_root / "versions" / version / "ui" / "start-building-app" / "dist").resolve())
        (host_data / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        version_two = "0.0.1-smoke"
        output_two = temp / "out-two"
        ui_two = temp / "ui-two"
        shutil.copytree(ROOT / "ui" / "start-building-app" / "dist", ui_two)
        ui_marker = "AGENTOPS_BUNDLE_SMOKE_UI_V2"
        with (ui_two / "index.html").open("a", encoding="utf-8") as handle:
            handle.write(f"\n<!-- {ui_marker} -->\n")
        built_two = run([
            sys.executable,
            str(BUILDER),
            "--output-dir",
            str(output_two),
            "--ui-dist",
            str(ui_two),
            "--version",
            version_two,
        ])
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
        upgraded_status = run([str(bin_dir / "agentops"), "host", "status"], env=env)
        upgraded_status_payload = json.loads(upgraded_status.stdout)
        expected_upgraded_ui = str((install_root / "versions" / version_two / "ui" / "start-building-app" / "dist").resolve())
        if upgraded_status_payload.get("ui_dist") != expected_upgraded_ui or upgraded_status_payload.get("ui_dist_managed") is not True:
            fail("upgrade continued serving the previous release UI", upgraded_status)
        upgraded_started = run([str(bin_dir / "agentops"), "host", "start", "--no-workers"], env=env)
        try:
            with urlopen(base_url + "/", timeout=10) as response:
                upgraded_html = response.read().decode("utf-8")
        finally:
            upgraded_stopped = run([str(bin_dir / "agentops"), "host", "stop"], env=env)
        if upgraded_started.returncode != 0 or upgraded_stopped.returncode != 0 or ui_marker not in upgraded_html:
            fail("upgraded Host did not serve the current release UI", upgraded_started)
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
        rolled_back_host_status = run([str(bin_dir / "agentops"), "host", "status"], env=env)
        rolled_back_host_payload = json.loads(rolled_back_host_status.stdout)
        expected_rolled_back_ui = str((install_root / "versions" / version / "ui" / "start-building-app" / "dist").resolve())
        if rolled_back_host_payload.get("ui_dist") != expected_rolled_back_ui or rolled_back_host_payload.get("ui_dist_managed") is not True:
            fail("rollback did not restore the matching release UI", rolled_back_host_status)
        rolled_back_started = run([str(bin_dir / "agentops"), "host", "start", "--no-workers"], env=env)
        try:
            with urlopen(base_url + "/", timeout=10) as response:
                rolled_back_html = response.read().decode("utf-8")
        finally:
            rolled_back_stopped = run([str(bin_dir / "agentops"), "host", "stop"], env=env)
        if rolled_back_started.returncode != 0 or rolled_back_stopped.returncode != 0 or ui_marker in rolled_back_html:
            fail("rolled-back Host did not serve the restored release UI", rolled_back_started)
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
            "installed_host_release_env": "passed",
            "installed_backup_restore_commands": "passed",
            "installed_host_init_and_doctor": "passed",
            "installed_agent_plan_specs": "passed",
            "installed_agent_plan_runtime_verification": "passed",
            "installed_owner_bootstrap_cli": "passed",
            "installed_host_cli_configuration": "passed",
            "installed_live_readback_client": "passed",
            "running_host_update_rejected": True,
            "two_version_upgrade_and_rollback": "passed",
            "pre_rollback_backup": "passed",
            "pre_update_backup": "passed",
            "upgrade_data_preserved": True,
            "upgrade_ui_followed_current_release": True,
            "rollback_ui_followed_current_release": True,
            "custom_ui_preserved": True,
            "served_ui_followed_upgrade_and_rollback": True,
            "uninstall_preserved_user_data": True,
            "network_used": False,
        }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
