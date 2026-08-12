from __future__ import annotations

import sys
import os
import tempfile
import unittest
from pathlib import Path

from templates.research_lab.contracts import ResearchError
from templates.research_lab.contracts import canonical_hash
from templates.research_lab.executors import ExecutionPolicy, ExecutionRequest, LocalProcessExecutor, SSHComputeTarget, SSHExecutor, SlurmExecutor, SlurmRequest
from .support import TEST_TRUST, signed


class FakeRunner:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, argv, *, timeout_seconds, stdin_bytes=None, environment=None):
        self.calls.append(tuple(argv))
        self.stdin_bytes = stdin_bytes
        self.environment = environment
        result = dict(self.result)
        if isinstance(result.get("remote_receipt"), dict) and len(result["remote_receipt"]) > 3 and stdin_bytes:
            import json
            request = json.loads(stdin_bytes)
            remote = {**result["remote_receipt"], "request_hash": canonical_hash(request), "authorization_receipt_hash": request["authorization_receipt_hash"], "target_snapshot_hash": request["target_snapshot_hash"]}
            remote.pop("receipt_hash", None)
            result["remote_receipt"] = {**remote, "receipt_hash": canonical_hash(remote)}
        return result


class FakeAuthority:
    def authorize_execute_once(self, *, workspace_id, tool_id, prepared_action_id, approval_id, request_hash):
        if not prepared_action_id or not approval_id:
            return {"decision": "deny", "executed_once": False}
        value = {"decision": "allow", "executed_once": True, "request_hash": request_hash, "tool_id": tool_id, "prepared_action_id": prepared_action_id, "approval_id": approval_id}
        return signed(value, "research.execution-authorization/v1")


class FakeSecretResolver:
    def resolve_for_process(self, *, secret_ref, target_id):
        return {"SSH_AUTH_SOCK": "/tmp/agent.sock"}


def remote_receipt(**value):
    return {**value, "receipt_hash": canonical_hash(value)}


def local_executor(root: Path, *, untrusted_code: bool = False, redaction_values=()):
    policy = ExecutionPolicy("ws_1", root, (Path(sys.executable).name,), ("research_lab.tool.local_execute",), untrusted_code, tuple(redaction_values))
    return LocalProcessExecutor(FakeAuthority(), policy, TEST_TRUST)

def ssh_executor(runner, resolver=None):
    return SSHExecutor(runner, secret_resolver=resolver or FakeSecretResolver(), authority=FakeAuthority(), trust=TEST_TRUST, workspace_id="ws_1", dns_resolver=lambda host, port: ("8.8.8.8",))


def request(root: Path, argv, **changes):
    values = {"attempt_id": "att_local", "argv": tuple(argv), "workdir": root, "environment": {}, "timeout_seconds": 5, "heartbeat_seconds": 0.01, "prepared_action_id": "pa_1", "approval_id": "apr_1"}
    values.update(changes)
    return ExecutionRequest(**values)


