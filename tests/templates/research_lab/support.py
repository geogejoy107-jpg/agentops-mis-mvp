from __future__ import annotations

import base64
import atexit
import copy
import json
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from templates.research_lab.contracts import canonical_hash
from templates.research_lab.trust import CoreReceiptVerifier, receipt_purpose

TEST_KEY_ID = "mis-core-test-v1"
_OPENSSL = shutil.which("openssl")
if _OPENSSL is None:
    raise RuntimeError("openssl is required for Research Lab receipt tests")
_KEY_ROOT = Path(tempfile.mkdtemp(prefix="research-lab-test-key-"))
atexit.register(shutil.rmtree, _KEY_ROOT, ignore_errors=True)
TEST_PRIVATE_KEY = _KEY_ROOT / "private.pem"
TEST_PUBLIC_KEY = _KEY_ROOT / "public.pem"
subprocess.run([_OPENSSL, "genpkey", "-algorithm", "ed25519", "-out", str(TEST_PRIVATE_KEY)], check=True, capture_output=True)
subprocess.run([_OPENSSL, "pkey", "-in", str(TEST_PRIVATE_KEY), "-pubout", "-out", str(TEST_PUBLIC_KEY)], check=True, capture_output=True)
_SIGNING_LOCK = threading.Lock()


class TestCoreReceiptVerifier(CoreReceiptVerifier):
    """Test-only public-key verifier; production uses C0's trusted verifier."""

    def __init__(self, *, revoked: bool = False) -> None:
        self.revoked = revoked

    def verify(self, payload, proof, *, purpose, expected_bindings):
        if self.revoked:
            raise ValueError("receipt verification key is revoked")
        if proof.get("algorithm") != "ed25519" or proof.get("key_id") != TEST_KEY_ID or proof.get("purpose") != purpose:
            raise ValueError("receipt proof is out of scope")
        if any(payload.get(key) != value for key, value in expected_bindings.items()):
            raise ValueError("receipt binding mismatch")
        if proof.get("payload_sha256") != canonical_hash(payload):
            raise ValueError("payload hash mismatch")
        with _SIGNING_LOCK:
            message = _KEY_ROOT / "verify.json"
            signature = _KEY_ROOT / "verify.bin"
            message.write_text(json.dumps({"purpose": purpose, "payload": dict(payload)}, sort_keys=True, separators=(",", ":")), encoding="utf-8")
            signature.write_bytes(base64.b64decode(str(proof.get("value") or ""), validate=True))
            completed = subprocess.run([_OPENSSL, "pkeyutl", "-verify", "-pubin", "-inkey", str(TEST_PUBLIC_KEY), "-rawin", "-in", str(message), "-sigfile", str(signature)], capture_output=True, check=False)
        if completed.returncode:
            raise ValueError("signature invalid")
        return {"verified": True, "purpose": purpose, "key_id": TEST_KEY_ID, "revocation_checked": True}


TEST_TRUST = TestCoreReceiptVerifier()

def signed(value, purpose):
    purpose = receipt_purpose(purpose)
    payload = {"authority": "mis_core", "audit_id": str(value.get("audit_id") or "aud_test"), **dict(value)}
    with _SIGNING_LOCK:
        message = _KEY_ROOT / "sign.json"
        signature = _KEY_ROOT / "sign.bin"
        message.write_text(json.dumps({"purpose": purpose, "payload": payload}, sort_keys=True, separators=(",", ":")), encoding="utf-8")
        subprocess.run([_OPENSSL, "pkeyutl", "-sign", "-inkey", str(TEST_PRIVATE_KEY), "-rawin", "-in", str(message), "-out", str(signature)], check=True, capture_output=True)
        encoded = base64.b64encode(signature.read_bytes()).decode("ascii")
    proof = {"algorithm": "ed25519", "key_id": TEST_KEY_ID, "purpose": purpose, "payload_sha256": canonical_hash(payload), "value": encoded}
    envelope = {"payload": payload, "proof": proof}
    return {**envelope, "receipt_hash": canonical_hash(envelope)}


