from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from templates.research_lab.contracts import CoreRefs, ResearchError, canonical_hash
from templates.research_lab.executors import ExecutionRequest, _verify_authorization, SlurmExecutor
from templates.research_lab.repository import ResearchRepository
from templates.research_lab.service import ResearchService
from .support import FakeCore, TEST_PUBLIC_KEY, TEST_TRUST, TestCoreReceiptVerifier, signed
from .c0_snapshot import exported_c0


class TrustBoundaryAttackTests(unittest.TestCase):
    def test_caller_boolean_and_self_hash_cannot_forge_core_authorization(self):
        payload = {"authority": "mis_core", "signature_verified": True, "audit_id": "aud_forged", "decision": "allow", "executed_once": True, "request_hash": "a" * 64, "tool_id": "research_lab.tool.local_execute", "prepared_action_id": "pa", "approval_id": "apr"}
        proof = {"algorithm": "ed25519", "key_id": "attacker", "purpose": "research.execution-authorization/v1", "payload_sha256": canonical_hash(payload), "value": "forged"}
        envelope = {"payload": payload, "proof": proof}
        with self.assertRaisesRegex(ResearchError, "signature|authority"):
            _verify_authorization({**envelope, "receipt_hash": canonical_hash(envelope)}, trust=TEST_TRUST, request_hash="a" * 64, tool_id="research_lab.tool.local_execute", prepared_action_id="pa", approval_id="apr")

    def test_revoked_core_key_fails_closed(self):
        receipt = signed({"decision": "allow", "executed_once": True, "request_hash": "a" * 64, "tool_id": "research_lab.tool.local_execute", "prepared_action_id": "pa", "approval_id": "apr"}, "research.execution-authorization/v1")
        revoked = TestCoreReceiptVerifier(revoked=True)
        with self.assertRaisesRegex(ResearchError, "signature|revocation"):
            _verify_authorization(receipt, trust=revoked, request_hash="a" * 64, tool_id="research_lab.tool.local_execute", prepared_action_id="pa", approval_id="apr")

    def test_generic_authority_and_plaintext_secret_fields_are_rejected(self):
        core = FakeCore(); refs = CoreRefs("ws_1", "prj_1", "tsk_tpl_v1_research_20260810", "plan_1", "run_1", "agt_c1")
        service = ResearchService(ResearchRepository(core, TEST_TRUST), now=lambda: "2026-08-12T00:00:00Z")
        credential_shape = "sk-" + "live" + "-forbidden"
        for contract in ({"canonical": True}, {"nested": {"api_key": "secret"}}, {"nested": {"value": credential_shape}}):
            with self.subTest(contract=contract), self.assertRaises(ResearchError):
                service.create_project(refs=refs, name="unsafe", research_contract=contract, idempotency_key="unsafe")
        with tempfile.TemporaryDirectory() as raw, self.assertRaisesRegex(ResearchError, "credential"):
            ExecutionRequest("att", ("/usr/bin/true",), Path(raw), {"VISIBLE": credential_shape}, 1)

    def test_slurm_substring_cannot_forge_completed(self):
        class Authority:
            def authorize_execute_once(self, **kwargs):
                return signed({"decision": "allow", "executed_once": True, "request_hash": kwargs["request_hash"], "tool_id": kwargs["tool_id"], "prepared_action_id": kwargs["prepared_action_id"], "approval_id": kwargs["approval_id"]}, "research.execution-authorization/v1")
        class Runner:
            def run(self, *args, **kwargs): return {"return_code": 0, "stdout": "42|NOT_COMPLETED|0:0|00:01"}
        with self.assertRaisesRegex(ResearchError, "schema"):
            SlurmExecutor(Runner(), authority=Authority(), trust=TEST_TRUST, workspace_id="ws_1").reconcile("42", prepared_action_id="pa", approval_id="apr")

    def test_record_receipts_are_verified_per_record_not_per_batch(self):
        class SwappedCore(FakeCore):
            def transact_domain_records_and_events(self, **kwargs):
                transaction = super().transact_domain_records_and_events(**kwargs)
                transaction["records"] = list(reversed(transaction["records"]))
                return transaction
        refs = CoreRefs("ws_1", "prj_1", "tsk_tpl_v1_research_20260810", "plan_1", "run_1", "agt_c1")
        operations = (
            {"kind":"experiment", "record_id":"exp_1", "value":{"created_at":"2026-08-12T00:00:00Z"}},
            {"kind":"trial", "record_id":"trl_1", "value":{"created_at":"2026-08-12T00:00:00Z"}},
        )
        with self.assertRaisesRegex(ResearchError, "bind kind|bind record_id"):
            ResearchRepository(SwappedCore(), TEST_TRUST).put_many(refs=refs, operations=operations)

    def test_real_c0_public_key_verifier_accepts_envelope_and_rejects_revocation(self):
        root = Path(__file__).resolve().parents[3]
        receipt = signed({"decision": "allow", "executed_once": True, "request_hash": "a" * 64, "tool_id": "research_lab.tool.local_execute"}, "research.execution-authorization/v1")
        with exported_c0(root) as c0, tempfile.TemporaryDirectory() as raw:
            trust_store = Path(raw) / "trust.json"
            trust_store.write_text(json.dumps({"keys": {"mis-core-test-v1": {"algorithm": "ed25519", "revoked": False, "purposes": ["research.execution-authorization.v1"], "public_key_pem": TEST_PUBLIC_KEY.read_text()}}}), encoding="utf-8")
            trust_store.chmod(0o600)
            script = """
import json, os, sys
from pathlib import Path
from templates.research_lab.trust import build_production_core_receipt_verifier
receipt = json.loads(sys.stdin.read())
store = Path(sys.argv[1])
os.environ['AGENTOPS_CORE_RECEIPT_TRUST_STORE'] = str(store)
verifier = build_production_core_receipt_verifier()
verified = verifier.verify(receipt['payload'], receipt['proof'], purpose='research.execution-authorization.v1', expected_bindings={'request_hash': 'a' * 64, 'tool_id': 'research_lab.tool.local_execute'})
assert verified['verified'] is True and verified['revocation_checked'] is True
data = json.loads(store.read_text()); data['keys']['mis-core-test-v1']['revoked'] = True; store.write_text(json.dumps(data)); store.chmod(0o600)
try:
    verifier.verify(receipt['payload'], receipt['proof'], purpose='research.execution-authorization.v1', expected_bindings={'request_hash': 'a' * 64})
except ValueError:
    pass
else:
    raise AssertionError('revoked key accepted')
"""
            environment = {**os.environ, "PYTHONPATH": os.pathsep.join((str(c0), str(root)))}
            completed = subprocess.run([sys.executable, "-P", "-W", "error", "-c", script, str(trust_store)], cwd="/tmp", env=environment, input=json.dumps(receipt), capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_production_composition_rejects_non_c0_verifier(self):
        root = Path(__file__).resolve().parents[3]
        script = """
from unittest.mock import patch
from templates.research_lab.contracts import ResearchError
from templates.research_lab.trust import build_production_core_receipt_verifier
class Fake:
    def verify(self, *args, **kwargs): return {'verified': True}
with patch('template_runtime.trust.build_core_receipt_verifier', return_value=Fake()):
    try:
        build_production_core_receipt_verifier()
    except ResearchError as exc:
        assert exc.code == 'research.core_verifier_untrusted'
    else:
        raise AssertionError('fake production verifier accepted')
"""
        with exported_c0(root) as c0:
            environment = {**os.environ, "PYTHONPATH": os.pathsep.join((str(c0), str(root)))}
            completed = subprocess.run([sys.executable, "-P", "-W", "error", "-c", script], cwd="/tmp", env=environment, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
