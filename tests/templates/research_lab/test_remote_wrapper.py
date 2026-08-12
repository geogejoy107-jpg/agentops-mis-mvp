from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from templates.research_lab.contracts import ResearchError, canonical_hash
from templates.research_lab.remote_wrapper import DurableSSHWrapper
from .support import TEST_TRUST, signed


class RemoteWrapperTests(unittest.TestCase):
    @staticmethod
    def request(**changes):
        value = {"attempt_id": "att_1", "operation": "submit", "remote_root": "/srv/research", "payload": {}, "admission_receipt_hash": "c" * 64, "target_snapshot_hash": "b" * 64}
        value.update(changes)
        authorization = signed({"decision": "allow", "executed_once": True, "request_hash": canonical_hash(value), "tool_id": "research_lab.tool.ssh_execute", "prepared_action_id": "pa_1", "approval_id": "apr_1"}, "research.execution-authorization/v1")
        return {**value, "authorization_receipt_hash": authorization["receipt_hash"], "core_authorization": authorization}

    def test_submit_is_durable_idempotent_and_transfer_is_hashed(self) -> None:
        calls = []
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw).resolve()
            alive = {4321: True}
            wrapper = DurableSSHWrapper(governed_root=root, trust=TEST_TRUST, process_launcher=lambda request, path: calls.append(request) or {"attempt_id": request["attempt_id"], "request_hash": canonical_hash(request), "pid": 4321, "process_start_identity": "start-1"}, process_probe=lambda pid, identity: alive.get(pid, False) and identity == "start-1", process_cancel=lambda pid, identity: alive.__setitem__(pid, False))
            request = self.request(remote_root=str(root), payload={"argv": ["python", "train.py"]})
            first = wrapper.handle(operation="submit", stdin_bytes=json.dumps(request).encode())
            second = wrapper.handle(operation="submit", stdin_bytes=json.dumps(request).encode())
            self.assertEqual(first, second)
            self.assertEqual(len(calls), 1)
            artifact = root / "attempts/att_1/artifact.tar"
            artifact.write_bytes(b"bounded-artifact")
            collected_request = self.request(remote_root=str(root), payload={"argv": ["python", "train.py"]}, operation="collect")
            collected = wrapper.handle(operation="collect", stdin_bytes=json.dumps(collected_request).encode())
            self.assertEqual(len(collected["artifact_sha256"]), 64)
            cancelled = wrapper.handle(operation="cancel", stdin_bytes=json.dumps(self.request(remote_root=str(root), payload={"argv": ["python", "train.py"]}, operation="cancel")).encode())
            status = wrapper.handle(operation="status", stdin_bytes=json.dumps(self.request(remote_root=str(root), payload={"argv": ["python", "train.py"]}, operation="status")).encode())
            self.assertEqual((cancelled["state"], status["state"]), ("cancelled", "cancelled"))

    def test_wrapper_rejects_mismatch_and_missing_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            wrapper = DurableSSHWrapper(governed_root=Path(raw), trust=TEST_TRUST, process_launcher=lambda request, path: {"attempt_id": request["attempt_id"], "request_hash": canonical_hash(request), "pid": 4321, "process_start_identity": "start-1"}, process_probe=lambda pid, identity: True, process_cancel=lambda pid, identity: None)
            with self.assertRaisesRegex(ResearchError, "does not match"):
                wrapper.handle(operation="submit", stdin_bytes=json.dumps(self.request(operation="cancel")).encode())
            request = self.request(remote_root=raw, payload={"argv": ["python", "a.py"]})
            wrapper.handle(operation="submit", stdin_bytes=json.dumps(request).encode())
            with self.assertRaisesRegex(ResearchError, "replay|exact wire request"):
                wrapper.handle(operation="submit", stdin_bytes=json.dumps({**request, "payload": {"argv": ["python", "evil.py"]}}).encode())
            marker = Path(raw) / "attempts/att_1/receipt.json"
            value = json.loads(marker.read_text()); value["pid"] = 9999; marker.write_text(json.dumps(value))
            with self.assertRaisesRegex(ResearchError, "integrity"):
                wrapper.handle(operation="status", stdin_bytes=json.dumps(self.request(remote_root=raw, payload={"argv": ["python", "a.py"]}, operation="status")).encode())

    def test_self_hashed_terminal_cannot_forge_completed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            wrapper = DurableSSHWrapper(governed_root=Path(raw), trust=TEST_TRUST, process_launcher=lambda request, path: {"attempt_id": request["attempt_id"], "request_hash": canonical_hash(request), "pid": 4321, "process_start_identity": "start-1"}, process_probe=lambda pid, identity: False)
            request = self.request(remote_root=raw)
            launch = wrapper.handle(operation="submit", stdin_bytes=json.dumps(request).encode())
            terminal = {"attempt_id": "att_1", "process_start_identity": "start-1", "state": "completed", "execution_request_hash": launch["request_hash"], "authorization_receipt_hash": request["authorization_receipt_hash"], "admission_receipt_hash": request["admission_receipt_hash"], "target_snapshot_hash": request["target_snapshot_hash"]}
            terminal["receipt_hash"] = canonical_hash(terminal)
            (Path(raw) / "attempts/att_1/terminal.json").write_text(json.dumps(terminal))
            with self.assertRaisesRegex(ResearchError, "terminal"):
                wrapper.handle(operation="status", stdin_bytes=json.dumps(self.request(remote_root=raw, operation="status")).encode())

    def test_cancel_after_verified_completion_remains_completed(self) -> None:
        cancelled = []
        with tempfile.TemporaryDirectory() as raw:
            wrapper = DurableSSHWrapper(governed_root=Path(raw), trust=TEST_TRUST, process_launcher=lambda request, path: {"attempt_id": request["attempt_id"], "request_hash": canonical_hash(request), "pid": 4321, "process_start_identity": "start-1"}, process_probe=lambda pid, identity: False, process_cancel=lambda pid, identity: cancelled.append(pid), terminal_verifier=lambda terminal, launch: terminal.get("scheduler_signature") == "verified")
            request = self.request(remote_root=raw)
            launch = wrapper.handle(operation="submit", stdin_bytes=json.dumps(request).encode())
            terminal = {"attempt_id":"att_1", "process_start_identity":"start-1", "state":"completed", "execution_request_hash":launch["request_hash"], "authorization_receipt_hash":request["authorization_receipt_hash"], "admission_receipt_hash":request["admission_receipt_hash"], "target_snapshot_hash":request["target_snapshot_hash"], "scheduler_signature":"verified"}
            terminal["receipt_hash"] = canonical_hash(terminal)
            (Path(raw) / "attempts/att_1/terminal.json").write_text(json.dumps(terminal))
            observed = wrapper.handle(operation="cancel", stdin_bytes=json.dumps(self.request(remote_root=raw, operation="cancel")).encode())
            self.assertEqual(observed["state"], "completed")
            self.assertEqual(cancelled, [])

    def test_crash_after_fence_never_launches_on_retry(self) -> None:
        launches = []
        with tempfile.TemporaryDirectory() as raw:
            wrapper = DurableSSHWrapper(
                governed_root=Path(raw), trust=TEST_TRUST,
                process_launcher=lambda request, path: launches.append(request) or {"attempt_id": request["attempt_id"], "request_hash": canonical_hash(request), "pid": 4321, "process_start_identity": "start-1"},
            )
            request = self.request(remote_root=raw)
            fence_written = DurableSSHWrapper._write_once

            def crash_after_fence(path, value):
                fence_written(path, value)
                if path.name == "launch-intent.json":
                    raise RuntimeError("crash-after-fence")

            wrapper._write_once = crash_after_fence
            with self.assertRaisesRegex(RuntimeError, "crash-after-fence"):
                wrapper.handle(operation="submit", stdin_bytes=json.dumps(request).encode())
            self.assertEqual(launches, [])
            recovered = DurableSSHWrapper(governed_root=Path(raw), trust=TEST_TRUST, process_launcher=lambda request, path: launches.append(request) or {}).handle(operation="submit", stdin_bytes=json.dumps(request).encode())
            self.assertEqual(recovered["state"], "remote_unknown")
            self.assertEqual(launches, [])

    def test_crash_after_launch_before_receipt_reconciles_without_second_launch(self) -> None:
        launches = []
        remote_registry = {}
        with tempfile.TemporaryDirectory() as raw:
            def launch(request, path):
                launches.append(request)
                observed = {"attempt_id": request["attempt_id"], "operation": request["operation"], "request_hash": canonical_hash(request), "authorization_receipt_hash": request["authorization_receipt_hash"], "admission_receipt_hash": request["admission_receipt_hash"], "target_snapshot_hash": request["target_snapshot_hash"], "state": "running", "pid": 4321, "process_start_identity": "start-1"}
                remote_registry[request["attempt_id"]] = signed(observed, "research.remote-launch-reconciliation/v1")
                return observed

            wrapper = DurableSSHWrapper(governed_root=Path(raw), trust=TEST_TRUST, process_launcher=launch)
            request = self.request(remote_root=raw)
            atomic_create = wrapper._atomic_create

            def crash_before_receipt(path, value):
                if path.name == "receipt.json":
                    raise RuntimeError("crash-before-receipt")
                atomic_create(path, value)

            wrapper._atomic_create = crash_before_receipt
            with self.assertRaisesRegex(RuntimeError, "crash-before-receipt"):
                wrapper.handle(operation="submit", stdin_bytes=json.dumps(request).encode())
            recovered = DurableSSHWrapper(
                governed_root=Path(raw), trust=TEST_TRUST,
                process_launcher=lambda request, path: launches.append(request) or {},
                launch_reconciler=lambda fence, path: remote_registry.get(fence["attempt_id"]),
            ).handle(operation="submit", stdin_bytes=json.dumps(request).encode())
            self.assertEqual((recovered["state"], recovered["pid"]), ("running", 4321))
            self.assertEqual(len(launches), 1)

    def test_forged_reconciler_booleans_are_remote_unknown_without_resend(self) -> None:
        launches = []
        with tempfile.TemporaryDirectory() as raw:
            request = self.request(remote_root=raw)
            attempt_dir = Path(raw) / "attempts/att_1"
            attempt_dir.mkdir(parents=True)
            fence = {
                "attempt_id": "att_1", "operation": "submit", "request_hash": canonical_hash(request),
                "authorization_receipt_hash": request["authorization_receipt_hash"],
                "admission_receipt_hash": request["admission_receipt_hash"],
                "target_snapshot_hash": request["target_snapshot_hash"], "state": "launch_fenced",
            }
            fence["receipt_hash"] = canonical_hash(fence)
            DurableSSHWrapper._write_once(attempt_dir / "launch-intent.json", fence)
            forged = {"authority": "remote_launch_registry", "authoritative": True, "attempt_id": "att_1", "operation": "submit", "request_hash": canonical_hash(request), "pid": 4321, "process_start_identity": "start-1"}
            wrapper = DurableSSHWrapper(governed_root=Path(raw), trust=TEST_TRUST, process_launcher=lambda *_: launches.append(1) or {}, launch_reconciler=lambda *_: forged)
            recovered = wrapper.handle(operation="submit", stdin_bytes=json.dumps(request).encode())
            self.assertEqual(recovered["state"], "remote_unknown")
            self.assertEqual(launches, [])
            self.assertFalse((attempt_dir / "receipt.json").exists())

    def test_reconciler_signed_receipt_must_bind_exact_request(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            request = self.request(remote_root=raw)
            attempt_dir = Path(raw) / "attempts/att_1"
            attempt_dir.mkdir(parents=True)
            fence = {"attempt_id": "att_1", "operation": "submit", "request_hash": canonical_hash(request), "authorization_receipt_hash": request["authorization_receipt_hash"], "admission_receipt_hash": request["admission_receipt_hash"], "target_snapshot_hash": request["target_snapshot_hash"], "state": "launch_fenced"}
            fence["receipt_hash"] = canonical_hash(fence)
            DurableSSHWrapper._write_once(attempt_dir / "launch-intent.json", fence)
            mismatched = signed({**fence, "receipt_hash": "not-authority", "request_hash": "f" * 64, "state": "running", "pid": 4321, "process_start_identity": "start-1"}, "research.remote-launch-reconciliation/v1")
            wrapper = DurableSSHWrapper(governed_root=Path(raw), trust=TEST_TRUST, process_launcher=lambda *_: self.fail("must not resend"), launch_reconciler=lambda *_: mismatched)
            self.assertEqual(wrapper.handle(operation="submit", stdin_bytes=json.dumps(request).encode())["state"], "remote_unknown")

    def test_reconciler_wrong_purpose_or_revoked_key_is_remote_unknown(self) -> None:
        class RemoteRevokedTrust:
            def verify(self, payload, proof, *, purpose, expected_bindings):
                if purpose == "research.remote-launch-reconciliation.v1":
                    raise ValueError("remote registry key is revoked")
                return TEST_TRUST.verify(payload, proof, purpose=purpose, expected_bindings=expected_bindings)

        for label, purpose, trust in (
            ("wrong-purpose", "research.execution-authorization/v1", TEST_TRUST),
            ("revoked-key", "research.remote-launch-reconciliation/v1", RemoteRevokedTrust()),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as raw:
                request = self.request(remote_root=raw)
                attempt_dir = Path(raw) / "attempts/att_1"
                attempt_dir.mkdir(parents=True)
                fence = {"attempt_id": "att_1", "operation": "submit", "request_hash": canonical_hash(request), "authorization_receipt_hash": request["authorization_receipt_hash"], "admission_receipt_hash": request["admission_receipt_hash"], "target_snapshot_hash": request["target_snapshot_hash"], "state": "launch_fenced"}
                fence["receipt_hash"] = canonical_hash(fence)
                DurableSSHWrapper._write_once(attempt_dir / "launch-intent.json", fence)
                observed = signed({**fence, "receipt_hash": "not-authority", "state": "running", "pid": 4321, "process_start_identity": "start-1"}, purpose)
                wrapper = DurableSSHWrapper(governed_root=Path(raw), trust=trust, process_launcher=lambda *_: self.fail("must not resend"), launch_reconciler=lambda *_: observed)
                self.assertEqual(wrapper.handle(operation="submit", stdin_bytes=json.dumps(request).encode())["state"], "remote_unknown")

    def test_crash_during_marker_create_leaves_no_partial_receipt_and_replace_is_atomic(self) -> None:
        launches = []
        with tempfile.TemporaryDirectory() as raw:
            wrapper = DurableSSHWrapper(
                governed_root=Path(raw), trust=TEST_TRUST,
                process_launcher=lambda request, path: launches.append(request) or {"attempt_id": request["attempt_id"], "request_hash": canonical_hash(request), "pid": 4321, "process_start_identity": "start-1"},
            )
            request = self.request(remote_root=raw)
            write_once = wrapper._write_once

            def crash_during_temp(path, value):
                if path.name.startswith("receipt.json."):
                    path.write_text("{", encoding="utf-8")
                    raise RuntimeError("crash-during-marker")
                write_once(path, value)

            with patch.object(DurableSSHWrapper, "_write_once", side_effect=crash_during_temp), self.assertRaisesRegex(RuntimeError, "crash-during-marker"):
                wrapper.handle(operation="submit", stdin_bytes=json.dumps(request).encode())
            self.assertFalse((Path(raw) / "attempts/att_1/receipt.json").exists())
            recovered = DurableSSHWrapper(governed_root=Path(raw), trust=TEST_TRUST, process_launcher=lambda request, path: launches.append(request) or {}).handle(operation="submit", stdin_bytes=json.dumps(request).encode())
            self.assertEqual(recovered["state"], "remote_unknown")
            self.assertEqual(len(launches), 1)

            marker = Path(raw) / "replace.json"
            marker.write_text(json.dumps({"state": "old", "receipt_hash": canonical_hash({"state": "old"})}), encoding="utf-8")
            with patch.object(os, "replace", side_effect=RuntimeError("replace-crash")):
                with self.assertRaisesRegex(RuntimeError, "replace-crash"):
                    DurableSSHWrapper._replace(marker, {"state": "new", "receipt_hash": canonical_hash({"state": "new"})})
            self.assertEqual(json.loads(marker.read_text())["state"], "old")


if __name__ == "__main__":
    unittest.main()
