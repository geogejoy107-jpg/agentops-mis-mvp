"""Lifecycle commands for the private, loopback AgentOps MIS host."""
from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STACK = ROOT / "scripts" / "run_local_stack.py"
BACKUP_UTILITY = ROOT / "scripts" / "agentops_local_backup.py"
DEFAULT_UI_DIST = ROOT / "ui" / "start-building-app" / "dist"
MACOS_TAILSCALE_BIN = Path("/Applications/Tailscale.app/Contents/MacOS/Tailscale")


def host_home() -> Path:
    return Path(os.environ.get("AGENTOPS_HOST_HOME") or (Path.home() / ".agentops" / "host")).expanduser().resolve()


def paths() -> dict[str, Path]:
    home = host_home()
    return {
        "home": home,
        "config": home / "config.json",
        "secrets": home / "secrets.json",
        "data": home / "data",
        "database": home / "data" / "agentops_mis.db",
        "backups": home / "backups",
        "logs": home / "logs",
        "log": home / "logs" / "host.log",
        "run": home / "run",
        "pid": home / "run" / "host.pid.json",
    }


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def write_private_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    path.chmod(0o600)


def read_json(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError):
        return {}


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def health(base_url: str) -> dict:
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + "/health", timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {"reachable": response.status == 200, "status": payload.get("status", "unknown")}
    except (OSError, ValueError, urllib.error.URLError):
        return {"reachable": False, "status": "unavailable"}


def tailscale_binary() -> tuple[str | None, str]:
    override = os.environ.get("AGENTOPS_TAILSCALE_BIN", "").strip()
    if override:
        candidate = Path(override).expanduser()
        return (str(candidate.resolve()), "configured") if candidate.is_file() and os.access(candidate, os.X_OK) else (None, "configured_invalid")
    path_binary = shutil.which("tailscale")
    if path_binary:
        return path_binary, "path"
    if MACOS_TAILSCALE_BIN.is_file() and os.access(MACOS_TAILSCALE_BIN, os.X_OK):
        return str(MACOS_TAILSCALE_BIN), "macos_app"
    return None, "unavailable"


def tailscale_state() -> dict:
    binary, source = tailscale_binary()
    result = {
        "installed": bool(binary),
        "installation_source": source,
        "backend_state": "unavailable",
        "dns_name": "",
        "token_omitted": True,
    }
    if not binary:
        return result
    try:
        process = subprocess.run([binary, "status", "--json"], capture_output=True, text=True, timeout=5, check=False)
        payload = json.loads(process.stdout) if process.returncode == 0 else {}
        self_state = payload.get("Self") or {}
        result.update({
            "backend_state": payload.get("BackendState") or "unknown",
            "dns_name": str(self_state.get("DNSName") or "").rstrip("."),
        })
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    return result


def require_initialized() -> tuple[dict, dict]:
    p = paths()
    config = read_json(p["config"])
    secret_values = read_json(p["secrets"])
    if not config or not secret_values:
        raise RuntimeError("Host is not initialized. Run: agentops host init")
    return config, secret_values


