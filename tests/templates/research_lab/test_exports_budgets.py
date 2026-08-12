from __future__ import annotations

import unittest
import json
import subprocess
import sys

from templates.research_lab.budgets import BudgetGate, ResearchBudget
from templates.research_lab.contracts import ResearchError, canonical_hash
from templates.research_lab.exports import bdci_evaluation_script, bdci_submission_package, manuscript_section, reproducibility_bundle, research_receipt
from .support import TEST_TRUST, signed


class ExportsBudgetsTests(unittest.TestCase):
    class EvidencePort:
        def verify_submission_evidence(self, *, references):
            return signed({"verified":True, "claim_ids":list(references["claim_ids"]), "reference_hash":canonical_hash({"submission_kind": "bdci_2026", "references": {key: list(value) for key, value in sorted(references.items())}})}, "research.bdci-submission-evidence/v1")
        def verify_export_evidence(self, *, export_kind, references): return signed({"verified":True, "export_kind":export_kind, "reference_hash":canonical_hash({"export_kind": export_kind, "references": {key: list(map(str, value)) for key, value in sorted(references.items())}})}, "research.export-evidence/v1")
    def test_budget_gate_blocks_overage_and_requires_approval(self) -> None:
        budget = ResearchBudget(10, 1000, 50, 2, 1, 300, 2, 10)
        result = BudgetGate.evaluate(budget=budget, consumed={"gpu_hours": 9, "tokens": 100}, request={"gpu_hours": 2, "tokens": 10, "cost_usd": 12}, stage="pilot")
        self.assertFalse(result["allowed"])
        self.assertTrue(result["approval_required"])

    def test_reproducibility_bundle_and_receipt_bind_core_evidence(self) -> None:
        protocol = {"protocol_hash": "a" * 64, "code_commit": "b" * 40, "dataset_version": "d1", "environment_lock_hash": "c" * 64, "seeds": [7, 11]}
        bundle = reproducibility_bundle(protocol=protocol, attempts=[{"job_attempt_id": "att_1"}], metrics=[{"metric_snapshot_id": "met_1"}], artifacts=[{"artifact_id": "art_1", "sha256": "d" * 64, "media_type": "application/json"}], claims=[{"research_claim_id": "clm_1", "evaluation_id": "eval_1", "reviewer_id": "usr_1"}], evidence_port=self.EvidencePort(), trust=TEST_TRUST)
        self.assertFalse(bundle["contains_raw_prompts_or_secrets"])
        receipt = research_receipt(core_refs={"workspace_id": "ws_1", "project_id": "prj_1", "task_id": "tsk_tpl_v1_research_20260810", "plan_id": "plan_1", "run_id": "run_1", "audit_id": "aud_1"}, protocol_hash="a" * 64, experiment_id="exp_1", trial_ids=["trl_1"], attempt_ids=["att_1"], artifact_ids=["art_1"], evaluation_ids=["eval_1"], claim_ids=["clm_1"], reviewer_ids=["usr_1"], external_integrations=[{"name": "ssh_gpu", "status": "unavailable"}], evidence_port=self.EvidencePort(), trust=TEST_TRUST)
        self.assertFalse(receipt["canonical"])

    def test_reproducibility_readback_binds_protocol_metrics_artifacts_evaluations_and_reviewers(self) -> None:
        class RecordingPort(self.EvidencePort):
            def __init__(self): self.references = None
            def verify_export_evidence(self, *, export_kind, references):
                self.references = references
                return super().verify_export_evidence(export_kind=export_kind, references=references)
        port = RecordingPort()
        reproducibility_bundle(protocol={"protocol_hash": "a" * 64, "code_commit": "b" * 40, "dataset_version": "d1", "environment_lock_hash": "c" * 64, "seeds": [7]}, attempts=[{"job_attempt_id": "att_1"}], metrics=[{"metric_snapshot_id": "met_1"}], artifacts=[{"artifact_id": "art_1", "sha256": "d" * 64}], claims=[{"research_claim_id": "clm_1", "evaluation_id": "eval_1", "reviewer_id": "usr_1"}], evidence_port=port, trust=TEST_TRUST)
        self.assertTrue({"protocol_hashes", "metric_ids", "artifact_sha256s", "evaluation_ids", "reviewer_ids"}.issubset(port.references))
        class ForgedPort:
            def verify_export_evidence(self, *, export_kind, references): return {"verified": True, "export_kind": export_kind, "reference_hash": canonical_hash({"export_kind": export_kind, "references": {key: list(map(str, value)) for key, value in sorted(references.items())}}), "receipt_hash": "0" * 64}
        with self.assertRaisesRegex(ResearchError, "verification|readback|envelope"):
            reproducibility_bundle(protocol={"protocol_hash": "a" * 64, "code_commit": "b" * 40, "dataset_version": "d1", "environment_lock_hash": "c" * 64, "seeds": [7]}, attempts=[], metrics=[], artifacts=[], claims=[], evidence_port=ForgedPort(), trust=TEST_TRUST)

    def test_evidence_sections_require_claims_and_citation_locators(self) -> None:
        with self.assertRaisesRegex(ResearchError, "claim references"):
            manuscript_section(section="results", content_artifact_id="art_text", claim_ids=[], figure_artifact_ids=[], table_artifact_ids=[], citations=[], evidence_port=self.EvidencePort(), trust=TEST_TRUST)
        with self.assertRaisesRegex(ResearchError, "source and locator"):
            manuscript_section(section="method", content_artifact_id="art_text", claim_ids=["clm_1"], figure_artifact_ids=[], table_artifact_ids=[], citations=[{"literature_id": "lit_1", "locator": ""}], evidence_port=self.EvidencePort(), trust=TEST_TRUST)

    def test_bdci_evaluation_and_submission_are_materialized_and_checksums_bound(self) -> None:
        evaluation = bdci_evaluation_script(input_schema={"prediction": "number"}, output_schema={"score": "number"}, metric="accuracy")
        repro = {"bundle_hash": "a" * 64}
        package = bdci_submission_package(short_paper="# Results", iclr_export="\\section{Results}", reproducibility=repro, input_output_manifest={"input_schema": {"prediction": "number"}, "output_schema": {"score": "number"}}, evaluation_script=evaluation, claims=[{"research_claim_id": "clm_1", "status": "supported", "evaluation_id": "eval_1"}], evidence_port=self.EvidencePort(), trust=TEST_TRUST)
        self.assertIn("evaluation/evaluate.py", package["files"])
        self.assertEqual(len(package["manifest"]["entries"]), 6)
        self.assertEqual(len(package["package_hash"]), 64)
        with self.assertRaisesRegex(ResearchError, "without passed"):
            bdci_submission_package(short_paper="x", iclr_export="y", reproducibility=repro, input_output_manifest={"input_schema": {"x": 1}, "output_schema": {"y": 1}}, evaluation_script=evaluation, claims=[{"status": "weak"}], evidence_port=self.EvidencePort(), trust=TEST_TRUST)
        invalid = subprocess.run((sys.executable, "-c", evaluation), input=json.dumps({"garbage": True}), text=True, capture_output=True)
        self.assertNotEqual(invalid.returncode, 0)
        valid = subprocess.run((sys.executable, "-c", evaluation), input=json.dumps({"input": {"prediction": 1.0}, "output": {"score": 1.0}, "predictions": [1, 0], "targets": [1, 1]}), text=True, capture_output=True)
        self.assertEqual(json.loads(valid.stdout)["score"], 0.5)


if __name__ == "__main__":
    unittest.main()