class ExecutorSecurityTests(unittest.TestCase):
    def test_local_executor_captures_logs_heartbeat_and_receipt(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            execution = request(root, (sys.executable, "-c", "print('ok')"))
            heartbeats = []
            receipt = local_executor(root).run(execution, output_dir=root / "out", heartbeat=heartbeats.append)
            self.assertEqual(receipt["state"], "completed")
            self.assertEqual(len(receipt["receipt_hash"]), 64)
            self.assertEqual((root / "out/stdout.log").read_text().strip(), "ok")
            self.assertTrue(heartbeats)

    def test_local_executor_rejects_inline_secret(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            with self.assertRaisesRegex(ResearchError, "inline secret"):
                request(Path(raw).resolve(), (sys.executable, "train.py", "--api-key=value"))

    def test_local_executor_rejects_symlink_log_target(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            target = root / "outside.log"
            target.write_text("retain")
            output = root / "out"
            output.mkdir()
            (output / "stdout.log").symlink_to(target)
            execution = request(root, (sys.executable, "-c", "print('overwrite')"))
            with self.assertRaisesRegex(ResearchError, "log paths"):
                local_executor(root).run(execution, output_dir=output, heartbeat=lambda _: None)
            self.assertEqual(target.read_text(), "retain")

    def test_local_executor_does_not_inherit_parent_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            os.environ["TEST_PRIVATE_TOKEN"] = "must-not-cross-boundary"
            try:
                execution = request(root, (sys.executable, "-c", "import os; print(os.getenv('TEST_PRIVATE_TOKEN', 'OMITTED'))"))
                receipt = local_executor(root).run(execution, output_dir=root / "out", heartbeat=lambda _: None)
                self.assertEqual(receipt["state"], "completed")
                self.assertEqual((root / "out/stdout.log").read_text().strip(), "OMITTED")
            finally:
                os.environ.pop("TEST_PRIVATE_TOKEN", None)

    def test_ssh_executor_uses_strict_argv_and_validates_receipt(self) -> None:
        runner = FakeRunner({"remote_receipt": remote_receipt(attempt_id="att_1", operation="submit", pid=42, log_cursor="0")})
        target = SSHComputeTarget("cmp_1", "gpu.example.org", "worker", "/srv/research", "/tmp/known_hosts", "vault://ssh/gpu")
        receipt = ssh_executor(runner).action(target=target, operation="submit", attempt_id="att_1", admission_receipt_hash="c" * 64, prepared_action_id="pa_1", approval_id="apr_1")
        self.assertEqual(receipt["remote_pid"], 42)
        self.assertIn("StrictHostKeyChecking=yes", runner.calls[0])
        self.assertNotIn("vault://ssh/gpu", runner.calls[0])
        self.assertEqual(runner.calls[0][-1], "--request-stdin")
        self.assertIn(b'"attempt_id":"att_1"', runner.stdin_bytes)

    def test_ssh_injection_and_plaintext_credentials_rejected(self) -> None:
        for changes in ({"host": "host;touch /tmp/x"}, {"secret_ref": "plaintext-password"}, {"remote_root": "/srv/../root"}):
            values = {"target_id": "cmp_1", "host": "gpu.example.org", "user": "worker", "remote_root": "/srv/research", "host_key_file": "/tmp/known_hosts", "secret_ref": "vault://ssh/gpu"}
            values.update(changes)
            with self.subTest(changes=changes), self.assertRaises(ResearchError):
                SSHComputeTarget(**values)

    def test_ssh_unavailable_is_truthful_not_success(self) -> None:
        runner = FakeRunner({"available": False, "reason_code": "network_unavailable"})
        target = SSHComputeTarget("cmp_1", "gpu.example.org", "worker", "/srv/research", "/tmp/known_hosts", "vault://ssh/gpu")
        receipt = ssh_executor(runner).action(target=target, operation="status", attempt_id="att_1", admission_receipt_hash="c" * 64, prepared_action_id="pa_1", approval_id="apr_1")
        self.assertEqual(receipt["state"], "unavailable")

    def test_slurm_submit_status_cancel_and_injection_guard(self) -> None:
        runner = FakeRunner({"stdout": "12345;cluster", "return_code": 0})
        executor = SlurmExecutor(runner, authority=FakeAuthority(), trust=TEST_TRUST, workspace_id="ws_1")
        receipt = executor.submit(SlurmRequest("att_1", "train.sh", "gpu", 1, 4, 8192, "02:00:00", "0-3%2"), prepared_action_id="pa_1", approval_id="apr_1")
        self.assertEqual(receipt["scheduler_job_id"], "12345")
        runner.result = {"stdout": "12345|CANCELLED|0:15|00:10:00", "return_code": 0}
        self.assertEqual(executor.cancel("12345", prepared_action_id="pa_2", approval_id="apr_2")["operation"], "cancel")
        runner.result = {"stdout": "12345|PREEMPTED|0:0|00:10:00"}
        self.assertEqual(executor.reconcile("12345", prepared_action_id="pa_status", approval_id="apr_status")["state"], "preempted")
        runner.result = {"stdout": "log", "cursor": "2000", "return_code": 0}
        self.assertEqual(executor.logs("12345", output_path="slurm-12345.out", prepared_action_id="pa_logs", approval_id="apr_logs")["log_cursor"], "2000")
        with self.assertRaises(ResearchError):
            SlurmRequest("att_1", "train.sh;id", "gpu", 1, 4, 8192, "02:00:00")

    def test_local_executor_rejects_shell_dynamic_env_and_workspace_escape(self) -> None:
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as outside:
            root = Path(raw).resolve()
            with self.assertRaisesRegex(ResearchError, "shell trampoline"):
                LocalProcessExecutor(FakeAuthority(), ExecutionPolicy("ws_1", root, ("sh",), ("research_lab.tool.local_execute",), False), TEST_TRUST).run(request(root, ("/bin/sh", "-c", "id")), output_dir=root / "out", heartbeat=lambda _: None)
            with self.assertRaisesRegex(ResearchError, "environment overrides"):
                request(root, (sys.executable, "train.py"), environment={"LD_PRELOAD": "/tmp/inject.so"})
            with self.assertRaisesRegex(ResearchError, "escapes"):
                local_executor(root).run(request(Path(outside).resolve(), (sys.executable, "train.py")), output_dir=Path(outside) / "out", heartbeat=lambda _: None)

    def test_local_executor_redacts_configured_output_literals(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            execution = request(root, (sys.executable, "-c", "print('TOP_SECRET_123')"))
            local_executor(root, redaction_values=("TOP_SECRET_123",)).run(execution, output_dir=root / "out", heartbeat=lambda _: None)
            self.assertEqual((root / "out/stdout.log").read_text().strip(), "[REDACTED]")

    def test_restart_adoption_binds_observed_argv(self) -> None:
        expected = canonical_hash([sys.executable, "train.py"])
        from templates.research_lab.executors import _sha256_file
        executable_hash = _sha256_file(Path(sys.executable).resolve())
        common = {"attempt_id": "att_1", "pid": os.getpid(), "expected_argv_hash": expected, "expected_executable_sha256": executable_hash, "observed_executable": Path(sys.executable), "expected_process_start_identity": "start-1", "observed_process_start_identity": "start-1"}
        mismatch = LocalProcessExecutor.adopt(**common, observed_argv=(sys.executable, "other.py"))
        self.assertFalse(mismatch["adopted"])
        matched = LocalProcessExecutor.adopt(**common, observed_argv=(sys.executable, "train.py"))
        self.assertTrue(matched["adopted"])

    def test_slurm_resume_binds_checkpoint_and_approval(self) -> None:
        runner = FakeRunner({"stdout": "23456;cluster", "return_code": 0})
        executor = SlurmExecutor(runner, authority=FakeAuthority(), trust=TEST_TRUST, workspace_id="ws_1")
        receipt = executor.resume(SlurmRequest("att_1", "train.sh", "gpu", 1, 4, 8192, "02:00:00"), checkpoint_path="model.pt", checkpoint_sha256="a" * 64, prepared_action_id="pa_resume", approval_id="apr_resume")
        self.assertEqual(receipt["scheduler_job_id"], "23456")
        self.assertIn("NONE", runner.calls[-1])
        self.assertNotIn("ALL", runner.calls[-1])
        self.assertIn("--gpus", runner.calls[-1])
        self.assertIn("--checkpoint-sha256", runner.calls[-1])

    def test_remote_receipts_and_slurm_logs_redact_nested_literals(self) -> None:
        runner = FakeRunner({"remote_receipt": remote_receipt(attempt_id="att_1", operation="status", nested={"password": "literal"}, message="uses /tmp/agent.sock")})
        target = SSHComputeTarget("cmp_1", "gpu.example.org", "worker", "/srv/research", "/tmp/known_hosts", "vault://ssh/gpu")
        receipt = ssh_executor(runner).action(target=target, operation="status", attempt_id="att_1", admission_receipt_hash="c" * 64, prepared_action_id="pa_1", approval_id="apr_1")
        self.assertEqual(receipt["remote_receipt"]["nested"]["password"], "[REDACTED]")
        self.assertNotIn("/tmp/agent.sock", str(receipt))
        slurm_runner = FakeRunner({"stdout": "token=TOP_SECRET_123", "return_code": 0})
        logs = SlurmExecutor(slurm_runner, authority=FakeAuthority(), trust=TEST_TRUST, workspace_id="ws_1", redaction_values=("TOP_SECRET_123",)).logs("123", output_path="job.log", prepared_action_id="pa_logs", approval_id="apr_logs")
        self.assertNotIn("TOP_SECRET_123", logs["log_text"])

    def test_local_approval_hash_binds_values_limits_and_exact_executable(self) -> None:
        class RecordingAuthority(FakeAuthority):
            def __init__(self): self.hashes = []
            def authorize_execute_once(self, **kwargs):
                self.hashes.append(kwargs["request_hash"])
                return super().authorize_execute_once(**kwargs)
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as untrusted:
            root = Path(raw).resolve(); authority = RecordingAuthority()
            policy = ExecutionPolicy("ws_1", root, (Path(sys.executable).name,), ("research_lab.tool.local_execute",), False)
            executor = LocalProcessExecutor(authority, policy, TEST_TRUST)
            for index, changes in enumerate(({"environment": {"MODE": "one"}, "timeout_seconds": 5}, {"environment": {"MODE": "two"}, "timeout_seconds": 6, "max_memory_bytes": 128 * 1024 * 1024})):
                executor.run(request(root, (sys.executable, "-c", "print('ok')"), **changes), output_dir=root / f"out-{index}", heartbeat=lambda _: None)
            self.assertNotEqual(authority.hashes[0], authority.hashes[1])
            copied = Path(untrusted) / Path(sys.executable).name
            copied.write_bytes(Path(sys.executable).read_bytes()); copied.chmod(0o755)
            with self.assertRaisesRegex(ResearchError, "outside"):
                policy.validate(request(root, (str(copied), "train.py")))

    def test_ssh_rejects_plaintext_secret_environment_and_forged_receipt(self) -> None:
        class PlaintextResolver:
            def resolve_for_process(self, **kwargs): return {"SSH_PASSWORD": "literal"}
        target = SSHComputeTarget("cmp_1", "gpu.example.org", "worker", "/srv/research", "/tmp/known_hosts", "vault://ssh/gpu")
        with self.assertRaisesRegex(ResearchError, "never plaintext"):
            ssh_executor(FakeRunner({}), PlaintextResolver()).action(target=target, operation="status", attempt_id="att_1", admission_receipt_hash="c" * 64, prepared_action_id="pa", approval_id="apr")
        with self.assertRaisesRegex(ResearchError, "receipt"):
            ssh_executor(FakeRunner({"remote_receipt": {"attempt_id": "att_1", "operation": "status", "receipt_hash": "a" * 64}})).action(target=target, operation="status", attempt_id="att_1", admission_receipt_hash="c" * 64, prepared_action_id="pa", approval_id="apr")

    def test_local_symlink_escape_and_private_ssh_dns_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as trusted_raw, tempfile.TemporaryDirectory() as outside_raw:
            trusted, outside = Path(trusted_raw), Path(outside_raw)
            executable = outside / "python"
            executable.write_bytes(Path(sys.executable).read_bytes()); executable.chmod(0o755)
            link = trusted / "python"; link.symlink_to(executable)
            policy = ExecutionPolicy("ws_1", trusted, ("python",), ("research_lab.tool.local_execute",), False, trusted_executable_roots=(trusted,))
            with self.assertRaisesRegex(ResearchError, "outside"):
                policy.validate(request(trusted, (str(link), "train.py")))
        target = SSHComputeTarget("cmp_1", "gpu.internal", "worker", "/srv/research", "/tmp/known_hosts", "vault://ssh/gpu")
        with self.assertRaisesRegex(ResearchError, "private SSH"):
            SSHExecutor(FakeRunner({}), secret_resolver=FakeSecretResolver(), authority=FakeAuthority(), trust=TEST_TRUST, workspace_id="ws_1", dns_resolver=lambda host, port: ("127.0.0.1",)).action(target=target, operation="status", attempt_id="att_1", admission_receipt_hash="c" * 64, prepared_action_id="pa", approval_id="apr")

    def test_private_ssh_target_requires_exact_signed_registration(self) -> None:
        base = SSHComputeTarget("cmp_1", "gpu.internal", "worker", "/srv/research", "/tmp/known_hosts", "vault://ssh/gpu", allow_private_network=True, target_registration_receipt_hash="a" * 64)
        registration = signed({"target_snapshot_hash": canonical_hash(base.registration_snapshot()), "decision":"allow", "workspace_id":"ws_1"}, "research.ssh-target-registration/v1")
        target = SSHComputeTarget("cmp_1", "gpu.internal", "worker", "/srv/research", "/tmp/known_hosts", "vault://ssh/gpu", allow_private_network=True, target_registration_receipt_hash=registration["receipt_hash"], target_registration_receipt=registration)
        executor = SSHExecutor(FakeRunner({}), secret_resolver=FakeSecretResolver(), authority=FakeAuthority(), trust=TEST_TRUST, workspace_id="ws_1", dns_resolver=lambda host, port: ("10.0.0.8",))
        self.assertEqual(executor._validate_addresses(target, ("10.0.0.8",)), ("10.0.0.8",))
        forged = SSHComputeTarget("cmp_2", "gpu.internal", "worker", "/srv/research", "/tmp/known_hosts", "vault://ssh/gpu", allow_private_network=True, target_registration_receipt_hash=registration["receipt_hash"], target_registration_receipt=registration)
        with self.assertRaisesRegex(ResearchError, "bind target_snapshot_hash"):
            executor._validate_addresses(forged, ("10.0.0.8",))

    def test_slurm_submit_exports_none_and_cancel_failure_is_not_success(self) -> None:
        runner = FakeRunner({"stdout": "42", "return_code": 0})
        executor = SlurmExecutor(runner, authority=FakeAuthority(), trust=TEST_TRUST, workspace_id="ws_1")
        executor.submit(SlurmRequest("att_1", "train.sh", "gpu", 1, 2, 1024, "01:00:00"), prepared_action_id="pa", approval_id="apr")
        self.assertIn("NONE", runner.calls[-1])
        runner.result = {"return_code": 1}
        with self.assertRaisesRegex(ResearchError, "did not complete"):
            executor.cancel("42", prepared_action_id="pa2", approval_id="apr2")


if __name__ == "__main__":
    unittest.main()
