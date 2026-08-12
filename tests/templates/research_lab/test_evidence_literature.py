from __future__ import annotations

import unittest

from templates.research_lab.contracts import ResearchError, evaluate_protocol_deviation, canonical_hash
from templates.research_lab.evidence import EvidenceGraph, evaluate_claim
from templates.research_lab.literature import LiteratureRecord, deduplicate, normalize_source_url, validate_resolved_addresses, verify_citation_claims
from .support import TEST_TRUST, signed


def evidence(role: str, seed: int, protocol_hash: str = "a" * 64, **changes):
    value = {"evidence_id": f"ev_{role}_{seed}", "protocol_hash": protocol_hash, "code_commit": "b" * 40, "dataset_version": "data-v1", "environment_lock_hash": "c" * 64, "seed": seed, "run_id": "run_1", "run_status": "completed", "job_attempt_id": f"att_{seed}", "metric_artifact_id": f"art_metric_{seed}", "figure_table_artifact_id": f"art_figure_{seed}", "evaluation_id": f"eval_{seed}", "reviewer_id": "usr_reviewer", "claim_id": "clm_1", "claim_statement_hash": "d" * 64, "metric_name": "accuracy", "metric_direction": "maximize", "evaluation_support_strength": "strong", "artifact_integrity": "verified", "evaluation_status": "passed", "role": role}
    value.update(changes)
    return value


class EvidenceLiteratureTests(unittest.TestCase):
    def test_supported_numeric_claim_requires_baseline_candidate_and_seeds(self) -> None:
        decision = evaluate_claim(stage="confirmatory", evidence=[evidence("baseline", 7), evidence("baseline", 11), evidence("candidate", 7), evidence("candidate", 11)])
        self.assertTrue(decision.eligible)
        self.assertEqual(decision.status.value, "supported")

    def test_smoke_and_unsupported_evidence_are_blocked(self) -> None:
        decision = evaluate_claim(stage="smoke", evidence=[evidence("candidate", 7, artifact_integrity="unverified")])
        self.assertFalse(decision.eligible)
        self.assertIn("stage_not_claim_eligible", decision.reasons)

    def test_cross_protocol_comparison_is_blocked(self) -> None:
        decision = evaluate_claim(stage="confirmatory", evidence=[evidence("baseline", 7), evidence("baseline", 11), evidence("candidate", 7, protocol_hash="d" * 64), evidence("candidate", 11, protocol_hash="d" * 64)])
        self.assertIn("cross_protocol_evidence", decision.reasons)

    def test_invalidation_propagates_and_cycles_fail(self) -> None:
        graph = EvidenceGraph([("artifact", "evaluation"), ("evaluation", "claim"), ("claim", "manuscript")])
        self.assertEqual(graph.invalidate_from("evaluation"), ("claim", "evaluation", "manuscript"))
        with self.assertRaisesRegex(ResearchError, "acyclic"):
            EvidenceGraph([("a", "b"), ("b", "a")])

    def test_literature_dedup_and_citation_locator(self) -> None:
        one = LiteratureRecord.create(title="Paper", authors=["A Author"], year=2026, source_url="https://doi.org/10.1000/example", doi="10.1000/EXAMPLE", arxiv_id=None, verification_status="verified", verified_at="2026-08-12T00:00:00Z", locator="p. 3", source_artifact_id="art_source")
        two = LiteratureRecord.create(title="Paper", authors=["A Author"], year=2026, source_url="https://example.org/paper", doi="https://doi.org/10.1000/example", arxiv_id=None, verification_status="unavailable", verified_at="2026-08-12T00:00:00Z", locator="p. 3", source_artifact_id="art_source2")
        self.assertEqual(len(deduplicate([one, two])), 1)
        class Port:
            def verify_citation_evidence(self, **kwargs): return {}
        result = verify_citation_claims([{"claim_id": "clm_1", "literature_id": one.literature_id, "locator": "", "source_excerpt_hash": "a" * 64}], {one.literature_id: one}, Port(), TEST_TRUST)
        self.assertFalse(result[0]["supported"])
        class VerifiedPort:
            def verify_citation_evidence(self, **kwargs):
                return signed({"verified":True, "reference_hash":canonical_hash(kwargs), "literature_id":kwargs["literature_id"], "source_artifact_id":kwargs["source_artifact_id"]}, "research.citation-evidence/v1")
        result = verify_citation_claims([{"claim_id": "clm_1", "literature_id": one.literature_id, "locator": "p. 3", "source_excerpt_hash": "a" * 64}], {one.literature_id: one}, VerifiedPort(), TEST_TRUST)
        self.assertTrue(result[0]["supported"])
        class ForgedPort:
            def verify_citation_evidence(self, **kwargs): return {"verified": True, "reference_hash": canonical_hash(kwargs), "receipt_hash": "0" * 64}
        forged = verify_citation_claims([{"claim_id": "clm_1", "literature_id": one.literature_id, "locator": "p. 3", "source_excerpt_hash": "a" * 64}], {one.literature_id: one}, ForgedPort(), TEST_TRUST)
        self.assertFalse(forged[0]["supported"])

    def test_source_url_rejects_local_and_credentials(self) -> None:
        for url in ("http://example.org", "https://localhost/paper", "https://169.254.169.254/latest/meta-data", "https://10.0.0.1/paper", "https://user:pass@example.org/paper"):
            with self.subTest(url=url), self.assertRaises(ResearchError):
                normalize_source_url(url)
        with self.assertRaisesRegex(ResearchError, "non-public"):
            validate_resolved_addresses(("127.0.0.1",))
        self.assertEqual(validate_resolved_addresses(("8.8.8.8",)), ("8.8.8.8",))

    def test_protocol_deviation_fails_on_unobserved_or_changed_actuals(self) -> None:
        result = evaluate_protocol_deviation(expected={"dataset": "v1", "precision": "fp32"}, actual={"dataset": "v2"})
        self.assertEqual(result["status"], "deviated")
        self.assertIn("precision", result["missing_actual_fields"])
        self.assertIn("dataset", result["unresolved_fields"])


if __name__ == "__main__":
    unittest.main()
