"""Fail-closed planning and stopped-Host rotation for private Host logs."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import secrets
import stat
from pathlib import Path


HOST_LOG_ROTATE_DEFAULT_MAX_BYTES = 8 * 1024 * 1024
HOST_LOG_ROTATE_MIN_MAX_BYTES = 1024 * 1024
HOST_LOG_ROTATE_DEFAULT_BACKUPS = 5
HOST_LOG_ROTATE_MIN_BACKUPS = 2
HOST_LOG_ROTATE_MAX_BACKUPS = 20
HOST_LOG_ROTATE_OUTPUT_LIMIT = 100
HOST_LOG_ROTATE_DIRECTORY_ENTRY_LIMIT = 256
_BACKUP_PATTERN = re.compile(r"^host\.log\.([1-9][0-9]*)$")
_QUARANTINE_PREFIX = ".agentops-log-rotate-quarantine-"


def _error(error: str, **extra) -> tuple[dict, int]:
    return {
        "ok": False,
        "operation": "host_log_rotate",
        "dry_run": True,
        "error": error,
        "content_omitted": True,
        "paths_omitted": True,
        "token_omitted": True,
        **extra,
    }, 1


def _metadata(path: Path, *, label: str) -> tuple[dict | None, dict | None]:
    try:
        value = path.lstat()
    except OSError:
        return None, {"error": "host_log_inventory_unreadable", "entry_label": label}
    if path.is_symlink():
        return None, {"error": "host_log_inventory_symlink", "entry_label": label}
    if not stat.S_ISREG(value.st_mode):
        return None, {"error": "host_log_inventory_not_regular", "entry_label": label}
    if value.st_uid != os.getuid():
        return None, {"error": "host_log_inventory_wrong_owner", "entry_label": label}
    if stat.S_IMODE(value.st_mode) != 0o600:
        return None, {"error": "host_log_inventory_permissions_unsafe", "entry_label": label}
    if value.st_nlink != 1:
        return None, {"error": "host_log_inventory_hardlink", "entry_label": label}
    return {
        "label": label,
        "device": int(value.st_dev),
        "inode": int(value.st_ino),
        "mode": stat.S_IMODE(value.st_mode),
        "uid": int(value.st_uid),
        "links": int(value.st_nlink),
        "size_bytes": int(value.st_size),
        "mtime_ns": int(value.st_mtime_ns),
        "ctime_ns": int(value.st_ctime_ns),
    }, None


def _entry_fingerprint(path: Path) -> dict:
    value = path.lstat()
    return {
        "name_sha256": hashlib.sha256(path.name.encode("utf-8")).hexdigest(),
        "device": int(value.st_dev),
        "inode": int(value.st_ino),
        "mode": int(value.st_mode),
        "uid": int(value.st_uid),
        "links": int(value.st_nlink),
        "size_bytes": int(value.st_size),
        "mtime_ns": int(value.st_mtime_ns),
        "ctime_ns": int(value.st_ctime_ns),
    }


def _inventory(log_dir: Path) -> tuple[dict, dict | None]:
    if log_dir.is_symlink():
        return {}, {"error": "host_log_directory_symlink"}
    try:
        directory = log_dir.lstat()
    except FileNotFoundError:
        return {
            "directory": None,
            "directory_entries": [],
            "active": None,
            "backups": [],
        }, None
    except OSError:
        return {}, {"error": "host_log_directory_unreadable"}
    if not stat.S_ISDIR(directory.st_mode):
        return {}, {"error": "host_log_directory_not_directory"}
    if directory.st_uid != os.getuid() or stat.S_IMODE(directory.st_mode) != 0o700:
        return {}, {"error": "host_log_directory_permissions_unsafe"}
    try:
        entries = sorted(log_dir.iterdir(), key=lambda item: item.name)
    except OSError:
        return {}, {"error": "host_log_directory_unreadable"}
    if len(entries) > HOST_LOG_ROTATE_DIRECTORY_ENTRY_LIMIT:
        return {}, {
            "error": "host_log_directory_entry_limit_exceeded",
            "entry_count": len(entries),
            "entry_limit": HOST_LOG_ROTATE_DIRECTORY_ENTRY_LIMIT,
        }

    active = None
    backups: list[tuple[int, dict]] = []
    directory_entries = []
    for entry in entries:
        try:
            directory_entries.append(_entry_fingerprint(entry))
        except OSError:
            return {}, {"error": "host_log_inventory_unreadable"}
        if entry.name.startswith(_QUARANTINE_PREFIX):
            return {}, {"error": "host_log_rotation_quarantine_present"}
        if entry.name == "host.log":
            active, error = _metadata(entry, label="host.log")
            if error:
                return {}, error
            continue
        if not entry.name.startswith("host.log."):
            continue
        match = _BACKUP_PATTERN.fullmatch(entry.name)
        if not match:
            return {}, {"error": "host_log_inventory_unknown_entry"}
        suffix = int(match.group(1))
        if suffix > HOST_LOG_ROTATE_DIRECTORY_ENTRY_LIMIT:
            return {}, {"error": "host_log_inventory_suffix_too_large"}
        metadata, error = _metadata(entry, label=f"host.log.{suffix}")
        if error:
            return {}, error
        backups.append((suffix, metadata))

    backups.sort(key=lambda item: item[0])
    suffixes = [item[0] for item in backups]
    if suffixes and suffixes != list(range(1, suffixes[-1] + 1)):
        return {}, {"error": "host_log_inventory_gap"}
    return {
        "directory": {
            "device": int(directory.st_dev),
            "inode": int(directory.st_ino),
            "mode": stat.S_IMODE(directory.st_mode),
            "uid": int(directory.st_uid),
            "links": int(directory.st_nlink),
        },
        "directory_entries": directory_entries,
        "active": active,
        "backups": [metadata for _suffix, metadata in backups],
    }, None


def build_rotation_plan(log_dir: Path, *, max_bytes: int, backups: int) -> tuple[dict, dict | None]:
    inventory, error = _inventory(log_dir)
    if error:
        return {}, error
    active = inventory["active"]
    rotation_required = bool(active and int(active["size_bytes"]) > max_bytes)
    discard = []
    if rotation_required:
        discard = [
            item["label"]
            for item in inventory["backups"]
            if int(item["label"].rsplit(".", 1)[1]) >= backups
        ]
    canonical = {
        "plan_schema_version": 1,
        "operation": "host_log_rotate",
        "log_root_sha256": hashlib.sha256(str(log_dir.absolute()).encode("utf-8")).hexdigest(),
        "max_bytes": max_bytes,
        "backups": backups,
        "inventory": inventory,
        "rotation_required": rotation_required,
        "discard": discard,
    }
    encoded = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    labels = ([active["label"]] if active else []) + [item["label"] for item in inventory["backups"]]
    public = {
        "ok": True,
        "operation": "host_log_rotate",
        "dry_run": True,
        "directory_present": inventory["directory"] is not None,
        "host_log_present": active is not None,
        "active_size_bytes": int(active["size_bytes"]) if active else 0,
        "max_bytes": max_bytes,
        "minimum_max_bytes": HOST_LOG_ROTATE_MIN_MAX_BYTES,
        "backups": backups,
        "minimum_backups": HOST_LOG_ROTATE_MIN_BACKUPS,
        "maximum_backups": HOST_LOG_ROTATE_MAX_BACKUPS,
        "rotation_required": rotation_required,
        "inventory_count": len(labels),
        "inventory_labels": labels[:HOST_LOG_ROTATE_OUTPUT_LIMIT],
        "inventory_labels_truncated": len(labels) > HOST_LOG_ROTATE_OUTPUT_LIMIT,
        "discard_count": len(discard),
        "discard_labels": discard[:HOST_LOG_ROTATE_OUTPUT_LIMIT],
        "discard_labels_truncated": len(discard) > HOST_LOG_ROTATE_OUTPUT_LIMIT,
        "plan_hash": hashlib.sha256(encoded).hexdigest(),
        "content_omitted": True,
        "paths_omitted": True,
        "token_omitted": True,
    }
    return {"canonical": canonical, "public": public}, None


def _same_metadata(path: Path, expected: dict) -> bool:
    current, error = _metadata(path, label=expected["label"])
    return error is None and current == expected


def _same_moved_file(path: Path, expected: dict) -> bool:
    current, error = _metadata(path, label=expected["label"])
    if error is not None:
        return False
    stable_keys = ("device", "inode", "mode", "uid", "links", "size_bytes", "mtime_ns")
    return all(current[key] == expected[key] for key in stable_keys)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _replace_checked(source: Path, destination: Path, expected: dict) -> None:
    if not _same_metadata(source, expected) or destination.exists() or destination.is_symlink():
        raise OSError("log inventory changed")
    os.replace(source, destination)


def _same_directory(path: Path, expected: dict) -> bool:
    try:
        current = path.lstat()
    except OSError:
        return False
    return bool(
        not path.is_symlink()
        and stat.S_ISDIR(current.st_mode)
        and current.st_dev == expected["device"]
        and current.st_ino == expected["inode"]
        and stat.S_IMODE(current.st_mode) == expected["mode"]
        and current.st_uid == expected["uid"]
        and current.st_nlink == expected["links"]
    )


def rotate_logs(
    log_dir: Path,
    *,
    max_bytes: int = HOST_LOG_ROTATE_DEFAULT_MAX_BYTES,
    backups: int = HOST_LOG_ROTATE_DEFAULT_BACKUPS,
    confirm_rotate: bool = False,
    plan_hash: str = "",
) -> tuple[dict, int]:
    if max_bytes < HOST_LOG_ROTATE_MIN_MAX_BYTES:
        return _error(
            "host_log_max_bytes_below_minimum",
            max_bytes=max_bytes,
            minimum_max_bytes=HOST_LOG_ROTATE_MIN_MAX_BYTES,
        )
    if backups < HOST_LOG_ROTATE_MIN_BACKUPS or backups > HOST_LOG_ROTATE_MAX_BACKUPS:
        return _error(
            "host_log_backups_out_of_range",
            backups=backups,
            minimum_backups=HOST_LOG_ROTATE_MIN_BACKUPS,
            maximum_backups=HOST_LOG_ROTATE_MAX_BACKUPS,
        )

    plan, error = build_rotation_plan(log_dir, max_bytes=max_bytes, backups=backups)
    if error:
        return _error(error.pop("error"), **error)
    public = plan["public"]
    if plan_hash and not confirm_rotate:
        return {**public, "ok": False, "error": "host_log_confirmation_required", "confirmation_applied": False}, 2
    if not confirm_rotate:
        return public, 0
    if not plan_hash:
        return {**public, "ok": False, "error": "host_log_plan_hash_required", "confirmation_applied": False}, 2
    if not re.fullmatch(r"[0-9a-f]{64}", str(plan_hash)):
        return {**public, "ok": False, "error": "host_log_plan_hash_invalid", "confirmation_applied": False}, 2
    if not hmac.compare_digest(plan_hash, public["plan_hash"]):
        return {
            **public,
            "ok": False,
            "error": "host_log_plan_mismatch",
            "stale_plan": True,
            "confirmation_applied": False,
        }, 2

    refreshed, refreshed_error = build_rotation_plan(log_dir, max_bytes=max_bytes, backups=backups)
    if refreshed_error or not hmac.compare_digest(plan_hash, refreshed.get("public", {}).get("plan_hash", "")):
        return _error(
            "host_log_inventory_changed",
            stale_plan=True,
            confirmation_applied=False,
        )[0], 2
    public = refreshed["public"]
    if not public["rotation_required"]:
        return {
            **public,
            "dry_run": False,
            "rotated": False,
            "confirmation_applied": True,
            "written_file_count": 0,
            "deleted_file_count": 0,
        }, 0

    canonical = refreshed["canonical"]
    inventory = canonical["inventory"]
    metadata_by_label = {
        item["label"]: item
        for item in ([inventory["active"]] if inventory["active"] else []) + inventory["backups"]
    }
    existing_suffixes = [int(item["label"].rsplit(".", 1)[1]) for item in inventory["backups"]]
    discard_suffixes = [suffix for suffix in existing_suffixes if suffix >= backups]
    shift_suffixes = sorted((suffix for suffix in existing_suffixes if suffix < backups), reverse=True)
    quarantine = log_dir / f"{_QUARANTINE_PREFIX}{secrets.token_hex(8)}"
    moves: list[tuple[Path, Path, dict]] = []
    quarantine_created = False
    active_created = False
    try:
        if not _same_directory(log_dir, inventory["directory"]):
            raise OSError("log directory changed")
        if discard_suffixes:
            quarantine.mkdir(mode=0o700)
            quarantine_created = True
            quarantine_metadata = quarantine.lstat()
            if (
                quarantine.is_symlink()
                or not stat.S_ISDIR(quarantine_metadata.st_mode)
                or quarantine_metadata.st_uid != os.getuid()
                or stat.S_IMODE(quarantine_metadata.st_mode) != 0o700
                or quarantine_metadata.st_dev != inventory["directory"]["device"]
            ):
                raise OSError("unsafe log quarantine")
        for suffix in sorted(discard_suffixes, reverse=True):
            source = log_dir / f"host.log.{suffix}"
            destination = quarantine / source.name
            expected = metadata_by_label[f"host.log.{suffix}"]
            _replace_checked(source, destination, expected)
            moves.append((source, destination, expected))
            if not _same_moved_file(destination, expected):
                raise OSError("log move could not be verified")
        for suffix in shift_suffixes:
            source = log_dir / f"host.log.{suffix}"
            destination = log_dir / f"host.log.{suffix + 1}"
            expected = metadata_by_label[f"host.log.{suffix}"]
            _replace_checked(source, destination, expected)
            moves.append((source, destination, expected))
            if not _same_moved_file(destination, expected):
                raise OSError("log move could not be verified")
        active = log_dir / "host.log"
        first_backup = log_dir / "host.log.1"
        expected_active = metadata_by_label["host.log"]
        _replace_checked(active, first_backup, expected_active)
        moves.append((active, first_backup, expected_active))
        if not _same_moved_file(first_backup, expected_active):
            raise OSError("log move could not be verified")

        descriptor = os.open(
            active,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        active_created = True
        created = active.lstat()
        if (
            active.is_symlink()
            or not stat.S_ISREG(created.st_mode)
            or created.st_uid != os.getuid()
            or stat.S_IMODE(created.st_mode) != 0o600
            or created.st_nlink != 1
            or created.st_size != 0
        ):
            raise OSError("new log is unsafe")
        _fsync_directory(log_dir)
        if quarantine_created:
            _fsync_directory(quarantine)
    except OSError:
        rollback_ok = True
        if active_created:
            try:
                active.unlink()
            except OSError:
                rollback_ok = False
        for source, destination, expected in reversed(moves):
            try:
                if source.exists() or source.is_symlink() or not _same_moved_file(destination, expected):
                    rollback_ok = False
                    continue
                os.replace(destination, source)
                if not _same_moved_file(source, expected):
                    rollback_ok = False
            except OSError:
                rollback_ok = False
        if quarantine_created:
            try:
                quarantine.rmdir()
            except OSError:
                rollback_ok = False
        try:
            _fsync_directory(log_dir)
        except OSError:
            rollback_ok = False
        return {
            **public,
            "ok": False,
            "dry_run": False,
            "error": "host_log_rotation_failed",
            "confirmation_applied": True,
            "state_rolled_back": rollback_ok,
            "failure_detail_omitted": True,
        }, 1

    deleted_count = 0
    cleanup_failed = False
    for _source, destination, _expected in moves:
        if destination.parent != quarantine:
            continue
        try:
            destination.unlink()
            deleted_count += 1
        except OSError:
            cleanup_failed = True
    if quarantine_created:
        try:
            quarantine.rmdir()
        except OSError:
            cleanup_failed = True
    try:
        _fsync_directory(log_dir)
    except OSError:
        cleanup_failed = True
    if cleanup_failed:
        return {
            **public,
            "ok": False,
            "dry_run": False,
            "error": "host_log_rotation_cleanup_incomplete",
            "confirmation_applied": True,
            "rotated": True,
            "deleted_file_count": deleted_count,
            "failure_detail_omitted": True,
        }, 1
    return {
        **public,
        "dry_run": False,
        "rotated": True,
        "confirmation_applied": True,
        "written_file_count": len(shift_suffixes) + 2,
        "deleted_file_count": deleted_count,
    }, 0
