#!/usr/bin/env python3
"""Run guarded Relay recovery against real systemd on a disposable Linux VM."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
import tempfile
from dataclasses import replace
from pathlib import Path


sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agentops_mis_cli.relay_activation import (  # noqa: E402
    CONTROLLED_STOP_EXEC_STATUS,
    ENABLEMENT_LINK_PATH,
    INVOCATION_ID_PATTERN,
    MAX_SYSTEMD_SHOW_BYTES,
    SYSTEMCTL_PATHS,
    SYSTEMD_PROPERTIES,
    UNIT_PATH,
    UNIT_NAME,
    ActivationPrerequisiteSnapshot,
    FileIdentity,
    LinkIdentity,
    compile_activation_plan,
    parse_systemd_show_bytes,
)
from agentops_mis_cli.relay_activation_evidence import (  # noqa: E402
    build_activation_journal_identity,
)
from agentops_mis_cli.relay_activation_journal import (  # noqa: E402
    GENESIS_REVISION_SHA256,
    _open_fixture_store,
    build_activation_revision,
)
from agentops_mis_cli.relay_activation_recovery_controller import (  # noqa: E402
    _run_confirmed_recovery_write_with,
)
from agentops_mis_cli.relay_activation_recovery_executor import (  # noqa: E402
    _run_confirmed_recovery_step_with,
)
from agentops_mis_cli.relay_activation_recovery_preview import (  # noqa: E402
    _preview_activation_recovery_with,
)
from agentops_mis_cli.relay_systemd_mutation import (  # noqa: E402
    _run_bound_systemd_mutation,
)
from agentops_mis_cli.relay_systemd_read import (  # noqa: E402
    read_systemd_show,
)
from scripts.relay_activation_recovery_decision_smoke import (  # noqa: E402
    prerequisites,
)


OPT_IN = "AGENTOPS_RELAY_LINUX_SYSTEMD_ACCEPTANCE"
UNIT_BYTES = b"""[Unit]
Description=AgentOps MIS disposable recovery acceptance

[Service]
Type=simple
ExecStart=/usr/bin/sleep infinity
DynamicUser=yes
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict

