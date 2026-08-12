from __future__ import annotations

import unittest

from template_runtime.protocols import RuntimeReceipt, RuntimeRequest, RuntimeState
from templates.research_lab.contracts import ResearchError, canonical_hash
from templates.research_lab.manifest import register_with_sdk
from templates.research_lab.runtime_team import CoreResearchRuntimeGovernance, ResearchRuntimeCoordinator
from .support import TEST_TRUST, signed


def receipt(state: RuntimeState, *, output_ref: str | None = None, schema: str = "research-plan/v1") -> RuntimeReceipt:
    return RuntimeReceipt("rr_1", "rq_1", state, "provider", "model", "0.1.16", schema, output_ref, "ckp_1", (), (), (), 1, 1, 0, 0.01, 10, "a" * 64, None)


class Runtime:
    def health(self): return {"state": "ready", "upstream_version": "0.1.16"}
    def start(self, request): return receipt(RuntimeState.COMPLETED, output_ref="art_output")
    def interrupt(self, runtime_request_id, reason): return receipt(RuntimeState.INTERRUPTED)
    def resume(self, runtime_request_id, checkpoint_ref, action_hash): return receipt(RuntimeState.RUNNING)
    def cancel(self, runtime_request_id, action_hash): return receipt(RuntimeState.CANCELLED)
    def reconcile(self, runtime_request_id): return receipt(RuntimeState.RUNNING)


class Governance:
    def __init__(self, allow=True): self.allow = allow; self.outputs = []
    def consume_runtime_output(self, **kwargs):
        self.outputs.append(kwargs)
        return {"committed": True, "outbox_receipt_hash": "b" * 64}
    def verify_runtime_receipt(self, **kwargs): return {"verified": True}
    def authorize_runtime_resume(self, **kwargs):
        return {"decision": "allow" if self.allow else "deny", "executed_once": self.allow, "receipt_hash": "c" * 64}
    def verify_resume_receipt(self, **kwargs): return {"verified": True}


class SDK:
    def __init__(self): self.calls = []
    def __getattr__(self, name):
        if name.startswith("register_"):
            return lambda declaration: self.calls.append((name, declaration))
        raise AttributeError(name)


