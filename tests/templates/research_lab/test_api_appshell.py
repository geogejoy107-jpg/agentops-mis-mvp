from __future__ import annotations

import json
import unittest
from pathlib import Path

from templates.research_lab.api import ROUTE_PREFIX, ResearchAPI, route_contracts
from templates.research_lab.contracts import CoreRefs, canonical_hash
from templates.research_lab.repository import ResearchRepository
from templates.research_lab.service import ResearchService
from templates.research_lab.ui import app_shell_extension

from .support import FakeCore, TEST_TRUST


ROOT = Path(__file__).resolve().parents[3]
REFS = CoreRefs("ws_1", "prj_1", "tsk_tpl_v1_research_20260810", "plan_1", "run_1", "agt_c1")


class APIAppShellTests(unittest.TestCase):
    class Operations:
        def execute(self, *, operation, body, refs):
            value = {"operation": operation}
            return {**value, "receipt_hash": canonical_hash(value)}
        def query(self, *, resource, refs): return {"resource": resource, "state": "ready"}
    def setUp(self) -> None:
        self.authorized = []
        self.api = ResearchAPI(ResearchService(ResearchRepository(FakeCore(), TEST_TRUST), now=lambda: "2026-08-12T00:00:00Z"), lambda action, refs: self.authorized.append(action), lambda: {"state": "degraded", "external_blockers": ["openjiuwen"]})

    def test_route_contracts_are_concrete_and_dispatch_health_truthfully(self) -> None:
        routes = route_contracts()
        self.assertGreaterEqual(len(routes), 15)
        self.assertTrue(all(item["path"].startswith(ROUTE_PREFIX) and item["method"] in {"GET", "POST"} for item in routes))
        status, body = self.api.dispatch(method="GET", path=f"{ROUTE_PREFIX}/health", body={}, refs=REFS)
        self.assertEqual(status, 200)
        self.assertEqual(body["state"], "degraded")

    def test_project_route_mutates_core_backed_service_and_lists_readback(self) -> None:
        status, created = self.api.dispatch(method="POST", path=f"{ROUTE_PREFIX}/projects", body={"name": "API Project", "research_contract": {"objective": "bounded"}, "idempotency_key": "api-create"}, refs=REFS)
        self.assertEqual(status, 201)
        status, listed = self.api.dispatch(method="GET", path=f"{ROUTE_PREFIX}/projects", body={}, refs=REFS)
        self.assertEqual(status, 200)
        self.assertEqual(listed["data"][0]["research_project_id"], created["data"]["research_project_id"])

    def test_deep_link_experiment_route_reads_real_scoped_record(self) -> None:
        _, project = self.api.dispatch(method="POST", path=f"{ROUTE_PREFIX}/projects", body={"name": "Deep", "research_contract": {}, "idempotency_key": "deep-project"}, refs=REFS)
        self.api.service.record_domain_object(refs=REFS, kind="research_question", record_id="que_deep", value={"question": "q"}, idempotency_key="deep-question")
        body = {"research_project_id": project["data"]["research_project_id"], "research_question_id": "que_deep", "protocol_id": "pro_deep", "protocol_version": 1, "research_question": "q", "hypothesis": "h", "stage": "confirmatory", "code_commit": "a" * 40, "dataset_version": "d1", "environment_lock_hash": "b" * 64, "primary_metric": "accuracy", "seeds": [7], "configuration": {"metric_direction": "maximize"}, "idempotency_key": "deep-exp"}
        status, created = self.api.dispatch(method="POST", path=f"{ROUTE_PREFIX}/experiments", body=body, refs=REFS)
        self.assertEqual(status, 201)
        experiment_id = created["data"]["experiment_id"]
        status, detail = self.api.dispatch(method="GET", path=f"{ROUTE_PREFIX}/experiments/{experiment_id}", body={}, refs=REFS)
        self.assertEqual((status, detail["data"]["experiment_id"]), (200, experiment_id))

    def test_appshell_points_to_real_component_and_all_surfaces(self) -> None:
        extension = app_shell_extension()
        self.assertEqual(len(extension["pages"]), 18)
        component = ROOT / extension["component"]
        self.assertTrue(component.is_file())
        source = component.read_text(encoding="utf-8")
        self.assertIn("fetch(`/api/v1/templates/research_lab/", source)
        self.assertIn("credentials: \"same-origin\"", source)
        for resource in ("attempts/start", "claims/decide", "evidence/invalidate", "literature/search", "budgets/evaluate", "runtime/dispatch", "runtime/resume", "memory/candidate", "migration/apply", "exports/bdci"):
            self.assertTrue(any(route["path"].endswith(resource) for route in route_contracts()))

    def test_governed_action_and_read_surfaces_dispatch_to_host_operations(self) -> None:
        api = ResearchAPI(self.api.service, self.api.authorize, self.api.health_provider, self.Operations())
        status, body = api.dispatch(method="POST", path=f"{ROUTE_PREFIX}/claims/decide", body={"claim_id": "clm_1"}, refs=REFS)
        self.assertEqual((status, body["data"]["operation"]), (200, "claims/decide"))
        status, body = api.dispatch(method="GET", path=f"{ROUTE_PREFIX}/runtime/health", body={}, refs=REFS)
        self.assertEqual((status, body["data"]["resource"]), (200, "runtime/health"))


if __name__ == "__main__":
    unittest.main()