def cmd_init(args) -> int:
    p = paths()
    if p["config"].exists() or p["secrets"].exists():
        emit({
            "ok": False,
            "operation": "host_init",
            "error": "already_initialized",
            "message": "Host configuration already exists; initialization never overwrites secrets.",
            "home": str(p["home"]),
            "token_omitted": True,
        })
        return 2
    for key in ("home", "data", "logs", "run"):
        p[key].mkdir(parents=True, exist_ok=True, mode=0o700)
        p[key].chmod(0o700)
    config = {
        "version": 1,
        "host": "127.0.0.1",
        "port": int(args.port),
        "workspace_id": args.workspace_id,
        "database_path": str(p["database"]),
        "ui_dist": str(Path(args.ui_dist).expanduser().resolve() if args.ui_dist else DEFAULT_UI_DIST),
        "deployment_mode": "private_host",
        "cookie_secure": False,
        "allowed_origins": [f"http://127.0.0.1:{int(args.port)}"],
        "network_publication": "disabled",
    }
    owner_setup_code = secrets.token_urlsafe(18)
    secret_values = {
        "api_key": "agthost_" + secrets.token_urlsafe(32),
        "admin_key": "agtadmin_" + secrets.token_urlsafe(32),
        "owner_setup_code": owner_setup_code,
    }
    write_private_json(p["config"], config)
    write_private_json(p["secrets"], secret_values)
    emit({
        "ok": True,
        "operation": "host_init",
        "home": str(p["home"]),
        "config_path": str(p["config"]),
        "secrets_path": str(p["secrets"]),
        "owner_setup_code": owner_setup_code,
        "owner_setup_code_visible_once": True,
        "next_actions": [
            "Build or provide the production UI bundle.",
            "Run: agentops host start --build-ui",
            "Open the local console and create the first Owner.",
        ],
        "token_omitted": True,
    })
    return 0


def host_env(config: dict, secret_values: dict) -> dict:
    env = os.environ.copy()
    env.update({
        "AGENTOPS_DB_PATH": config["database_path"],
        "AGENTOPS_DEPLOYMENT_MODE": "private_host",
        "AGENTOPS_HUMAN_AUTH_REQUIRED": "true",
        "AGENTOPS_COOKIE_SECURE": "true" if config.get("cookie_secure", True) else "false",
        "AGENTOPS_API_KEY": secret_values["api_key"],
        "AGENTOPS_ADMIN_KEY": secret_values["admin_key"],
        "AGENTOPS_OWNER_SETUP_CODE": secret_values["owner_setup_code"],
        "AGENTOPS_ALLOWED_ORIGINS": ",".join(config.get("allowed_origins") or []),
        "AGENTOPS_WORKSPACE_ID": config.get("workspace_id", "local-demo"),
        "AGENTOPS_SKIP_SEED_EXPORTS": "1",
    })
    return env


def stack_command(config: dict, args) -> list[str]:
    command = [
        sys.executable,
        str(STACK),
        "--backend-host",
        config["host"],
        "--backend-port",
        str(config["port"]),
        "--production-ui",
        "--ui-dist",
        config["ui_dist"],
    ]
    if args.build_ui:
        command.append("--build-ui")
        if args.install_ui:
            command.append("--install-ui")
    if args.no_workers:
        command.append("--no-workers")
    else:
        for adapter in args.worker or ["mock"]:
            command.extend(["--worker", adapter])
    if args.confirm_live_workers:
        command.append("--confirm-live-workers")
    return command


def cmd_start(args) -> int:
    config, secret_values = require_initialized()
    p = paths()
    pid_record = read_json(p["pid"])
    pid = int(pid_record.get("pid") or 0)
    if process_alive(pid):
        emit({"ok": False, "operation": "host_start", "error": "already_running", "pid": pid, "token_omitted": True})
        return 2
    command = stack_command(config, args)
    env = host_env(config, secret_values)
    if args.foreground:
        return subprocess.run(command, cwd=ROOT, env=env, check=False).returncode
    p["log"].parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with p["log"].open("a", encoding="utf-8") as log_file:
        p["log"].chmod(0o600)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    write_private_json(p["pid"], {"pid": process.pid, "started_at_epoch": time.time()})
    base_url = f"http://{config['host']}:{config['port']}"
    deadline = time.time() + 25
    readiness = {"reachable": False, "status": "unavailable"}
    while time.time() < deadline and process.poll() is None:
        readiness = health(base_url)
        if readiness["reachable"]:
            break
        time.sleep(0.25)
    if not readiness["reachable"]:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except OSError:
            pass
        p["pid"].unlink(missing_ok=True)
        emit({
            "ok": False,
            "operation": "host_start",
            "error": "startup_failed",
            "log_path": str(p["log"]),
            "token_omitted": True,
        })
        return 1
    emit({
        "ok": True,
        "operation": "host_start",
        "pid": process.pid,
        "local_console_url": base_url + "/workspace",
        "health": readiness,
        "workers": args.worker or ([] if args.no_workers else ["mock"]),
        "live_workers_confirmed": bool(args.confirm_live_workers),
        "network_publication": config.get("network_publication", "disabled"),
        "log_path": str(p["log"]),
        "token_omitted": True,
    })
    return 0


