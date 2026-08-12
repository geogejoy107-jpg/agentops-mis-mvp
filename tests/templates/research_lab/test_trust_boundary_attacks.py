from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from templates.research_lab.contracts import CoreRefs, ResearchError, canonical_hash
from templates.research_lab.executors import ExecutionRequest, _verify_authorization, SlurmExecutor
from templates.research_lab.repository import ResearchRepository
from templates.research_lab.service import ResearchService
from templates.research_lab.trust import CoreTrustStore, attest_test_receipt

from .support import FakeCore, TEST_KEY, TEST_KEY_ID, TEST_TRUST


class TrustBoundaryAttackTests(unittest.TestCase):
    def test_caller_boolean_and_self_hash_cannot_forge_core_authorization(self):
        value = {"authority": "mis_core", "signature_verified": True, "audit_id": "aud_forged", "decision": "allow", "executed_once": True, "request_hash": "a" * 64, "tool_id": "research_lab.tool.local_execute", "prepared_action_id": "pa", "approval_id": "apr"}
        with self.assertRaisesRegex(ResearchError, "key|signature"):
            _verify_authorization({**value, "receipt_hash": canonical_hash(value)}, trust=TEST_TRUST, request_hash="a" * 64, tool_id="research_lab.tool.local_execute", prepared_action_id="pa", approval_id="apr")

    def test_revoked_core_key_fails_closed(self):
        receipt = attest_test_receipt({"decision": "allow", "executed_once": True, "request_hash": "a" * 64, "tool_id": "research_lab.tool.local_execute", "prepared_action_id": "pa", "approval_id": "apr"}, purpose="research.execution-authorization/v1", key_id=TEST_KEY_ID, key=TEST_KEY)
        revoked = CoreTrustStore({TEST_KEY_ID: TEST_KEY}, frozenset({TEST_KEY_ID}))
        with self.assertRaisesRegex(ResearchError, "revoked"):
            _verify_authorization(receipt, trust=revoked, request_hash="a" * 64, tool_id="research_lab.tool.local_execute", prepared_action_id="pa", approval_id="apr")

    def test_generic_authority_and_plaintext_secret_fields_are_rejected(self):
        core = FakeCore(); refs = CoreRefs("ws_1", "prj_1", "tsk_tpl_v1_research_20260810", "plan_1", "run_1", "agt_c1")
        service = ResearchService(ResearchRepository(core, TEST_TRUST), now=lambda: "2026-08-12T00:00:00Z")
        for contract in ({"canonical": True}, {"nested": {"api_key": "secret"}}, {"nested": {"value": "sk-live-forbidden"}}):
            with self.subTest(contract=contract), self.assertRaises(ResearchError):
                service.create_project(refs=refs, name="unsafe", research_contract=contract, idempotency_key="unsafe")
        with tempfile.TemporaryDirectory() as raw, self.assertRaisesRegex(ResearchError, "credential"):
            ExecutionRequest("att", ("/usr/bin/true",), Path(raw), {"VISIBLE": "sk-live-forbidden"}, 1)

    def test_slurm_substring_cannot_forge_completed(self):
        class Authority:
            def authorize_execute_once(self, **kwargs):
                return attest_test_receipt({"decision": "allow", "executed_once": True, "request_hash": kwargs["request_hash"], "tool_id": kwargs["tool_id"], "prepared_action_id": kwargs["prepared_action_id"], "approval_id": kwargs["approval_id"]}, purpose="research.execution-authorization/v1", key_id=TEST_KEY_ID, key=TEST_KEY)
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


if __name__ == "__main__":
    unittest.main()
