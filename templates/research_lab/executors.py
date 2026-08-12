"""Production executor contracts for local processes, OpenSSH, and Slurm.

Commands are always argv sequences and never evaluated through a local shell.
Remote actions use an allowlisted wrapper/scheduler interface.  Credential
values are deliberately absent; only secret-provider reference IDs are legal.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import socket
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Protocol, Sequence

from .contracts import ResearchError, canonical_hash, require_sha256
from .observability import redact_nested
from .trust import CoreTrustStore, reject_untrusted_payload, require_core_receipt

_SAFE_ATOM = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,255}$")
_SAFE_REMOTE_PATH = re.compile(r"^/[A-Za-z0-9._/-]+$")
_SECRET_REF = re.compile(r"^(?:mis-secret|keychain|vault)://[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_SENSITIVE = re.compile(r"(?:token|secret|password|passwd|api[_-]?key|private[_-]?key)", re.I)
_DANGEROUS_ENV = re.compile(r"^(?:LD_|DYLD_|PYTHONPATH$|PYTHONHOME$|BASH_ENV$|ENV$|PROMPT_COMMAND$)", re.I)


def _safe_argv(argv: Sequence[str]) -> tuple[str, ...]:
    if not argv or any(not isinstance(part, str) or not part or "\x00" in part or "\n" in part or "\r" in part for part in argv):
        raise ResearchError("research.unsafe_command", "command must be a non-empty control-character-free argv")
    if any(_SENSITIVE.search(part.split("=", 1)[0].lstrip("-")) and "=" in part for part in argv):
        raise ResearchError("research.secret_literal", "command cannot contain inline secret values")
    return tuple(argv)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _redact_literals(value: Any, literals: Sequence[str]) -> Any:
    value = redact_nested(value)
    if isinstance(value, Mapping):
        return {str(key): _redact_literals(child, literals) for key, child in value.items()}
    if isinstance(value, list):
        return [_redact_literals(child, literals) for child in value]
    if isinstance(value, str):
        for literal in literals:
            if literal:
                value = value.replace(literal, "[REDACTED]")
    return value


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    attempt_id: str
    argv: tuple[str, ...]
    workdir: Path
    environment: Mapping[str, str]
    timeout_seconds: float
    heartbeat_seconds: float = 5.0
    max_memory_bytes: int | None = None
    max_cpu_seconds: int | None = None
    tool_id: str = "research_lab.tool.local_execute"
    prepared_action_id: str = ""
    approval_id: str = ""
    admission_receipt_hash: str = ""

    def __post_init__(self) -> None:
        _safe_argv(self.argv)
        if not self.workdir.is_absolute() or not self.workdir.is_dir():
            raise ResearchError("research.invalid_workdir", "workdir must be an existing absolute directory")
        if self.timeout_seconds <= 0 or self.heartbeat_seconds <= 0:
            raise ResearchError("research.invalid_timeout", "timeouts must be positive")
        if any(_SENSITIVE.search(key) for key in self.environment):
            raise ResearchError("research.secret_literal", "environment must use secret-provider references")
        if any(not isinstance(key, str) or not isinstance(value, str) for key, value in self.environment.items()):
            raise ResearchError("research.invalid_environment", "environment must map strings to strings")
        if any(_DANGEROUS_ENV.search(key) for key in self.environment):
            raise ResearchError("research.unsafe_environment", "dynamic-loader and interpreter environment overrides are forbidden")
        reject_untrusted_payload(self.environment, path="execution.environment")
        if self.admission_receipt_hash:
            require_sha256(self.admission_receipt_hash, "admission_receipt_hash")


class ExecutionAuthorityPort(Protocol):
    def authorize_execute_once(self, *, workspace_id: str, tool_id: str, prepared_action_id: str, approval_id: str, request_hash: str) -> Mapping[str, Any]: ...


class SecretResolver(Protocol):
    def resolve_for_process(self, *, secret_ref: str, target_id: str) -> Mapping[str, str]: ...


def _verify_authorization(receipt: Mapping[str, Any], *, trust: CoreTrustStore, request_hash: str, tool_id: str, prepared_action_id: str, approval_id: str) -> Mapping[str, Any]:
    receipt = require_core_receipt(receipt, trust=trust, purpose="research.execution-authorization/v1", bindings={"request_hash": request_hash, "tool_id": tool_id, "prepared_action_id": prepared_action_id, "approval_id": approval_id})
    if (
        receipt.get("decision") != "allow"
        or receipt.get("executed_once") is not True
    ):
        raise ResearchError("research.execution_not_authorized", "Core PreparedAction/Approval execute-once readback does not bind the exact request")
    return receipt


@dataclass(frozen=True, slots=True)
class ExecutionPolicy:
    workspace_id: str
    workspace_root: Path
    executable_allowlist: tuple[str, ...]
    tool_allowlist: tuple[str, ...]
    untrusted_code: bool = True
    redaction_values: tuple[str, ...] = ()
    trusted_executable_roots: tuple[Path, ...] = (Path("/usr/bin"), Path("/bin"), Path("/usr/local/bin"), Path("/opt/homebrew/bin"), Path("/opt/homebrew/opt"), Path("/opt/homebrew/Cellar"))

    def validate(self, request: ExecutionRequest) -> Mapping[str, Any]:
        root = self.workspace_root.resolve(strict=True)
        workdir = request.workdir.resolve(strict=True)
        if workdir != root and root not in workdir.parents:
            raise ResearchError("research.workdir_outside_workspace", "workdir escapes governed workspace root")
        requested_executable = Path(request.argv[0])
        if not requested_executable.is_absolute():
            raise ResearchError("research.executable_path_required", "executable must be an exact absolute path")
        lexical_executable = Path(os.path.abspath(requested_executable))
        executable_path = requested_executable.resolve(strict=True)
        if not executable_path.is_file():
            raise ResearchError("research.executable_untrusted", "executable must resolve to a regular file")
        trusted_roots = tuple(path.resolve(strict=True) for path in self.trusted_executable_roots if path.exists())
        lexical_trusted_roots = tuple(Path(os.path.abspath(path)) for path in self.trusted_executable_roots if path.exists())
        lexical_allowed = lexical_executable == root or root in lexical_executable.parents or any(lexical_executable == trusted or trusted in lexical_executable.parents for trusted in lexical_trusted_roots)
        resolved_allowed = executable_path == root or root in executable_path.parents or any(executable_path == trusted or trusted in executable_path.parents for trusted in trusted_roots)
        if not lexical_allowed or not resolved_allowed:
            raise ResearchError("research.executable_untrusted", "executable is outside the workspace and trusted system roots")
        executable = executable_path.name
        if executable not in self.executable_allowlist or request.tool_id not in self.tool_allowlist:
            raise ResearchError("research.command_not_allowlisted", "tool or executable is not allowlisted")
        if executable in {"sh", "bash", "zsh", "dash", "fish", "cmd", "powershell", "pwsh"}:
            raise ResearchError("research.shell_trampoline_forbidden", "shell trampoline execution is forbidden")
        if self.untrusted_code and any(part in {"-c", "-m"} for part in request.argv[1:]):
            raise ResearchError("research.untrusted_dynamic_code", "dynamic interpreter code is forbidden for untrusted workspaces")
        return {"workspace_id": self.workspace_id, "workspace_root": str(root), "executable": executable, "executable_path": str(executable_path), "executable_sha256": _sha256_file(executable_path), "tool_id": request.tool_id}

    def redact_file(self, path: Path) -> None:
        if not self.redaction_values:
            return
        raw = path.read_bytes()
        for value in self.redaction_values:
            if value:
                raw = raw.replace(value.encode("utf-8"), b"[REDACTED]")
        path.write_bytes(raw)


class LocalProcessExecutor:
    """Process-group executor with heartbeat, cancellation, limits and adoption."""

    def __init__(self, authority: ExecutionAuthorityPort, policy: ExecutionPolicy, trust: CoreTrustStore) -> None:
        self._authority = authority
        self._policy = policy
        self._trust = trust

    def run(
        self,
        request: ExecutionRequest,
        *,
        output_dir: Path,
        heartbeat: Callable[[Mapping[str, Any]], None],
        cancelled: Callable[[], bool] = lambda: False,
    ) -> Mapping[str, Any]:
        policy_snapshot = self._policy.validate(request)
        prepared_request = {
            "attempt_id": request.attempt_id,
            "argv": list(request.argv),
            "resolved_executable_path": policy_snapshot["executable_path"],
            "resolved_executable_sha256": policy_snapshot["executable_sha256"],
            "workdir": str(request.workdir.resolve()),
            "environment_value_hashes": {key: canonical_hash({"value": value}) for key, value in sorted(request.environment.items())},
            "timeout_seconds": request.timeout_seconds,
            "heartbeat_seconds": request.heartbeat_seconds,
            "max_memory_bytes": request.max_memory_bytes,
            "max_cpu_seconds": request.max_cpu_seconds,
            "tool_id": request.tool_id,
            "admission_receipt_hash": request.admission_receipt_hash,
        }
        request_hash = canonical_hash(prepared_request)
        authorization = self._authority.authorize_execute_once(workspace_id=self._policy.workspace_id, tool_id=request.tool_id, prepared_action_id=request.prepared_action_id, approval_id=request.approval_id, request_hash=request_hash)
        _verify_authorization(authorization, trust=self._trust, request_hash=request_hash, tool_id=request.tool_id, prepared_action_id=request.prepared_action_id, approval_id=request.approval_id)
        if output_dir.exists() and output_dir.is_symlink():
            raise ResearchError("research.unsafe_output_dir", "executor output directory cannot be a symlink")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_dir = output_dir.resolve()
        if output_dir == request.workdir or request.workdir not in output_dir.parents:
            raise ResearchError("research.unsafe_output_dir", "executor output directory must be a dedicated child of workdir")
        stdout_path = output_dir / "stdout.log"
        stderr_path = output_dir / "stderr.log"
        if any(path.exists() and (path.is_symlink() or not path.is_file()) for path in (stdout_path, stderr_path)):
            raise ResearchError("research.unsafe_output_path", "executor log paths must be regular files")
        started = time.monotonic()

        def configure_child() -> None:
            os.setsid()
            try:
                import resource

                if request.max_memory_bytes is not None:
                    resource.setrlimit(resource.RLIMIT_AS, (request.max_memory_bytes, request.max_memory_bytes))
                if request.max_cpu_seconds is not None:
                    resource.setrlimit(resource.RLIMIT_CPU, (request.max_cpu_seconds, request.max_cpu_seconds))
            except (ImportError, OSError, ValueError):
                if request.max_memory_bytes is not None or request.max_cpu_seconds is not None:
                    os._exit(126)

        with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
            process = subprocess.Popen(
                request.argv,
                cwd=request.workdir,
                env={
                    **{key: os.environ[key] for key in ("PATH", "LANG", "LC_ALL", "TMPDIR", "SYSTEMROOT") if key in os.environ},
                    **dict(request.environment),
                },
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=False,
                preexec_fn=configure_child if os.name == "posix" else None,
                close_fds=True,
            )
            pid_receipt = {"attempt_id": request.attempt_id, "pid": process.pid, "started_monotonic_ms": int(started * 1000), "argv_hash": canonical_hash(list(request.argv))}
            heartbeat({**pid_receipt, "elapsed_ms": 0, "state": "running"})
            last_heartbeat = 0.0
            terminal = "failed"
            while process.poll() is None:
                elapsed = time.monotonic() - started
                if cancelled():
                    self._terminate_group(process)
                    terminal = "cancelled"
                    break
                if elapsed >= request.timeout_seconds:
                    self._terminate_group(process)
                    terminal = "timed_out"
                    break
                if elapsed - last_heartbeat >= request.heartbeat_seconds:
                    heartbeat({**pid_receipt, "elapsed_ms": int(elapsed * 1000), "state": "running"})
                    last_heartbeat = elapsed
                time.sleep(min(0.1, request.heartbeat_seconds))
            return_code = process.wait(timeout=5)
            if terminal == "failed":
                terminal = "completed" if return_code == 0 else "failed"
        self._policy.redact_file(stdout_path)
        self._policy.redact_file(stderr_path)
        receipt = {
            **pid_receipt,
            "executor": "local",
            "operation": "cancel" if terminal == "cancelled" else "collect",
            "state": terminal,
            "return_code": return_code,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "stdout": {"path": stdout_path.name, "sha256": _sha256_file(stdout_path), "size_bytes": stdout_path.stat().st_size},
            "stderr": {"path": stderr_path.name, "sha256": _sha256_file(stderr_path), "size_bytes": stderr_path.stat().st_size},
            "authorization_receipt_hash": authorization["receipt_hash"],
            "admission_receipt_hash": request.admission_receipt_hash,
            "request_hash": request_hash,
            "policy_snapshot_hash": canonical_hash(policy_snapshot),
        }
        return {**receipt, "receipt_hash": canonical_hash(receipt)}

    @staticmethod
    def _terminate_group(process: subprocess.Popen[bytes]) -> None:
        try:
            if os.name == "posix":
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            else:
                process.terminate()
            process.wait(timeout=3)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            if process.poll() is None:
                if os.name == "posix":
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
        except PermissionError as exc:
            raise ResearchError("research.process_cancel_denied", "process group could not be cancelled") from exc

    @staticmethod
    def adopt(*, attempt_id: str, pid: int, expected_argv_hash: str, observed_argv: Sequence[str], expected_executable_sha256: str, observed_executable: Path, expected_process_start_identity: str, observed_process_start_identity: str) -> Mapping[str, Any]:
        require_sha256(expected_argv_hash, "expected_argv_hash")
        require_sha256(expected_executable_sha256, "expected_executable_sha256")
        alive = pid > 1
        if alive:
            try:
                os.kill(pid, 0)
            except OSError:
                alive = False
        observed_hash = canonical_hash(list(_safe_argv(observed_argv)))
        observed_executable_sha256 = _sha256_file(observed_executable.resolve(strict=True))
        adopted = alive and observed_hash == expected_argv_hash and observed_executable_sha256 == expected_executable_sha256 and bool(expected_process_start_identity) and expected_process_start_identity == observed_process_start_identity
        receipt = {"attempt_id": attempt_id, "pid": pid, "state": "running" if adopted else "remote_unknown", "expected_argv_hash": expected_argv_hash, "observed_argv_hash": observed_hash, "observed_executable_sha256": observed_executable_sha256, "process_start_identity": observed_process_start_identity, "adopted": adopted}
        return {**receipt, "receipt_hash": canonical_hash(receipt)}


class CommandRunner(Protocol):
    def run(self, argv: Sequence[str], *, timeout_seconds: float, stdin_bytes: bytes | None = None, environment: Mapping[str, str] | None = None) -> Mapping[str, Any]: ...


@dataclass(frozen=True, slots=True)
class SSHComputeTarget:
    target_id: str
    host: str
    user: str
    remote_root: str
    host_key_file: str
    secret_ref: str
    port: int = 22
    wrapper: str = "research-lab-wrapper"
    allow_private_network: bool = False
    target_registration_receipt_hash: str = ""
    target_registration_receipt: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        for field, value in (("host", self.host), ("user", self.user), ("wrapper", self.wrapper)):
            if not _SAFE_ATOM.fullmatch(value):
                raise ResearchError("research.invalid_ssh_target", f"{field} contains unsafe characters")
        if not _SAFE_REMOTE_PATH.fullmatch(self.remote_root) or ".." in PurePosixPath(self.remote_root).parts:
            raise ResearchError("research.invalid_ssh_target", "remote_root must be an absolute safe path")
        if not self.host_key_file or "\n" in self.host_key_file or "\x00" in self.host_key_file:
            raise ResearchError("research.invalid_ssh_target", "host_key_file reference is required")
        if not Path(self.host_key_file).is_absolute() or any(character.isspace() for character in self.host_key_file):
            raise ResearchError("research.invalid_ssh_target", "host_key_file must be an absolute whitespace-free reference")
        if not _SECRET_REF.fullmatch(self.secret_ref):
            raise ResearchError("research.invalid_secret_ref", "SSH credentials must be a governed secret reference")
        if not 1 <= self.port <= 65535:
            raise ResearchError("research.invalid_ssh_target", "SSH port is invalid")
        if self.allow_private_network:
            require_sha256(self.target_registration_receipt_hash, "target_registration_receipt_hash")

    def public_snapshot(self) -> Mapping[str, Any]:
        return {"target_id": self.target_id, "host": self.host, "user": self.user, "remote_root": self.remote_root, "port": self.port, "wrapper": self.wrapper, "host_key_file_configured": True, "secret_ref_scheme": self.secret_ref.split(":", 1)[0], "allow_private_network": self.allow_private_network, "target_registration_receipt_hash": self.target_registration_receipt_hash or None}

    def registration_snapshot(self) -> Mapping[str, Any]:
        return {key: value for key, value in self.public_snapshot().items() if key != "target_registration_receipt_hash"}


class SSHExecutor:
    def __init__(self, runner: CommandRunner, *, secret_resolver: SecretResolver, authority: ExecutionAuthorityPort, trust: CoreTrustStore, workspace_id: str, dns_resolver: Callable[[str, int], Sequence[str]] | None = None) -> None:
        self._runner = runner
        self._secret_resolver = secret_resolver
        self._authority = authority
        self._trust = trust
        self._workspace_id = workspace_id
        self._dns_resolver = dns_resolver or self._resolve_addresses

    @staticmethod
    def _resolve_addresses(host: str, port: int) -> tuple[str, ...]:
        try:
            return tuple(sorted({item[4][0] for item in socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)}))
        except socket.gaierror as exc:
            raise ResearchError("research.ssh_dns_unverified", "SSH hostname could not be resolved") from exc

    def _validate_addresses(self, target: SSHComputeTarget, addresses: Sequence[str]) -> tuple[str, ...]:
        import ipaddress
        if not addresses:
            raise ResearchError("research.ssh_dns_unverified", "SSH target requires DNS resolution evidence")
        normalized = []
        private = False
        for raw in addresses:
            try:
                address = ipaddress.ip_address(raw)
            except ValueError as exc:
                raise ResearchError("research.ssh_dns_invalid", "SSH resolver returned an invalid address") from exc
            blocked = address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or address.is_reserved
            private = private or blocked
            normalized.append(str(address))
        if private:
            if not target.allow_private_network or not target.target_registration_receipt:
                raise ResearchError("research.ssh_private_target_denied", "private SSH targets require an exact governed target registration receipt")
            verified = require_core_receipt(target.target_registration_receipt, trust=self._trust, purpose="research.ssh-target-registration/v1", bindings={"target_snapshot_hash": canonical_hash(target.registration_snapshot()), "decision": "allow", "workspace_id": self._workspace_id})
            if verified["receipt_hash"] != target.target_registration_receipt_hash:
                raise ResearchError("research.ssh_private_target_denied", "private SSH target registration hash mismatched")
        return tuple(sorted(set(normalized)))

    @staticmethod
    def _base(target: SSHComputeTarget, resolved_address: str) -> tuple[str, ...]:
        return ("ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"HostKeyAlias={target.host}", "-o", f"UserKnownHostsFile={target.host_key_file}", "-p", str(target.port), f"{target.user}@{resolved_address}", "--", target.wrapper)

    def action(self, *, target: SSHComputeTarget, operation: str, attempt_id: str, admission_receipt_hash: str, payload: Mapping[str, Any] | None = None, timeout_seconds: float = 30, prepared_action_id: str, approval_id: str) -> Mapping[str, Any]:
        if operation not in {"submit", "status", "logs", "cancel", "reconcile", "collect", "resume"}:
            raise ResearchError("research.invalid_ssh_operation", "SSH wrapper operation is not allowlisted")
        require_sha256(admission_receipt_hash, "admission_receipt_hash")
        resolved_addresses = self._validate_addresses(target, self._dns_resolver(target.host, target.port))
        selected_address = resolved_addresses[0]
        request = {"attempt_id": attempt_id, "remote_root": target.remote_root, "operation": operation, "payload": dict(payload or {}), "admission_receipt_hash": admission_receipt_hash, "target_snapshot_hash": canonical_hash(target.public_snapshot()), "resolved_addresses": list(resolved_addresses), "selected_address": selected_address, "timeout_seconds": timeout_seconds}
        request_hash = canonical_hash(request)
        authorization = self._authority.authorize_execute_once(workspace_id=self._workspace_id, tool_id="research_lab.tool.ssh_execute", prepared_action_id=prepared_action_id, approval_id=approval_id, request_hash=request_hash)
        _verify_authorization(authorization, trust=self._trust, request_hash=request_hash, tool_id="research_lab.tool.ssh_execute", prepared_action_id=prepared_action_id, approval_id=approval_id)
        wire_request = {**request, "authorization_receipt_hash": authorization["receipt_hash"], "core_authorization": dict(authorization)}
        encoded = json.dumps(wire_request, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
        wire_request_hash = canonical_hash(wire_request)
        secret_env = dict(self._secret_resolver.resolve_for_process(secret_ref=target.secret_ref, target_id=target.target_id))
        if not secret_env or any(not isinstance(k, str) or not isinstance(v, str) or _DANGEROUS_ENV.search(k) for k, v in secret_env.items()):
            raise ResearchError("research.secret_resolution_invalid", "secret resolver returned an unsafe process environment")
        if set(secret_env) - {"SSH_AUTH_SOCK"} or not str(secret_env.get("SSH_AUTH_SOCK", "")).startswith("/"):
            raise ResearchError("research.secret_resolution_invalid", "SSH secrets must remain in an agent/socket reference, never plaintext environment variables")
        result = self._runner.run((*self._base(target, selected_address), operation, "--request-stdin"), timeout_seconds=timeout_seconds, stdin_bytes=encoded, environment=secret_env)
        if result.get("available") is False:
            receipt = {"executor": "ssh", "attempt_id": attempt_id, "state": "unavailable", "target": target.public_snapshot(), "resolved_addresses": list(resolved_addresses), "operation": operation, "request_hash": request_hash, "authorization_receipt_hash": authorization["receipt_hash"], "admission_receipt_hash": admission_receipt_hash, "reason_code": result.get("reason_code", "ssh_unavailable")}
            return {**receipt, "receipt_hash": canonical_hash(receipt)}
        if not isinstance(result.get("remote_receipt"), Mapping):
            raise ResearchError("research.ssh_receipt_invalid", "remote wrapper did not return a structured receipt")
        remote = dict(result["remote_receipt"])
        if remote.get("attempt_id") != attempt_id or remote.get("operation") != operation or remote.get("request_hash") != wire_request_hash or remote.get("authorization_receipt_hash") != authorization["receipt_hash"] or remote.get("target_snapshot_hash") != request["target_snapshot_hash"]:
            raise ResearchError("research.ssh_receipt_invalid", "remote receipt does not match requested action")
        remote_hash = str(remote.pop("receipt_hash", ""))
        if not re.fullmatch(r"[0-9a-f]{64}", remote_hash) or remote_hash != canonical_hash(remote) or operation in {"collect", "logs"} and (not remote.get("artifact_id") or not re.fullmatch(r"[0-9a-f]{64}", str(remote.get("artifact_sha256") or ""))):
            raise ResearchError("research.ssh_receipt_invalid", "remote receipt or transferred Artifact integrity is missing")
        remote = dict(_redact_literals(remote, tuple(secret_env.values())))
        remote["upstream_receipt_hash"] = remote_hash
        receipt = {"executor": "ssh", "attempt_id": attempt_id, "state": remote.get("state"), "admission_receipt_hash": admission_receipt_hash, "target_snapshot_hash": canonical_hash(target.public_snapshot()), "resolved_addresses": list(resolved_addresses), "operation": operation, "remote_receipt": remote, "log_cursor": remote.get("log_cursor"), "remote_pid": remote.get("pid"), "scheduler_job_id": remote.get("job_id"), "authorization_receipt_hash": authorization["receipt_hash"], "request_hash": request_hash}
        return {**receipt, "receipt_hash": canonical_hash(receipt)}


@dataclass(frozen=True, slots=True)
class SlurmRequest:
    attempt_id: str
    script_path: str
    partition: str
    gpus: int
    cpus: int
    memory_mib: int
    time_limit: str
    array: str | None = None

    def __post_init__(self) -> None:
        for value in (self.attempt_id, self.script_path, self.partition, self.time_limit):
            if not _SAFE_ATOM.fullmatch(value) or ".." in value:
                raise ResearchError("research.invalid_slurm_request", "Slurm request contains unsafe values")
        if min(self.gpus, self.cpus, self.memory_mib) < 0 or self.cpus < 1 or self.memory_mib < 1:
            raise ResearchError("research.invalid_slurm_request", "Slurm resources are invalid")
        if self.array is not None and not re.fullmatch(r"\d+(?:-\d+)?(?:%\d+)?", self.array):
            raise ResearchError("research.invalid_slurm_request", "Slurm array expression is invalid")


class SlurmExecutor:
    def __init__(self, runner: CommandRunner, *, authority: ExecutionAuthorityPort, trust: CoreTrustStore, workspace_id: str, redaction_values: Sequence[str] = ()) -> None:
        self._runner = runner
        self._authority = authority
        self._trust = trust
        self._workspace_id = workspace_id
        self._redaction_values = tuple(redaction_values)

    def _authorize(self, *, operation: str, request: Mapping[str, Any], prepared_action_id: str, approval_id: str) -> Mapping[str, Any]:
        request_hash = canonical_hash({"operation": operation, **dict(request)})
        receipt = self._authority.authorize_execute_once(workspace_id=self._workspace_id, tool_id="research_lab.tool.slurm_execute", prepared_action_id=prepared_action_id, approval_id=approval_id, request_hash=request_hash)
        return _verify_authorization(receipt, trust=self._trust, request_hash=request_hash, tool_id="research_lab.tool.slurm_execute", prepared_action_id=prepared_action_id, approval_id=approval_id)

    def submit(self, request: SlurmRequest, *, prepared_action_id: str, approval_id: str) -> Mapping[str, Any]:
        authorization = self._authorize(operation="submit", request={field: getattr(request, field) for field in request.__dataclass_fields__}, prepared_action_id=prepared_action_id, approval_id=approval_id)
        argv = ["sbatch", "--parsable", "--export", "NONE", "--job-name", request.attempt_id, "--partition", request.partition, "--cpus-per-task", str(request.cpus), "--mem", str(request.memory_mib), "--time", request.time_limit]
        if request.gpus:
            argv.extend(("--gpus", str(request.gpus)))
        if request.array:
            argv.extend(("--array", request.array))
        argv.append(request.script_path)
        result = self._runner.run(tuple(argv), timeout_seconds=30)
        if result.get("available") is False:
            receipt = {"executor": "slurm", "state": "unavailable", "reason_code": result.get("reason_code", "slurm_unavailable")}
            return {**receipt, "receipt_hash": canonical_hash(receipt)}
        job_id = str(result.get("stdout", "")).strip().split(";", 1)[0]
        if not re.fullmatch(r"\d+", job_id):
            raise ResearchError("research.slurm_receipt_invalid", "sbatch did not return a scheduler job id")
        resource_request = {field: getattr(request, field) for field in request.__dataclass_fields__}
        receipt = {"executor": "slurm", "operation": "submit", "state": "submitted", "attempt_id": request.attempt_id, "scheduler_job_id": job_id, "resource_request_hash": canonical_hash(resource_request), "request_hash": authorization["request_hash"], "authorization_receipt_hash": authorization["receipt_hash"]}
        return {**receipt, "receipt_hash": canonical_hash(receipt)}

    def status(self, job_id: str, *, prepared_action_id: str, approval_id: str) -> Mapping[str, Any]:
        if not re.fullmatch(r"\d+(?:_\d+)?", job_id):
            raise ResearchError("research.invalid_slurm_job", "scheduler job id is invalid")
        authorization = self._authorize(operation="status", request={"scheduler_job_id": job_id}, prepared_action_id=prepared_action_id, approval_id=approval_id)
        result = self._runner.run(("sacct", "-n", "-P", "-j", job_id, "--format=JobIDRaw,State,ExitCode,Elapsed"), timeout_seconds=30)
        if result.get("available") is False:
            receipt = {"executor": "slurm", "operation": "status", "scheduler_job_id": job_id, "state": "unavailable", "authorization_receipt_hash": authorization["receipt_hash"], "request_hash": authorization["request_hash"]}
            return {**receipt, "receipt_hash": canonical_hash(receipt)}
        if result.get("return_code", 0) != 0:
            raise ResearchError("research.slurm_status_unconfirmed", "Slurm status command failed")
        rows = []
        for raw in str(result.get("stdout", "")).splitlines():
            fields = raw.strip().split("|")
            allowed_states = {"PENDING", "CONFIGURING", "RUNNING", "COMPLETING", "COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "PREEMPTED", "NODE_FAIL", "OUT_OF_MEMORY", "BOOT_FAIL", "DEADLINE"}
            normalized_state = fields[1].removesuffix("+") if len(fields) == 4 else ""
            if len(fields) != 4 or not re.fullmatch(r"\d+(?:_\d+)?", fields[0]) or normalized_state not in allowed_states or not re.fullmatch(r"\d+:\d+", fields[2]):
                raise ResearchError("research.slurm_status_unconfirmed", "Slurm status output is not the exact structured schema")
            if fields[0] == job_id:
                rows.append({"job_id": fields[0], "state": normalized_state, "exit_code": fields[2], "elapsed": fields[3]})
        if len(rows) != 1:
            raise ResearchError("research.slurm_status_unconfirmed", "Slurm status must contain exactly one requested job row")
        receipt = {"executor": "slurm", "operation": "status", "scheduler_job_id": job_id, "available": True, "scheduler_state": rows[0]["state"], "exit_code": rows[0]["exit_code"], "elapsed": rows[0]["elapsed"], "authorization_receipt_hash": authorization["receipt_hash"], "request_hash": authorization["request_hash"]}
        return {**receipt, "receipt_hash": canonical_hash(receipt)}

    def cancel(self, job_id: str, *, prepared_action_id: str, approval_id: str) -> Mapping[str, Any]:
        if not re.fullmatch(r"\d+(?:_\d+)?", job_id):
            raise ResearchError("research.invalid_slurm_job", "scheduler job id is invalid")
        authorization = self._authorize(operation="cancel", request={"scheduler_job_id": job_id}, prepared_action_id=prepared_action_id, approval_id=approval_id)
        result = self._runner.run(("scancel", job_id), timeout_seconds=30)
        if result.get("available") is False or result.get("return_code") != 0:
            raise ResearchError("research.slurm_cancel_unconfirmed", "Slurm cancellation did not complete successfully")
        observed = self._runner.run(("sacct", "-n", "-P", "-j", job_id, "--format=JobIDRaw,State,ExitCode,Elapsed"), timeout_seconds=30)
        rows = [line.strip().split("|") for line in str(observed.get("stdout", "")).splitlines() if line.strip()]
        exact = [row for row in rows if len(row) == 4 and row[0] == job_id]
        if observed.get("return_code", 0) != 0 or len(exact) != 1 or exact[0][1].removesuffix("+") not in {"CANCELLED", "COMPLETED", "FAILED", "TIMEOUT", "PREEMPTED"}:
            raise ResearchError("research.slurm_cancel_unconfirmed", "Slurm cancellation terminal readback did not confirm")
        receipt = {"executor": "slurm", "operation": "cancel", "scheduler_job_id": job_id, "return_code": result.get("return_code"), "scheduler_state": exact[0][1].removesuffix("+"), "exit_code": exact[0][2], "authorization_receipt_hash": authorization["receipt_hash"], "request_hash": authorization["request_hash"]}
        return {**receipt, "receipt_hash": canonical_hash(receipt)}

    def logs(self, job_id: str, *, output_path: str, prepared_action_id: str, approval_id: str) -> Mapping[str, Any]:
        if not re.fullmatch(r"\d+(?:_\d+)?", job_id) or not _SAFE_ATOM.fullmatch(output_path) or ".." in output_path:
            raise ResearchError("research.invalid_slurm_job", "scheduler job or log path is invalid")
        authorization = self._authorize(operation="logs", request={"scheduler_job_id": job_id, "output_path": output_path}, prepared_action_id=prepared_action_id, approval_id=approval_id)
        result = self._runner.run(("tail", "-n", "2000", "--", output_path), timeout_seconds=30)
        if result.get("available") is False or result.get("return_code", 0) != 0:
            raise ResearchError("research.slurm_logs_unconfirmed", "Slurm log read failed")
        receipt = {"executor": "slurm", "operation": "logs", "scheduler_job_id": job_id, "available": result.get("available", True), "log_text": _redact_literals(str(result.get("stdout", ""))[:131072], self._redaction_values), "log_cursor": result.get("cursor"), "authorization_receipt_hash": authorization["receipt_hash"]}
        return {**receipt, "receipt_hash": canonical_hash(receipt)}

    def reconcile(self, job_id: str, *, prepared_action_id: str, approval_id: str) -> Mapping[str, Any]:
        status = self.status(job_id, prepared_action_id=prepared_action_id, approval_id=approval_id)
        if status.get("state") == "unavailable":
            result = {"executor": "slurm", "operation": "reconcile", "scheduler_job_id": job_id, "state": "remote_unknown", "status_receipt_hash": status["receipt_hash"], "authorization_receipt_hash": status["authorization_receipt_hash"]}
            return {**result, "receipt_hash": canonical_hash(result)}
        state_text = str(status.get("scheduler_state", ""))
        if state_text == "PREEMPTED":
            state = "preempted"
        elif state_text in {"RUNNING", "PENDING", "CONFIGURING", "COMPLETING"}:
            state = "running"
        elif state_text == "COMPLETED" and status.get("exit_code") == "0:0":
            state = "completed"
        elif state_text:
            state = "failed"
        else:
            state = "remote_unknown"
        result = {"executor": "slurm", "operation": "reconcile", "scheduler_job_id": job_id, "state": state, "status_receipt_hash": status["receipt_hash"]}
        return {**result, "receipt_hash": canonical_hash(result)}

    def resume(self, request: SlurmRequest, *, checkpoint_path: str, checkpoint_sha256: str, prepared_action_id: str, approval_id: str) -> Mapping[str, Any]:
        if not _SAFE_ATOM.fullmatch(checkpoint_path) or ".." in checkpoint_path:
            raise ResearchError("research.checkpoint_invalid", "Slurm checkpoint path is unsafe")
        require_sha256(checkpoint_sha256, "checkpoint_sha256")
        resumed = SlurmRequest(attempt_id=request.attempt_id, script_path=request.script_path, partition=request.partition, gpus=request.gpus, cpus=request.cpus, memory_mib=request.memory_mib, time_limit=request.time_limit, array=request.array)
        resource_request = {field: getattr(request, field) for field in request.__dataclass_fields__}
        authorization = self._authorize(operation="resume", request={**resource_request, "checkpoint_path": checkpoint_path, "checkpoint_sha256": checkpoint_sha256}, prepared_action_id=prepared_action_id, approval_id=approval_id)
        argv = ["sbatch", "--parsable", "--export", "NONE", "--job-name", request.attempt_id, "--partition", request.partition, "--cpus-per-task", str(request.cpus), "--mem", str(request.memory_mib), "--time", request.time_limit]
        if request.gpus:
            argv.extend(("--gpus", str(request.gpus)))
        if request.array:
            argv.extend(("--array", request.array))
        argv.extend((request.script_path, "--resume", checkpoint_path, "--checkpoint-sha256", checkpoint_sha256))
        result = self._runner.run(tuple(argv), timeout_seconds=30)
        if result.get("available") is False:
            receipt = {"executor": "slurm", "operation": "resume", "state": "unavailable", "reason_code": result.get("reason_code", "slurm_unavailable"), "authorization_receipt_hash": authorization["receipt_hash"]}
            return {**receipt, "receipt_hash": canonical_hash(receipt)}
        job_id = str(result.get("stdout", "")).strip().split(";", 1)[0]
        if not re.fullmatch(r"\d+", job_id):
            raise ResearchError("research.slurm_receipt_invalid", "resume did not return a scheduler job id")
        receipt = {"executor": "slurm", "operation": "resume", "state": "submitted", "attempt_id": resumed.attempt_id, "scheduler_job_id": job_id, "checkpoint_sha256": checkpoint_sha256, "resource_request_hash": canonical_hash(resource_request), "request_hash": authorization["request_hash"], "authorization_receipt_hash": authorization["receipt_hash"]}
        return {**receipt, "receipt_hash": canonical_hash(receipt)}