[Install]
WantedBy=multi-user.target
"""
UNIT_CHANGED_BYTES = UNIT_BYTES + b"\n# recovery acceptance\n"
MAX_STEP_COUNT = 16
SYSTEMD_SHOW_TIMEOUT_SECONDS = 5


class AcceptanceFailure(Exception):
    def __init__(self, stage: str = "unknown") -> None:
        self.stage = stage
        super().__init__("linux_systemd_acceptance_failed")


def _fingerprint(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
        stat.S_IFMT(metadata.st_mode),
        stat.S_IMODE(metadata.st_mode),
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_nlink,
    )


def _file_identity(path: str) -> FileIdentity:
    descriptor = -1
    try:
        before = os.lstat(path)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size <= 0
            or before.st_nlink != 1
        ):
            raise AcceptanceFailure
        descriptor = os.open(
            path,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        opened = os.fstat(descriptor)
        if _fingerprint(before) != _fingerprint(opened):
            raise AcceptanceFailure
        digest = hashlib.sha256()
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(64 * 1024, remaining))
            if not chunk:
                raise AcceptanceFailure
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise AcceptanceFailure
        after = os.fstat(descriptor)
        current = os.lstat(path)
        if not (
            _fingerprint(opened)
            == _fingerprint(after)
            == _fingerprint(current)
        ):
            raise AcceptanceFailure
        return FileIdentity(
            kind="regular",
            canonical_path=path,
            device_id=opened.st_dev,
            inode=opened.st_ino,
            owner_id=opened.st_uid,
            group_id=opened.st_gid,
            mode=stat.S_IMODE(opened.st_mode),
            nlink=opened.st_nlink,
            size=opened.st_size,
            content_sha256=digest.hexdigest(),
        )
    except AcceptanceFailure:
        raise
    except Exception:
        raise AcceptanceFailure from None
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _systemctl_identity() -> FileIdentity:
    for path in ("/usr/bin/systemctl", "/bin/systemctl"):
        if path not in SYSTEMCTL_PATHS:
            continue
        try:
            return _file_identity(path)
        except AcceptanceFailure:
            continue
    raise AcceptanceFailure


def _diagnose_rollback_stop(identity: FileIdentity) -> str:
    """Return one bounded classifier without retaining systemd output."""

    try:
        result = subprocess.run(
            (
                identity.canonical_path,
                "--system",
                "show",
                UNIT_NAME,
                "--no-pager",
                "--property=" + ",".join(SYSTEMD_PROPERTIES),
            ),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd="/",
            env={
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": "/usr/bin:/bin",
            },
            timeout=SYSTEMD_SHOW_TIMEOUT_SECONDS,
        )
    except Exception:
        return "rollback_rollback_stop_diagnostic_command"
    raw = result.stdout
    if (
        result.returncode != 0
        or not isinstance(raw, bytes)
        or not raw
        or len(raw) > MAX_SYSTEMD_SHOW_BYTES
        or b"\x00" in raw
        or b"\r" in raw
    ):
        return "rollback_rollback_stop_diagnostic_command"
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError:
        return "rollback_rollback_stop_diagnostic_shape"
    values: dict[str, str] = {}
    for line in lines:
        if "=" not in line:
            return "rollback_rollback_stop_diagnostic_shape"
        name, value = line.split("=", 1)
        if (
            name not in SYSTEMD_PROPERTIES
            or name in values
            or len(value) > 4096
        ):
            return "rollback_rollback_stop_diagnostic_shape"
        values[name] = value
    if set(values) != set(SYSTEMD_PROPERTIES):
        return "rollback_rollback_stop_diagnostic_shape"
    expected = (
        ("LoadState", {"loaded"}, "load_state"),
        ("UnitFileState", {"enabled"}, "unit_file_state"),
        ("ActiveState", {"inactive"}, "active_state"),
        ("SubState", {"dead"}, "sub_state"),
        ("Result", {"", "success"}, "result"),
        ("FragmentPath", {UNIT_PATH}, "fragment_path"),
        ("NeedDaemonReload", {"no"}, "daemon_reload"),
        ("MainPID", {"0"}, "main_pid"),
    )
    for name, allowed, classifier in expected:
        if values[name] not in allowed:
            return f"rollback_rollback_stop_diagnostic_{classifier}"
    exec_status_value = values["ExecMainStatus"]
    if (
        not exec_status_value
        or not exec_status_value.isascii()
        or not exec_status_value.isdecimal()
        or (
            len(exec_status_value) > 1
            and exec_status_value.startswith("0")
        )
        or int(exec_status_value) > 255
        or (
            int(exec_status_value)
            not in {0, CONTROLLED_STOP_EXEC_STATUS}
        )
        or (
            int(exec_status_value) == CONTROLLED_STOP_EXEC_STATUS
            and values["Result"] != "success"
        )
    ):
        return "rollback_rollback_stop_diagnostic_exec_status"
    invocation_id = values["InvocationID"]
    if (
        invocation_id
        and not INVOCATION_ID_PATTERN.fullmatch(invocation_id)
    ):
        return "rollback_rollback_stop_diagnostic_invocation_id"
    try:
        snapshot = parse_systemd_show_bytes(raw)
    except Exception:
        return "rollback_rollback_stop_diagnostic_parser"
    if (
        snapshot.active_state != "inactive"
        or snapshot.unit_file_state != "enabled"
        or snapshot.need_daemon_reload
    ):
        return "rollback_rollback_stop_diagnostic_observation"
    return "rollback_rollback_stop_diagnostic_valid_late_state"


def _enablement_links() -> tuple[LinkIdentity, ...]:
    try:
        metadata = os.lstat(ENABLEMENT_LINK_PATH)
    except FileNotFoundError:
        return ()
    except OSError:
        raise AcceptanceFailure from None
    if (
        not stat.S_ISLNK(metadata.st_mode)
        or Path(ENABLEMENT_LINK_PATH).resolve()
        != Path(UNIT_PATH)
    ):
        raise AcceptanceFailure
    return (
        LinkIdentity(
            kind="symlink",
            canonical_path=ENABLEMENT_LINK_PATH,
            target=UNIT_PATH,
            device_id=metadata.st_dev,
            inode=metadata.st_ino,
            owner_id=metadata.st_uid,
            group_id=metadata.st_gid,
            nlink=metadata.st_nlink,
        ),
    )


def _write_unit() -> None:
    descriptor = -1
    created: tuple[int, int] | None = None
    complete = False
    try:
        descriptor = os.open(
            UNIT_PATH,
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            0o644,
        )
        metadata = os.fstat(descriptor)
        created = (metadata.st_dev, metadata.st_ino)
        view = memoryview(UNIT_BYTES)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise AcceptanceFailure
            view = view[written:]
        os.fsync(descriptor)
        complete = True
    except AcceptanceFailure:
        raise
    except Exception:
        raise AcceptanceFailure from None
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass
        if created is not None and not complete:
            try:
                current = os.lstat(UNIT_PATH)
                if (current.st_dev, current.st_ino) == created:
                    os.unlink(UNIT_PATH)
            except OSError:
                pass


def _mark_unit_changed() -> None:
    descriptor = -1
    try:
        descriptor = os.open(
            UNIT_PATH,
            os.O_WRONLY
            | os.O_APPEND
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        if os.write(descriptor, b"\n# recovery acceptance\n") != 23:
            raise AcceptanceFailure
        os.fsync(descriptor)
    except AcceptanceFailure:
        raise
    except Exception:
        raise AcceptanceFailure from None
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _owned_unit() -> bool:
    descriptor = -1
    try:
        descriptor = os.open(
            UNIT_PATH,
            os.O_RDONLY
            | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
        )
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > len(UNIT_CHANGED_BYTES)
        ):
            return False
        payload = bytearray()
        while len(payload) < metadata.st_size:
            chunk = os.read(
                descriptor,
                metadata.st_size - len(payload),
            )
            if not chunk:
                return False
            payload.extend(chunk)
        return bytes(payload) in {UNIT_BYTES, UNIT_CHANGED_BYTES}
    except FileNotFoundError:
        return True
    except OSError:
        return False
    finally:
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError:
                pass


def _cleanup(systemctl: FileIdentity | None) -> bool:
    if not _owned_unit():
        return False
    command = (
        systemctl.canonical_path
        if systemctl is not None
        else "/usr/bin/systemctl"
    )
    for operation in ("stop", "disable"):
        try:
            subprocess.run(
                (
                    command,
                    "--system",
                    operation,
                    "agentops-mis-relay.service",
                ),
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=15,
            )
        except Exception:
            pass
    for path in (ENABLEMENT_LINK_PATH, UNIT_PATH):
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError:
            return False
    try:
        subprocess.run(
            (command, "--system", "daemon-reload"),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
        subprocess.run(
            (
                command,
                "--system",
                "reset-failed",
                "agentops-mis-relay.service",
            ),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=15,
        )
    except Exception:
        return False
    return not os.path.lexists(UNIT_PATH) and not os.path.lexists(
        ENABLEMENT_LINK_PATH
    )


def _run() -> dict[str, object]:
    if (
        os.environ.get(OPT_IN) != "1"
        or not sys.platform.startswith("linux")
        or os.geteuid() != 0
        or not Path("/run/systemd/system").is_dir()
        or os.path.lexists(UNIT_PATH)
        or os.path.lexists(ENABLEMENT_LINK_PATH)
    ):
        raise AcceptanceFailure("preflight")

    stage = "setup"
    systemctl: FileIdentity | None = None
    cleanup_ok = False
    forward_steps: list[str] = []
    rollback_steps: list[str] = []
    final_state = ""
    try:
        systemctl = _systemctl_identity()
        _write_unit()
        _run_bound_systemd_mutation(systemctl, "daemon_reload")
        _mark_unit_changed()
        unit = _file_identity(UNIT_PATH)
        base = replace(
            prerequisites(),
            unit=unit,
            systemctl=systemctl,
        )

        def scanner() -> ActivationPrerequisiteSnapshot:
            return replace(
                base,
                enablement_links=_enablement_links(),
            )

        stage = "initial_observation"
        initial_prerequisites = scanner()
        initial_systemd = read_systemd_show(initial_prerequisites)
        plan = compile_activation_plan(
            initial_prerequisites,
            initial_systemd,
        )
        if plan.ok is not True or plan.plan_sha256 is None:
            raise AcceptanceFailure
        identity = build_activation_journal_identity(
            initial_prerequisites,
            initial_systemd,
            confirmed_plan_sha256=plan.plan_sha256,
        )
        prepared = build_activation_revision(
            identity,
            revision=1,
            previous_revision_sha256=GENESIS_REVISION_SHA256,
            phase="prepared",
            step_id="transaction_open",
            owns_enable=False,
            owns_start=False,
        )

        with tempfile.TemporaryDirectory(
            prefix="relay-linux-systemd-recovery-"
        ) as temporary:
            journal_root = Path(temporary)
            journal_root.chmod(0o700)
            with _open_fixture_store(journal_root) as store:
                store.publish_revision(prepared)

                stage = "forward_execution"
                for _index in range(MAX_STEP_COUNT):
                    stage = "forward_preview"
                    decision = _preview_activation_recovery_with(
                        plan.plan_sha256,
                        "resume",
                        snapshot_loader=store._load_recovery_snapshot,
                        scanner=scanner,
                        systemd_reader=read_systemd_show,
                    )
                    operation = decision.get("operation_id")
                    if operation == "publish_success_receipt":
                        break
                    if operation != "run_step":
                        raise AcceptanceFailure
                    step_id = str(decision.get("step_id"))
                    if step_id not in {
                        "daemon_reload",
                        "enable",
                        "start",
                        "verify",
                    }:
                        raise AcceptanceFailure
                    stage = f"forward_{step_id}"
                    forward_steps.append(step_id)
                    _run_confirmed_recovery_step_with(
                        plan.plan_sha256,
                        "resume",
                        str(decision["decision_sha256"]),
                        store=store,
                        scanner=scanner,
                        systemd_reader=read_systemd_show,
                        mutation_runner=_run_bound_systemd_mutation,
                    )
                else:
                    raise AcceptanceFailure

                stage = "rollback_execution"
                for _index in range(MAX_STEP_COUNT):
                    stage = "rollback_preview"
                    decision = _preview_activation_recovery_with(
                        plan.plan_sha256,
                        "rollback",
                        snapshot_loader=store._load_recovery_snapshot,
                        scanner=scanner,
                        systemd_reader=read_systemd_show,
                    )
                    operation = decision.get("operation_id")
                    if operation == "run_step":
                        step_id = str(decision.get("step_id"))
                        if step_id not in {
                            "rollback_stop",
                            "rollback_disable",
                            "verify",
                        }:
                            raise AcceptanceFailure
                        stage = f"rollback_{step_id}"
                        rollback_steps.append(step_id)
                        try:
                            _run_confirmed_recovery_step_with(
                                plan.plan_sha256,
                                "rollback",
                                str(decision["decision_sha256"]),
                                store=store,
                                scanner=scanner,
                                systemd_reader=read_systemd_show,
                                mutation_runner=_run_bound_systemd_mutation,
                            )
                        except Exception:
                            if step_id == "rollback_stop":
                                raise AcceptanceFailure(
                                    _diagnose_rollback_stop(systemctl)
                                ) from None
                            raise
                    else:
                        action_id = str(decision.get("action_id"))
                        if action_id not in {
                            "publish_rollback_receipt",
                            "complete",
                        }:
                            raise AcceptanceFailure
                        stage = f"rollback_{action_id}"
                        result = _run_confirmed_recovery_write_with(
                            plan.plan_sha256,
                            "rollback",
                            str(decision["decision_sha256"]),
                            store=store,
                            scanner=scanner,
                            systemd_reader=read_systemd_show,
                        )
                        if action_id == "complete":
                            final_state = str(result.get("state"))
                            break
                else:
                    raise AcceptanceFailure

                final_systemd = read_systemd_show(scanner())
                snapshot = store._load_recovery_snapshot(
                    plan.plan_sha256
                )
                if (
                    final_state != "service_state_rolled_back"
                    or snapshot.revisions[-1].phase != "terminal"
                    or snapshot.revisions[-1].terminal_state
                    != "service_state_rolled_back"
                    or final_systemd.active_state != "inactive"
                    or final_systemd.unit_file_state != "disabled"
                    or _enablement_links()
                ):
                    raise AcceptanceFailure
        stage = "complete"
        return {
            "final_state": final_state,
            "forward_steps": forward_steps,
            "initial_reload_required": (
                initial_systemd.need_daemon_reload
            ),
            "journal_scope": "temporary_fixture",
            "linux_systemd": True,
            "network_used": False,
            "ok": True,
            "operation": "relay_linux_systemd_recovery_acceptance",
            "rollback_steps": rollback_steps,
            "stage": stage,
            "systemctl_bound": True,
        }
    except AcceptanceFailure as exc:
        raise AcceptanceFailure(
            stage if exc.stage == "unknown" else exc.stage
        ) from None
    except Exception:
        raise AcceptanceFailure(stage) from None
    finally:
        cleanup_ok = _cleanup(systemctl)
        if not cleanup_ok:
            raise AcceptanceFailure("cleanup")


def main() -> int:
    result: dict[str, object]
    try:
        result = _run()
        result["cleanup_ok"] = True
    except AcceptanceFailure as exc:
        result = {
            "cleanup_ok": (
                not os.path.lexists(UNIT_PATH)
                and not os.path.lexists(ENABLEMENT_LINK_PATH)
            ),
            "failure_id": "linux_systemd_acceptance_failed",
            "linux_systemd": sys.platform.startswith("linux"),
            "network_used": False,
            "ok": False,
            "operation": "relay_linux_systemd_recovery_acceptance",
            "stage": exc.stage,
        }
    except Exception:
        result = {
            "cleanup_ok": False,
            "failure_id": "linux_systemd_acceptance_failed",
            "linux_systemd": sys.platform.startswith("linux"),
            "network_used": False,
            "ok": False,
            "operation": "relay_linux_systemd_recovery_acceptance",
            "stage": "unknown",
        }
    print(json.dumps(result, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