def cmd_status(_args) -> int:
    config, _secret_values = require_initialized()
    p = paths()
    pid_record = read_json(p["pid"])
    pid = int(pid_record.get("pid") or 0)
    running = process_alive(pid)
    base_url = f"http://{config['host']}:{config['port']}"
    readiness = health(base_url) if running else {"reachable": False, "status": "stopped"}
    ts = tailscale_state()
    private_url = f"https://{ts['dns_name']}/workspace" if ts["dns_name"] else ""
    emit({
        "ok": running and readiness["reachable"],
        "operation": "host_status",
        "running": running,
        "pid": pid if running else None,
        "health": readiness,
        "local_console_url": base_url + "/workspace",
        "private_console_url": private_url,
        "tailscale": ts,
        "database_path": config["database_path"],
        "ui_dist": config["ui_dist"],
        "token_omitted": True,
    })
    return 0 if running and readiness["reachable"] else 1


def cmd_stop(_args) -> int:
    p = paths()
    record = read_json(p["pid"])
    pid = int(record.get("pid") or 0)
    if not process_alive(pid):
        p["pid"].unlink(missing_ok=True)
        emit({"ok": True, "operation": "host_stop", "status": "already_stopped", "token_omitted": True})
        return 0
    try:
        os.killpg(pid, signal.SIGTERM)
    except OSError:
        os.kill(pid, signal.SIGTERM)
    deadline = time.time() + 12
    while time.time() < deadline and process_alive(pid):
        time.sleep(0.2)
    if process_alive(pid):
        emit({"ok": False, "operation": "host_stop", "status": "timeout", "pid": pid, "token_omitted": True})
        return 1
    p["pid"].unlink(missing_ok=True)
    emit({"ok": True, "operation": "host_stop", "status": "stopped", "token_omitted": True})
    return 0


def cmd_restart(args) -> int:
    cmd_stop(args)
    return cmd_start(args)


def cmd_doctor(_args) -> int:
    config, _secret_values = require_initialized()
    p = paths()
    gates = [
        {"id": "config_private", "ok": (p["config"].stat().st_mode & 0o077) == 0},
        {"id": "secrets_private", "ok": (p["secrets"].stat().st_mode & 0o077) == 0},
        {"id": "database_parent_private", "ok": (p["data"].stat().st_mode & 0o077) == 0},
        {"id": "production_ui", "ok": (Path(config["ui_dist"]) / "index.html").is_file()},
        {"id": "stack_entrypoint", "ok": STACK.is_file()},
    ]
    ts = tailscale_state()
    emit({
        "ok": all(gate["ok"] for gate in gates),
        "operation": "host_doctor",
        "gates": gates,
        "tailscale": ts,
        "next_actions": [
            "Run agentops host start --build-ui if the production UI gate is false.",
            "Install and sign in to Tailscale on both devices before private publication.",
        ],
        "token_omitted": True,
    })
    return 0 if all(gate["ok"] for gate in gates) else 1


def cmd_logs(_args) -> int:
    p = paths()
    size = p["log"].stat().st_size if p["log"].exists() else 0
    emit({
        "ok": p["log"].exists(),
        "operation": "host_logs",
        "log_path": str(p["log"]),
        "size_bytes": size,
        "content_omitted": True,
        "token_omitted": True,
    })
    return 0 if p["log"].exists() else 1