class RuntimeGovernanceTests(unittest.TestCase):
    def test_completed_runtime_output_drives_atomic_domain_write(self):
        governance = Governance()
        coordinator = ResearchRuntimeCoordinator(Runtime(), governance)
        request = RuntimeRequest("rq_1", "ws_1", "prj_1", "research_lab", None, "run_1", "agt_1", "team_1", "provider", "model", "a" * 64, "idem", None, "art_input")
        observed = coordinator.dispatch(request, input_event="research_lab.project.created")
        self.assertEqual(observed["state"], "completed")
        self.assertEqual(governance.outputs[0]["output_ref"], "art_output")

    def test_resume_fails_without_core_prepared_action_readback(self):
        with self.assertRaisesRegex(ResearchError, "denied"):
            ResearchRuntimeCoordinator(Runtime(), Governance(False)).resume("rq_1", "ckp_1", "a" * 64)

    def test_unrelated_runtime_receipt_is_rejected_before_domain_write(self):
        class Drifted(Runtime):
            def start(self, request): return RuntimeReceipt("rr_other", "rq_other", RuntimeState.COMPLETED, "other-provider", "other-model", "0.1.16", "research-plan/v1", "art_output", None, (), (), (), 0, 0, 0, 0.0, 1, "f" * 64, None)
        request = RuntimeRequest("rq_1", "ws_1", "prj_1", "research_lab", None, "run_1", "agt_1", "team_1", "provider", "model", "a" * 64, "idem", None, "art_input")
        with self.assertRaisesRegex(ResearchError, "must bind"):
            ResearchRuntimeCoordinator(Drifted(), Governance()).dispatch(request, input_event="research_lab.project.created")

    def test_manifest_registers_concrete_sdk_declarations(self):
        sdk = SDK(); register_with_sdk(sdk)
        methods = {name for name, _ in sdk.calls}
        self.assertTrue({"register_workflow", "register_agent_team", "register_tool", "register_api_route", "register_ui_extension", "register_memory_policy", "register_cli_command", "register_fixture", "register_testing_hook", "register_exporter"}.issubset(methods))
        registered_routes = [declaration for name, declaration in sdk.calls if name == "register_api_route"]
        self.assertEqual(len(registered_routes), 41)
        self.assertEqual(len({(item["configuration"]["method"], item["configuration"]["path"]) for item in registered_routes}), 41)

    def test_core_runtime_attestation_binds_policy_input_provider_model_and_audit(self):
        request = RuntimeRequest("rq_1", "ws_1", "prj_1", "research_lab", None, "run_1", "agt_1", "team_1", "provider", "model", "a" * 64, "idem", None, "art_input")
        runtime_receipt = receipt(RuntimeState.COMPLETED, output_ref="art_output")
        class Core:
            def verify_runtime_receipt_readback(self, **kwargs):
                value = {"verified": True, "request_hash": kwargs["request_hash"], "runtime_receipt_hash": kwargs["receipt"]["receipt_hash"], "runtime_receipt_document_hash": canonical_hash(kwargs["receipt"]), "runtime_request_id": kwargs["request"].runtime_request_id, "policy_hash": kwargs["request"].policy_hash, "input_ref": kwargs["request"].input_ref, "provider": kwargs["request"].provider, "model": kwargs["request"].model, "output_schema": kwargs["expected_output_schema"]}
                return signed(value, "research.runtime-receipt/v1")
            def read_runtime_output(self, **kwargs): return {}
            def commit_runtime_domain_output_and_event(self, **kwargs): return {}
            def authorize_runtime_resume_once(self, **kwargs): return {}
            def verify_runtime_resume_receipt_readback(self, **kwargs): return {}
        verified = CoreResearchRuntimeGovernance(Core(), TEST_TRUST).verify_runtime_receipt(request=request, receipt=runtime_receipt, role="research_lead", expected_output_schema="research-plan/v1")
        self.assertTrue(verified["verified"])

    def test_resume_attestation_binds_full_receipt_and_atomic_completed_output(self):
        runtime_receipt = receipt(RuntimeState.COMPLETED, output_ref="art_output")
        authorization = signed({"runtime_request_id":"rq_1", "checkpoint_ref":"ckp_1", "action_hash":"d" * 64, "decision":"allow", "executed_once":True}, "research.runtime-resume-authorization/v1")
        class Core:
            def verify_runtime_receipt_readback(self, **kwargs): return {}
            def read_runtime_output(self, **kwargs): return {}
            def commit_runtime_domain_output_and_event(self, **kwargs): return {}
            def authorize_runtime_resume_once(self, **kwargs): return {}
            def verify_runtime_resume_receipt_readback(self, **kwargs):
                value = {"runtime_request_id":kwargs["runtime_request_id"], "checkpoint_ref":kwargs["checkpoint_ref"], "action_hash":kwargs["action_hash"], "runtime_receipt_hash":kwargs["receipt"]["receipt_hash"], "runtime_receipt_document_hash":canonical_hash(kwargs["receipt"]), "authorization_receipt_hash":kwargs["authorization_receipt_hash"], "state":kwargs["receipt"]["state"], "output_ref":kwargs["receipt"]["output_ref"], "output_committed":True, "outbox_receipt_hash":"e" * 64, "verified":True}
                return signed(value, "research.runtime-resume-receipt/v1")
        governance = CoreResearchRuntimeGovernance(Core(), TEST_TRUST)
        verified = governance.verify_resume_receipt(runtime_request_id="rq_1", checkpoint_ref="ckp_1", action_hash="d" * 64, receipt=runtime_receipt, authorization=authorization)
        self.assertTrue(verified["output_committed"])

        class Forged(Core):
            def verify_runtime_resume_receipt_readback(self, **kwargs):
                value = dict(super().verify_runtime_resume_receipt_readback(**kwargs)["payload"])
                value["runtime_receipt_document_hash"] = "f" * 64
                return signed(value, "research.runtime-resume-receipt/v1")
        with self.assertRaisesRegex(ResearchError, "bind runtime_receipt_document_hash"):
            CoreResearchRuntimeGovernance(Forged(), TEST_TRUST).verify_resume_receipt(runtime_request_id="rq_1", checkpoint_ref="ckp_1", action_hash="d" * 64, receipt=runtime_receipt, authorization=authorization)


if __name__ == "__main__":
    unittest.main()
