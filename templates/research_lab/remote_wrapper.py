"""Durable remote-side wrapper contract for governed SSH execution."""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import uuid
from pathlib import Path
from typing import Any, Callable, Mapping

from .contracts import ResearchError, canonical_hash
from .trust import CoreReceiptVerifier, require_core_receipt

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class DurableSSHWrapper:
    def __init__(self, *, governed_root: Path, trust: CoreReceiptVerifier, process_launcher: Callable[[Mapping[str, Any], Path], Mapping[str, Any]], process_probe: Callable[[int, str], bool] | None = None, process_cancel: Callable[[int, str], None] | None = None, terminal_verifier: Callable[[Mapping[str, Any], Mapping[str, Any]], bool] | None = None, launch_reconciler: Callable[[Mapping[str, Any], Path], Mapping[str, Any] | None] | None = None, maximum_artifact_bytes: int = 10 * 1024**3) -> None:
        self.root = governed_root.resolve(strict=True)
        self.process_launcher = process_launcher
        self.process_probe = process_probe or self._probe_process
        self.process_cancel = process_cancel or self._cancel_process
        self.terminal_verifier = terminal_verifier or (lambda _terminal, _launch: False)
        self.launch_reconciler = launch_reconciler or (lambda _fence, _attempt_dir: None)
        self.maximum_artifact_bytes = maximum_artifact_bytes
        self.trust = trust

    @staticmethod
    def _process_identity(pid: int) -> str:
        observed = subprocess.run(("ps", "-o", "lstart=", "-p", str(pid)), capture_output=True, text=True, timeout=5, check=False).stdout.strip()
        return canonical_hash({"pid": pid, "started_at": observed}) if observed else ""

    @classmethod
    def _probe_process(cls, pid: int, identity: str) -> bool:
        return bool(identity) and cls._process_identity(pid) == identity

    @classmethod
    def _cancel_process(cls, pid: int, identity: str) -> None:
        if not cls._probe_process(pid, identity):
            raise ResearchError("research.remote_pid_identity_mismatch", "remote PID is absent or has been reused")
        os.kill(pid, signal.SIGTERM)

    def _attempt_dir(self, attempt_id: str) -> Path:
        if not _ID.fullmatch(attempt_id):
            raise ResearchError("research.remote_attempt_invalid", "attempt ID is invalid")
        attempts = (self.root / "attempts").resolve()
        if not attempts.exists():
            attempts.mkdir()
            self._fsync_directory(self.root)
        value = (attempts / attempt_id).resolve()
        if self.root not in value.parents:
            raise ResearchError("research.remote_root_escape", "attempt path escapes governed root")
        if not value.exists():
            value.mkdir()
            self._fsync_directory(attempts)
        return value

    @staticmethod
    def _read(path: Path) -> Mapping[str, Any]:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ResearchError("research.remote_marker_invalid", "remote marker must be a structured receipt")
        supplied = str(value.get("receipt_hash") or "")
        unsigned = {key: child for key, child in value.items() if key != "receipt_hash"}
        if not re.fullmatch(r"[0-9a-f]{64}", supplied) or supplied != canonical_hash(unsigned):
            raise ResearchError("research.remote_marker_tampered", "remote marker integrity verification failed")
        return value

    @staticmethod
    def _write_once(path: Path, value: Mapping[str, Any]) -> None:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        descriptor = os.open(path, flags, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(dict(value), handle, sort_keys=True, separators=(",", ":"), allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        DurableSSHWrapper._fsync_directory(path.parent)

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @staticmethod
    def _replace(path: Path, value: Mapping[str, Any]) -> None:
        temporary = path.with_name(path.name + f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
        DurableSSHWrapper._write_once(temporary, value)
        os.replace(temporary, path)
        DurableSSHWrapper._fsync_directory(path.parent)

    @staticmethod
    def _atomic_create(path: Path, value: Mapping[str, Any]) -> None:
        """Create a complete no-clobber marker; a crash cannot expose partial JSON."""
        temporary = path.with_name(path.name + f".{os.getpid()}.{uuid.uuid4().hex}.tmp")
        DurableSSHWrapper._write_once(temporary, value)
        try:
            os.link(temporary, path)
            DurableSSHWrapper._fsync_directory(path.parent)
        finally:
            try:
                temporary.unlink()
                DurableSSHWrapper._fsync_directory(path.parent)
            except FileNotFoundError:
                pass

    @staticmethod
    def _receipt_from_launch(fence: Mapping[str, Any], launched: Mapping[str, Any]) -> dict[str, Any]:
        if launched.get("attempt_id") != fence["attempt_id"] or launched.get("request_hash") != fence["request_hash"]:
            raise ResearchError("research.remote_launch_invalid", "launcher result does not bind the fenced attempt and request")
        if not isinstance(launched.get("pid"), int) or launched["pid"] <= 1 or not isinstance(launched.get("process_start_identity"), str) or not launched["process_start_identity"]:
            raise ResearchError("research.remote_launch_invalid", "launcher did not return a durable PID and start identity")
        receipt = {
            "attempt_id": fence["attempt_id"],
            "operation": fence["operation"],
            "pid": launched["pid"],
            "process_start_identity": launched["process_start_identity"],
            "state": "running",
            "request_hash": fence["request_hash"],
            "authorization_receipt_hash": fence["authorization_receipt_hash"],
            "admission_receipt_hash": fence["admission_receipt_hash"],
            "target_snapshot_hash": fence["target_snapshot_hash"],
            "log_cursor": "0",
        }
        receipt["receipt_hash"] = canonical_hash(receipt)
        return receipt

    def _recover_fenced_launch(self, fence: Mapping[str, Any], attempt_dir: Path) -> dict[str, Any]:
        observed = self.launch_reconciler(fence, attempt_dir)
        if observed:
            if observed.get("authority") != "remote_launch_registry" or observed.get("authoritative") is not True:
                raise ResearchError("research.remote_reconcile_untrusted", "launch reconciliation lacks remote attempt authority")
            receipt = self._receipt_from_launch(fence, observed)
            self._atomic_create(attempt_dir / "receipt.json", receipt)
            return receipt
        unknown = {
            "attempt_id": fence["attempt_id"],
            "operation": fence["operation"],
            "state": "remote_unknown",
            "request_hash": fence["request_hash"],
            "authorization_receipt_hash": fence["authorization_receipt_hash"],
            "admission_receipt_hash": fence["admission_receipt_hash"],
            "target_snapshot_hash": fence["target_snapshot_hash"],
            "launch_fence_hash": fence["receipt_hash"],
            "log_cursor": "0",
        }
        unknown["receipt_hash"] = canonical_hash(unknown)
        return unknown

    def handle(self, *, operation: str, stdin_bytes: bytes) -> Mapping[str, Any]:
        if len(stdin_bytes) > 1024 * 1024:
            raise ResearchError("research.remote_request_too_large", "remote request exceeds maximum size")
        request = json.loads(stdin_bytes.decode("utf-8"))
        if request.get("operation") != operation:
            raise ResearchError("research.remote_operation_mismatch", "request operation does not match argv")
        for field in ("authorization_receipt_hash", "target_snapshot_hash", "admission_receipt_hash"):
            if not re.fullmatch(r"[0-9a-f]{64}", str(request.get(field) or "")):
                raise ResearchError("research.remote_request_untrusted", "remote request must bind Core authorization and ComputeTarget snapshot")
        core_authorization = require_core_receipt(request.get("core_authorization") or {}, trust=self.trust, purpose="research.execution-authorization/v1", bindings={"tool_id": "research_lab.tool.ssh_execute", "decision": "allow", "executed_once": True})
        unsigned_request = {key: value for key, value in request.items() if key not in {"core_authorization", "authorization_receipt_hash"}}
        if core_authorization.get("request_hash") != canonical_hash(unsigned_request) or core_authorization["receipt_hash"] != request["authorization_receipt_hash"]:
            raise ResearchError("research.remote_request_untrusted", "remote Core authorization does not bind the exact wire request")
        attempt_id = str(request.get("attempt_id") or "")
        attempt_dir = self._attempt_dir(attempt_id)
        marker = attempt_dir / "receipt.json"
        fence_path = attempt_dir / "launch-intent.json"
        if operation in {"submit", "resume"}:
            if marker.exists():
                receipt = dict(self._read(marker))
                if receipt.get("request_hash") != canonical_hash(request) or receipt.get("operation") != operation:
                    raise ResearchError("research.remote_replay_mismatch", "attempt replay does not match the durable request")
            elif fence_path.exists():
                fence = dict(self._read(fence_path))
                if fence.get("attempt_id") != attempt_id or fence.get("operation") != operation or fence.get("request_hash") != canonical_hash(request):
                    raise ResearchError("research.remote_replay_mismatch", "launch fence does not bind this exact attempt request")
                receipt = self._recover_fenced_launch(fence, attempt_dir)
            else:
                fence = {
                    "attempt_id": attempt_id,
                    "operation": operation,
                    "request_hash": canonical_hash(request),
                    "authorization_receipt_hash": request["authorization_receipt_hash"],
                    "admission_receipt_hash": request["admission_receipt_hash"],
                    "target_snapshot_hash": request["target_snapshot_hash"],
                    "state": "launch_fenced",
                }
                fence["receipt_hash"] = canonical_hash(fence)
                self._write_once(fence_path, fence)
                launched = dict(self.process_launcher(request, attempt_dir))
                receipt = self._receipt_from_launch(fence, launched)
                self._atomic_create(marker, receipt)
            return receipt
        if not marker.exists():
            raise ResearchError("research.remote_attempt_missing", "remote attempt marker does not exist")
        prior = dict(self._read(marker))
        if operation in {"status", "reconcile", "cancel"}:
            pid, identity = int(prior["pid"]), str(prior.get("process_start_identity") or "")
            terminal_path = attempt_dir / "terminal.json"
            terminal = dict(self._read(terminal_path)) if terminal_path.exists() else {}
            if terminal and (
                terminal.get("attempt_id") != attempt_id
                or terminal.get("process_start_identity") != identity
                or terminal.get("state") not in {"completed", "failed", "cancelled", "timed_out"}
                or terminal.get("execution_request_hash") != prior.get("request_hash")
                or terminal.get("authorization_receipt_hash") != prior.get("authorization_receipt_hash")
                or terminal.get("admission_receipt_hash") != prior.get("admission_receipt_hash")
                or terminal.get("target_snapshot_hash") != prior.get("target_snapshot_hash")
                or not self.terminal_verifier(terminal, prior)
            ):
                raise ResearchError("research.remote_terminal_invalid", "remote terminal receipt does not bind the durable process")
            if terminal:
                state = str(terminal["state"])
                alive = False
            elif operation == "cancel" and prior.get("state") not in {"cancelled", "completed", "failed", "timed_out"}:
                self.process_cancel(pid, identity)
                alive = self.process_probe(pid, identity)
                if alive:
                    raise ResearchError("research.remote_cancel_unconfirmed", "remote process remains alive after cancellation")
                state = "cancelled"
            else:
                alive = self.process_probe(pid, identity)
                state = str(prior.get("state")) if prior.get("state") in {"cancelled", "completed", "failed", "timed_out"} else ("running" if alive else "remote_unknown")
            receipt = {**prior, "operation": operation, "state": state, "request_hash": canonical_hash(request), "authorization_receipt_hash": request["authorization_receipt_hash"], "admission_receipt_hash": request["admission_receipt_hash"], "target_snapshot_hash": request["target_snapshot_hash"], "parent_request_hash": prior.get("request_hash"), "log_cursor": prior.get("log_cursor", "0")}
            durable = {**receipt, "operation": prior.get("operation", "submit")}
            durable["request_hash"] = prior.get("request_hash")
            durable["authorization_receipt_hash"] = prior.get("authorization_receipt_hash")
            durable["admission_receipt_hash"] = prior.get("admission_receipt_hash")
            durable["target_snapshot_hash"] = prior.get("target_snapshot_hash")
            durable.pop("parent_request_hash", None)
            durable["receipt_hash"] = canonical_hash({key: value for key, value in durable.items() if key != "receipt_hash"})
            self._replace(marker, durable)
        elif operation in {"logs", "collect"}:
            artifact_path = attempt_dir / ("stdout.log" if operation == "logs" else "artifact.tar")
            if not artifact_path.is_file() or artifact_path.is_symlink():
                raise ResearchError("research.remote_artifact_missing", "requested remote Artifact is unavailable")
            if artifact_path.stat().st_size > self.maximum_artifact_bytes:
                raise ResearchError("research.remote_artifact_too_large", "requested remote Artifact exceeds the configured transfer limit")
            digest_state = hashlib.sha256()
            with artifact_path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest_state.update(chunk)
            digest = digest_state.hexdigest()
            receipt = {"attempt_id": attempt_id, "operation": operation, "artifact_id": f"art_{digest[:20]}", "artifact_sha256": digest, "request_hash": canonical_hash(request), "authorization_receipt_hash": request["authorization_receipt_hash"], "admission_receipt_hash": request["admission_receipt_hash"], "target_snapshot_hash": request["target_snapshot_hash"], "parent_request_hash": prior.get("request_hash"), "log_cursor": str(artifact_path.stat().st_size)}
        else:
            raise ResearchError("research.invalid_ssh_operation", "remote operation is not allowlisted")
        receipt.pop("receipt_hash", None)
        receipt["receipt_hash"] = canonical_hash(receipt)
        return receipt