def run_backup_utility(*arguments: str) -> tuple[dict, int]:
    if not BACKUP_UTILITY.is_file():
        return {"ok": False, "error": "backup_utility_missing"}, 1
    process = subprocess.run(
        [sys.executable, str(BACKUP_UTILITY), *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    try:
        payload = json.loads(process.stdout)
    except ValueError:
        payload = {"ok": False, "error": "backup_utility_invalid_response"}
    payload["utility_output_omitted"] = True
    payload["token_omitted"] = True
    return payload, process.returncode


def cmd_backup(_args) -> int:
    config, _secret_values = require_initialized()
    p = paths()
    p["backups"].mkdir(parents=True, exist_ok=True, mode=0o700)
    p["backups"].chmod(0o700)
    payload, status = run_backup_utility(
        "create",
        "--db-path",
        config["database_path"],
        "--backup-dir",
        str(p["backups"]),
    )
    for key in ("backup_path", "manifest_path"):
        value = payload.get(key)
        if value and Path(str(value)).is_file():
            Path(str(value)).chmod(0o600)
    payload["operation"] = "host_backup"
    payload["secret_store_included"] = False
    payload["hashed_auth_state_included"] = True
    payload["host_may_remain_running"] = True
    emit(payload)
    return status


def cmd_backup_verify(args) -> int:
    require_initialized()
    p = paths()
    arguments = ["verify"]
    if args.backup:
        arguments.extend(["--backup", str(Path(args.backup).expanduser().resolve())])
    else:
        arguments.extend(["--backup-dir", str(p["backups"])])
    payload, status = run_backup_utility(*arguments)
    payload["operation"] = "host_backup_verify"
    payload["read_only"] = True
    emit(payload)
    return status


def cmd_restore(args) -> int:
    config, _secret_values = require_initialized()
    p = paths()
    pid = int(read_json(p["pid"]).get("pid") or 0)
    if process_alive(pid):
        emit({
            "ok": False,
            "operation": "host_restore",
            "error": "host_running",
            "message": "Stop the Host before restoring its authority ledger.",
            "next_action": "agentops host stop",
            "token_omitted": True,
        })
        return 2
    if not args.confirm_restore:
        emit({
            "ok": False,
            "operation": "host_restore",
            "dry_run": True,
            "error": "confirm_restore_required",
            "message": "Re-run with --confirm-restore after verifying the selected backup.",
            "token_omitted": True,
        })
        return 2
    arguments = [
        "restore",
        "--backup",
        str(Path(args.backup).expanduser().resolve()),
        "--target",
        config["database_path"],
        "--confirm-restore",
    ]
    if Path(config["database_path"]).exists():
        arguments.append("--overwrite")
    payload, status = run_backup_utility(*arguments)
    for key in ("target_path", "pre_restore_copy"):
        value = payload.get(key)
        if value and Path(str(value)).is_file():
            Path(str(value)).chmod(0o600)
    payload["operation"] = "host_restore"
    payload["secret_store_restored"] = False
    payload["hashed_auth_records_restored"] = True
    payload["restored_auth_state_revoked"] = True
    payload["restart_required"] = status == 0
    payload["next_action"] = "agentops host start" if status == 0 else "Verify the backup and retry."
    emit(payload)
    return status


def install_state() -> dict:
    configured = os.environ.get("AGENTOPS_INSTALL_ROOT")
    install_root = Path(configured).expanduser().resolve() if configured else (
        ROOT.parent.parent if ROOT.parent.name == "versions" else ROOT
    )
    current = install_root / "current"
    previous = install_root / "previous"

    def release(link: Path) -> dict:
        if not link.is_symlink():
            return {}
        target = link.resolve()
        versions = (install_root / "versions").resolve()
        if versions not in target.parents or not target.is_dir():
            return {}
        manifest = read_json(target / "release-manifest.json")
        if not manifest:
            return {}
        return {
            "version": manifest.get("version"),
            "git_commit": manifest.get("git_commit"),
            "target": str(target),
        }

    return {
        "install_root": install_root,
        "current_link": current,
        "previous_link": previous,
        "current": release(current),
        "previous": release(previous),
    }


def cmd_version(_args) -> int:
    state = install_state()
    current = state["current"]
    emit({
        "ok": bool(current),
        "operation": "host_version",
        "packaged_install": bool(current),
        "version": current.get("version") or "development",
        "git_commit": current.get("git_commit"),
        "previous_version": state["previous"].get("version"),
        "token_omitted": True,
    })
    return 0


def cmd_update(args) -> int:
    state = install_state()
    current = state["current"]
    if not args.check:
        emit({
            "ok": False,
            "operation": "host_update",
            "error": "check_required",
            "message": "Use --check for the side-effect-free update status command.",
            "token_omitted": True,
        })
        return 2
    emit({
        "ok": bool(current),
        "operation": "host_update_check",
        "check_only": True,
        "network_used": False,
        "current_version": current.get("version") or "development",
        "current_git_commit": current.get("git_commit"),
        "previous_version": state["previous"].get("version"),
        "update_available": "unknown",
        "next_action": "Install a newer verified release bundle while the Host is stopped.",
        "token_omitted": True,
    })
    return 0 if current else 1


def cmd_rollback(args) -> int:
    config, _secret_values = require_initialized()
    p = paths()
    pid = int(read_json(p["pid"]).get("pid") or 0)
    if process_alive(pid):
        emit({
            "ok": False,
            "operation": "host_rollback",
            "error": "host_running",
            "next_action": "agentops host stop",
            "token_omitted": True,
        })
        return 2
    state = install_state()
    current = state["current"]
    previous = state["previous"]
    if not current or not previous:
        emit({
            "ok": False,
            "operation": "host_rollback",
            "error": "previous_version_unavailable",
            "token_omitted": True,
        })
        return 2
    if not args.confirm_rollback:
        emit({
            "ok": False,
            "operation": "host_rollback",
            "dry_run": True,
            "error": "confirm_rollback_required",
            "from_version": current.get("version"),
            "to_version": previous.get("version"),
            "token_omitted": True,
        })
        return 2
    p["backups"].mkdir(parents=True, exist_ok=True, mode=0o700)
    backup, backup_status = run_backup_utility(
        "create",
        "--db-path",
        config["database_path"],
        "--backup-dir",
        str(p["backups"]),
    )
    if backup_status != 0 or not backup.get("ok"):
        emit({
            "ok": False,
            "operation": "host_rollback",
            "error": "pre_rollback_backup_failed",
            "token_omitted": True,
        })
        return 1
    for key in ("backup_path", "manifest_path"):
        value = backup.get(key)
        if value and Path(str(value)).is_file():
            Path(str(value)).chmod(0o600)

    current_link = state["current_link"]
    previous_link = state["previous_link"]
    next_current = current_link.with_name("current.next")
    next_previous = previous_link.with_name("previous.next")
    for temporary in (next_current, next_previous):
        temporary.unlink(missing_ok=True)
    next_current.symlink_to(previous["target"])
    next_previous.symlink_to(current["target"])
    os.replace(next_current, current_link)
    try:
        os.replace(next_previous, previous_link)
    except OSError:
        recovery = current_link.with_name("current.recovery")
        recovery.unlink(missing_ok=True)
        recovery.symlink_to(current["target"])
        os.replace(recovery, current_link)
        next_previous.unlink(missing_ok=True)
        emit({
            "ok": False,
            "operation": "host_rollback",
            "error": "binary_pointer_swap_failed",
            "current_version_preserved": True,
            "token_omitted": True,
        })
        return 1
    emit({
        "ok": True,
        "operation": "host_rollback",
        "from_version": current.get("version"),
        "to_version": previous.get("version"),
        "pre_rollback_backup_path": backup.get("backup_path"),
        "data_path_unchanged": True,
        "restart_required": True,
        "next_action": "agentops host start",
        "token_omitted": True,
    })
    return 0


def cmd_console_url(_args) -> int:
    config, _secret_values = require_initialized()
    ts = tailscale_state()
    local_url = f"http://{config['host']}:{config['port']}/workspace"
    private_url = f"https://{ts['dns_name']}/workspace" if ts["dns_name"] else ""
    emit({
        "ok": True,
        "operation": "host_console_url",
        "local_console_url": local_url,
        "private_console_url": private_url,
        "private_url_ready": bool(private_url and ts["backend_state"] == "Running"),
        "token_omitted": True,
    })
    return 0


def cmd_tailscale_preview(_args) -> int:
    config, _secret_values = require_initialized()
    target = f"http://{config['host']}:{config['port']}"
    ts = tailscale_state()
    emit({
        "ok": True,
        "operation": "host_tailscale_preview",
        "preview_only": True,
        "command": f"tailscale serve --bg {target}",
        "revoke_command": "tailscale serve reset",
        "tailscale": ts,
        "public_funnel_enabled": False,
        "automatic_execution": False,
        "token_omitted": True,
    })
    return 0


def cmd_tailscale_apply(args) -> int:
    config, _secret_values = require_initialized()
    target = f"http://{config['host']}:{config['port']}"
    ts = tailscale_state()
    preview = {
        "ok": False,
        "operation": "host_tailscale_apply",
        "preview_only": not args.confirm,
        "command": f"tailscale serve --bg {target}",
        "tailscale": ts,
        "public_funnel_enabled": False,
        "token_omitted": True,
    }
    if not args.confirm:
        preview.update({"error": "confirmation_required", "message": "Re-run with --confirm after reviewing the Serve command."})
        emit(preview)
        return 2
    binary, _source = tailscale_binary()
    if not binary or ts["backend_state"] != "Running" or not ts["dns_name"]:
        preview.update({"error": "tailscale_not_ready", "message": "Tailscale must be installed, Running, and have a DNS name."})
        emit(preview)
        return 2
    process = subprocess.run([binary, "serve", "--bg", target], capture_output=True, text=True, timeout=30, check=False)
    if process.returncode != 0:
        preview.update({"error": "tailscale_serve_failed", "message": "Tailscale Serve failed; command output was omitted.", "exit_code": process.returncode})
        emit(preview)
        return 1
    origin = f"https://{ts['dns_name']}"
    origins = sorted(set(config.get("allowed_origins") or []) | {origin})
    config.update({
        "allowed_origins": origins,
        "network_publication": "tailscale_serve",
        "private_console_origin": origin,
        "cookie_secure": True,
    })
    write_private_json(paths()["config"], config)
    emit({
        "ok": True,
        "operation": "host_tailscale_apply",
        "private_console_url": origin + "/workspace",
        "network_publication": "tailscale_serve",
        "public_funnel_enabled": False,
        "restart_required": True,
        "next_action": "agentops host restart",
        "command_output_omitted": True,
        "token_omitted": True,
    })
    return 0


def cmd_tailscale_revoke(args) -> int:
    config, _secret_values = require_initialized()
    if not args.confirm:
        emit({
            "ok": False,
            "operation": "host_tailscale_revoke",
            "preview_only": True,
            "error": "confirmation_required",
            "command": "tailscale serve reset",
            "token_omitted": True,
        })
        return 2
    binary, _source = tailscale_binary()
    if not binary:
        emit({"ok": False, "operation": "host_tailscale_revoke", "error": "tailscale_not_installed", "token_omitted": True})
        return 2
    process = subprocess.run([binary, "serve", "reset"], capture_output=True, text=True, timeout=30, check=False)
    if process.returncode != 0:
        emit({
            "ok": False,
            "operation": "host_tailscale_revoke",
            "error": "tailscale_reset_failed",
            "exit_code": process.returncode,
            "command_output_omitted": True,
            "token_omitted": True,
        })
        return 1
    local_origin = f"http://{config['host']}:{config['port']}"
    config.update({
        "allowed_origins": [local_origin],
        "network_publication": "disabled",
        "private_console_origin": "",
        "cookie_secure": False,
    })
    write_private_json(paths()["config"], config)
    emit({
        "ok": True,
        "operation": "host_tailscale_revoke",
        "network_publication": "disabled",
        "restart_required": True,
        "next_action": "agentops host restart",
        "command_output_omitted": True,
        "token_omitted": True,
    })
    return 0


def add_start_options(parser) -> None:
    parser.add_argument("--foreground", action="store_true")
    parser.add_argument("--build-ui", action="store_true")
    parser.add_argument("--install-ui", action="store_true")
    parser.add_argument("--worker", action="append", choices=["mock", "hermes", "openclaw"])
    parser.add_argument("--no-workers", action="store_true")
    parser.add_argument("--confirm-live-workers", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="agentops host", description="Manage the private local AgentOps MIS host.")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create private host config and one-time Owner setup code.")
    init.add_argument("--port", type=int, default=8787)
    init.add_argument("--workspace-id", default="local-demo")
    init.add_argument("--ui-dist")
    init.set_defaults(handler=cmd_init)
    start = sub.add_parser("start", help="Start the private host in the background by default.")
    add_start_options(start)
    start.set_defaults(handler=cmd_start)
    stop = sub.add_parser("stop", help="Stop the managed private host process group.")
    stop.set_defaults(handler=cmd_stop)
    restart = sub.add_parser("restart", help="Restart the managed private host.")
    add_start_options(restart)
    restart.set_defaults(handler=cmd_restart)
    status = sub.add_parser("status", help="Show redacted host, health and private-network status.")
    status.set_defaults(handler=cmd_status)
    doctor = sub.add_parser("doctor", help="Check private files, UI bundle and Tailscale readiness.")
    doctor.set_defaults(handler=cmd_doctor)
    logs = sub.add_parser("logs", help="Show log metadata without printing raw host output.")
    logs.set_defaults(handler=cmd_logs)
    backup = sub.add_parser("backup", help="Create a verified SQLite authority-ledger backup while the Host may remain running.")
    backup.set_defaults(handler=cmd_backup)
    backup_verify = sub.add_parser("backup-verify", help="Verify the latest or selected Host backup without printing ledger rows.")
    backup_verify.add_argument("--backup")
    backup_verify.set_defaults(handler=cmd_backup_verify)
    restore = sub.add_parser("restore", help="Restore a verified ledger backup while the Host is stopped.")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--confirm-restore", action="store_true")
    restore.set_defaults(handler=cmd_restore)
    version = sub.add_parser("version", help="Show packaged release provenance without contacting the network.")
    version.set_defaults(handler=cmd_version)
    update = sub.add_parser("update", help="Check local packaged update state without installing anything.")
    update.add_argument("--check", action="store_true")
    update.set_defaults(handler=cmd_update)
    rollback = sub.add_parser("rollback", help="Switch to the previous verified binary after a local ledger backup.")
    rollback.add_argument("--confirm-rollback", action="store_true")
    rollback.set_defaults(handler=cmd_rollback)
    console_url = sub.add_parser("console-url", help="Show local and private console URLs.")
    console_url.set_defaults(handler=cmd_console_url)
    preview = sub.add_parser("tailscale-preview", help="Preview Tailscale Serve and revoke commands without executing them.")
    preview.set_defaults(handler=cmd_tailscale_preview)
    apply = sub.add_parser("tailscale-apply", help="Apply Tailscale Serve only after explicit confirmation.")
    apply.add_argument("--confirm", action="store_true")
    apply.set_defaults(handler=cmd_tailscale_apply)
    revoke = sub.add_parser("tailscale-revoke", help="Reset Tailscale Serve only after explicit confirmation.")
    revoke.add_argument("--confirm", action="store_true")
    revoke.set_defaults(handler=cmd_tailscale_revoke)
    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except RuntimeError as exc:
        emit({"ok": False, "operation": f"host_{args.command}", "error": "host_not_ready", "message": str(exc), "token_omitted": True})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
