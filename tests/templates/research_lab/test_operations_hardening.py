from __future__ import annotations

import unittest

from templates.research_lab.contracts import CoreRefs, ResearchError, canonical_hash
from templates.research_lab.operations import ResearchOperationsAdapter
from .support import TEST_TRUST, signed


REFS = CoreRefs("ws_1", "prj_1", "tsk_tpl_v1_research_20260810", "plan_1", "run_1", "agt_c1")


class Core:
    forged = False
    def query_research(self, *, resource, refs):
        return {"resource": resource, "workspace_id": refs.workspace_id, "project_id": refs.project_id, "state": "ready"}
    def execute_research_once(self, *, operation, request, refs, request_hash):
        value = {"operation": operation, "request_hash": "0" * 64 if self.forged else request_hash, "run_id": refs.run_id, "committed": True}
        return signed(value, "research.operation-execute/v1")


class OperationsHardeningTests(unittest.TestCase):
    def test_adapter_binds_core_scope_request_and_canonical_receipt(self):
        core = Core(); adapter = ResearchOperationsAdapter(core, TEST_TRUST)
        self.assertEqual(adapter.query(resource="runtime/health", refs=REFS)["project_id"], "prj_1")
        receipt = adapter.execute(operation="budgets/evaluate", body={"idempotency_key": "idem", "gpu_hours": 1}, refs=REFS)
        self.assertTrue(receipt["committed"])
        core.forged = True
        with self.assertRaisesRegex(ResearchError, "request_hash|exact request"):
            adapter.execute(operation="budgets/evaluate", body={"idempotency_key": "idem2"}, refs=REFS)

    def test_adapter_requires_idempotency_and_registered_operations(self):
        adapter = ResearchOperationsAdapter(Core(), TEST_TRUST)
        with self.assertRaisesRegex(ResearchError, "idempotency"):
            adapter.execute(operation="budgets/evaluate", body={}, refs=REFS)
        with self.assertRaisesRegex(ResearchError, "not registered"):
            adapter.execute(operation="arbitrary", body={"idempotency_key": "x"}, refs=REFS)


if __name__ == "__main__":
    unittest.main()