class FakeCore:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str, str, str, str], dict[str, Any]] = {}
        self.events: dict[str, dict[str, Any]] = {}
        self.valid_refs = {"ws_1", "prj_1", "tsk_tpl_v1_research_20260810", "plan_1", "run_1", "agt_c1"}
        self._lock = threading.Lock()
        self.fail_event_commit = False
        self.core_records: dict[tuple[str, str, str], dict[str, Any]] = {}
        self.attempt_admission_allowed = True
        for authority, record_id, extra in (
            ("plan", "plan_1", {"status": "verified"}),
            ("run", "run_1", {"status": "completed", "plan_id": "plan_1", "task_id": "tsk_tpl_v1_research_20260810"}),
            ("identity", "usr_reviewer", {"claim_review_permission_id": "perm_claim_review"}),
            ("permission", "perm_claim_review", {"action": "research_lab.permission.claim.review", "decision": "allow"}),
        ):
            self.core_records[("ws_1", authority, record_id)] = signed({"workspace_id": "ws_1", "project_id": "prj_1", f"{authority}_id": record_id, **extra}, f"research.core-authority/{authority}/v1")

    def get_domain_record(self, *, namespace: str, kind: str, record_id: str, workspace_id: str, project_id: str) -> Mapping[str, Any] | None:
        value = self.records.get((workspace_id, project_id, namespace, kind, record_id))
        return None if value is None else copy.deepcopy(value)

    def list_domain_records(self, *, namespace: str, kind: str, workspace_id: str, project_id: str, filters: Mapping[str, Any]):
        values = [copy.deepcopy(value) for (ws, project, ns, record_kind, _), value in self.records.items() if ws == workspace_id and project == project_id and ns == namespace and record_kind == kind]
        return [value for value in values if all(value.get(key) == expected for key, expected in filters.items())]

    def assert_core_references(self, *, workspace_id: str, references: Mapping[str, str]) -> None:
        if workspace_id not in self.valid_refs or any(value not in self.valid_refs for value in references.values()):
            raise ValueError("missing_core_reference")

    def get_core_authority_record(self, *, authority: str, record_id: str, workspace_id: str):
        value = self.core_records.get((workspace_id, authority, record_id))
        return None if value is None else copy.deepcopy(value)

    def add_core_record(self, authority: str, record_id: str, **value: Any) -> None:
        self.core_records[("ws_1", authority, record_id)] = signed({"workspace_id": "ws_1", "project_id": "prj_1", f"{authority}_id": record_id, **value}, f"research.core-authority/{authority}/v1")

    def authorize_research_attempt(self, *, workspace_id, project_id, task_id, run_id, executor, compute_target_id, trial_id, attempt_number):
        allowed = self.attempt_admission_allowed
        request = {"workspace_id": workspace_id, "project_id": project_id, "task_id": task_id, "plan_id": "plan_1", "run_id": run_id, "executor": executor, "compute_target_id": compute_target_id, "trial_id": trial_id, "attempt_number": attempt_number}
        value = {"decision": "allow" if allowed else "deny", "target_verified": allowed, "budget_allowed": allowed, "concurrency_allowed": allowed, "retry_allowed": allowed, "approval_satisfied": allowed, **request, "request_hash": canonical_hash(request)}
        return signed(value, "research.attempt-admission/v1")

    def transact_domain_records_and_events(self, *, namespace: str, workspace_id: str, operations, events):
        with self._lock:
            staged = copy.deepcopy(self.records)
            staged_events = copy.deepcopy(self.events)
            receipts = []
            for operation in operations:
                project_id = str(operation["value"].get("project_id") or "")
                if not project_id:
                    raise ValueError("project_scope_required")
                key = (workspace_id, project_id, namespace, operation["kind"], operation["record_id"])
                existing = staged.get(key)
                if existing is not None and operation["value"].get("idempotency_key") and operation["value"].get("idempotency_key") == existing.get("idempotency_key"):
                    receipts.append(copy.deepcopy(existing))
                    continue
                current_version = 0 if existing is None else int(existing["version"])
                expected = operation.get("expected_version")
                if expected is not None and expected != current_version:
                    raise ValueError("optimistic_concurrency_conflict")
                stored = {**copy.deepcopy(dict(operation["value"])), "version": current_version + 1}
                staged[key] = stored
                receipts.append(copy.deepcopy(stored))
            if self.fail_event_commit and events:
                raise RuntimeError("outbox unavailable")
            event_receipts = []
            for event in events:
                event_id = str(event["event_id"])
                staged_events.setdefault(event_id, dict(event))
                receipt = {"event_id": event_id, "event_hash": canonical_hash(event), "committed": True}
                event_receipts.append(signed(receipt, "research.outbox-event-commit/v1"))
            self.records = staged
            self.events = staged_events
            record_receipts = []
            for operation, stored in zip(operations, receipts):
                record_receipts.append(signed({"namespace": namespace, "workspace_id": workspace_id, "project_id": operation["value"]["project_id"], "kind": operation["kind"], "record_id": operation["record_id"], "value_hash": canonical_hash(operation["value"]), "value": stored, "version": stored["version"], "committed": True}, "research.domain-record-commit/v1"))
            return {"records": record_receipts, "events": event_receipts}
