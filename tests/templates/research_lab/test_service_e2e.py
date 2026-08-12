from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor

from templates.research_lab.contracts import CoreRefs, ExperimentStage, ResearchError, ResearchProtocol, canonical_hash
from templates.research_lab.repository import ResearchRepository
from templates.research_lab.service import ResearchService

from .support import FakeCore, TEST_TRUST, signed


NOW = "2026-08-12T01:00:00+08:00"


def refs(workspace_id: str = "ws_1", project_id: str = "prj_1") -> CoreRefs:
    return CoreRefs(workspace_id, project_id, "tsk_tpl_v1_research_20260810", "plan_1", "run_1", "agt_c1")


def protocol(stage: ExperimentStage = ExperimentStage.CONFIRMATORY) -> ResearchProtocol:
    return ResearchProtocol("pro_1", 1, "Does the candidate improve the baseline?", "candidate > baseline", stage, "1" * 40, "dataset-snapshot-v1", "2" * 64, "accuracy", (7, 11), {"optimizer": "adam", "metric_direction": "maximize"})

def executor_receipt(attempt, operation, state):
    value = {"attempt_id": attempt["job_attempt_id"], "executor": attempt["executor"], "operation": operation, "state": state, "request_hash": "a" * 64, "authorization_receipt_hash": "b" * 64, "admission_receipt_hash": attempt["admission_receipt_hash"], "workspace_id": "ws_1", "project_id": "prj_1", "run_id": "run_1"}
    return signed(value, "research.execution-receipt/v1")


class ServiceE2ETests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = FakeCore()
        self.repository = ResearchRepository(self.core, TEST_TRUST)
        self.service = ResearchService(self.repository, now=lambda: NOW)
        self.repository.put(kind="research_project", record_id="rsp_1", refs=refs(), value={"research_project_id": "rsp_1", "created_at": NOW, "idempotency_key": "fixture-project"})
        self.service.record_domain_object(refs=refs(), kind="research_question", record_id="que_1", value={"question": "Does it improve?"}, idempotency_key="fixture-question")

    def test_reference_pipeline_uses_core_ids_and_separates_trials_attempts(self) -> None:
        project = self.service.create_project(refs=refs(), name="Reference", research_contract={"objective": "verified"}, idempotency_key="idem_project")
        experiment = self.service.create_experiment(refs=refs(), research_project_id=project["research_project_id"], question_id="que_1", protocol=protocol(), idempotency_key="idem_exp")
        trials = self.service.create_trials(refs=refs(), experiment_id=experiment["experiment_id"], protocol=protocol(), matrix=({"seed": 7, "role": "baseline"}, {"seed": 11, "role": "candidate"}))
        self.assertEqual(len(trials), 2)
        attempt1 = self.service.start_job_attempt(refs=refs(), trial_id=trials[0]["trial_id"], executor="local", compute_target_id="cmp_local", idempotency_key="idem_att_1")
        attempt2 = self.service.start_job_attempt(refs=refs(), trial_id=trials[1]["trial_id"], executor="local", compute_target_id="cmp_local", idempotency_key="idem_att_2")
        self.assertNotEqual(attempt1["job_attempt_id"], attempt2["job_attempt_id"])
        self.assertEqual({attempt1["trial_id"], attempt2["trial_id"]}, {trial["trial_id"] for trial in trials})
        self.assertEqual(attempt1["run_id"], "run_1")
        self.assertTrue(self.core.events)

    def test_project_create_is_idempotent(self) -> None:
        before = len(self.core.events)
        first = self.service.create_project(refs=refs(), name="Reference", research_contract={}, idempotency_key="same")
        second = self.service.create_project(refs=refs(), name="Reference", research_contract={}, idempotency_key="same")
        self.assertEqual(first, second)
        self.assertEqual(len(self.core.events), before + 1)

    def test_project_and_outbox_event_rollback_atomically(self) -> None:
        before_records = dict(self.core.records)
        before_events = dict(self.core.events)
        self.core.fail_event_commit = True
        with self.assertRaisesRegex(RuntimeError, "outbox unavailable"):
            self.service.create_project(refs=refs(), name="Atomic", research_contract={}, idempotency_key="atomic")
        self.assertEqual(self.core.records, before_records)
        self.assertEqual(self.core.events, before_events)

    def test_frozen_protocol_cannot_mutate(self) -> None:
        self.service.freeze_protocol(refs=refs(), experiment_id="exp_1", protocol=protocol(), idempotency_key="freeze")
        changed = ResearchProtocol("pro_1", 1, "Changed question?", "candidate > baseline", ExperimentStage.CONFIRMATORY, "1" * 40, "dataset-snapshot-v1", "2" * 64, "accuracy", (7, 11), {"optimizer": "adam"})
        with self.assertRaisesRegex(ResearchError, "cannot be mutated"):
            self.service.freeze_protocol(refs=refs(), experiment_id="exp_1", protocol=changed, idempotency_key="freeze2")

    def test_concurrent_attempt_is_blocked(self) -> None:
        experiment = self.service.create_experiment(refs=refs(), research_project_id="rsp_1", question_id="que_1", protocol=protocol(), idempotency_key="exp")
        trial = self.service.create_trials(refs=refs(), experiment_id=experiment["experiment_id"], protocol=protocol(), matrix=({"seed": 7},))[0]
        attempt = self.service.start_job_attempt(refs=refs(), trial_id=trial["trial_id"], executor="ssh", compute_target_id="cmp_gpu", idempotency_key="first")
        self.service.transition_attempt(refs=refs(), attempt_id=attempt["job_attempt_id"], target="submitted", expected_version=1, receipt=executor_receipt(attempt, "submit", "submitted"))
        with self.assertRaisesRegex(ResearchError, "non-terminal attempt"):
            self.service.start_job_attempt(refs=refs(), trial_id=trial["trial_id"], executor="ssh", compute_target_id="cmp_gpu", idempotency_key="second")

    def test_attempt_requires_core_target_budget_concurrency_retry_and_approval_admission(self) -> None:
        experiment = self.service.create_experiment(refs=refs(), research_project_id="rsp_1", question_id="que_1", protocol=protocol(), idempotency_key="exp-admission")
        trial = self.service.create_trials(refs=refs(), experiment_id=experiment["experiment_id"], protocol=protocol(), matrix=({"seed": 7},))[0]
        self.core.attempt_admission_allowed = False
        with self.assertRaisesRegex(ResearchError, "admission denied"):
            self.service.start_job_attempt(refs=refs(), trial_id=trial["trial_id"], executor="ssh", compute_target_id="cmp_gpu", idempotency_key="denied")

    def test_attempt_rejects_forged_executor_receipt_and_dangling_experiment(self) -> None:
        with self.assertRaisesRegex(ResearchError, "was not found"):
            self.service.create_experiment(refs=refs(), research_project_id="rsp_missing", question_id="que_1", protocol=protocol(), idempotency_key="dangling")
        experiment = self.service.create_experiment(refs=refs(), research_project_id="rsp_1", question_id="que_1", protocol=protocol(), idempotency_key="receipt-exp")
        trial = self.service.create_trials(refs=refs(), experiment_id=experiment["experiment_id"], protocol=protocol(), matrix=({"seed": 7},))[0]
        attempt = self.service.start_job_attempt(refs=refs(), trial_id=trial["trial_id"], executor="local", compute_target_id="cmp", idempotency_key="receipt-attempt")
        with self.assertRaisesRegex(ResearchError, "does not bind|signature|canonical"):
            self.service.transition_attempt(refs=refs(), attempt_id=attempt["job_attempt_id"], target="submitted", expected_version=attempt["version"], receipt={"receipt_hash": "x"})

    def test_concurrent_submit_allows_exactly_one_attempt(self) -> None:
        experiment = self.service.create_experiment(refs=refs(), research_project_id="rsp_1", question_id="que_1", protocol=protocol(), idempotency_key="exp-concurrent")
        trial = self.service.create_trials(refs=refs(), experiment_id=experiment["experiment_id"], protocol=protocol(), matrix=({"seed": 7},))[0]

        def submit(index: int):
            try:
                return self.service.start_job_attempt(refs=refs(), trial_id=trial["trial_id"], executor="ssh", compute_target_id="cmp_gpu", idempotency_key=f"concurrent-{index}")
            except ResearchError as exc:
                return exc.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(submit, (1, 2)))
        successes = [item for item in results if isinstance(item, dict)]
        conflicts = [item for item in results if item == "research.concurrent_attempt"]
        self.assertEqual((len(successes), len(conflicts)), (1, 1))

    def test_terminal_attempt_updates_trial_and_failed_attempt_can_retry(self) -> None:
        experiment = self.service.create_experiment(refs=refs(), research_project_id="rsp_1", question_id="que_1", protocol=protocol(), idempotency_key="exp-terminal")
        trial = self.service.create_trials(refs=refs(), experiment_id=experiment["experiment_id"], protocol=protocol(), matrix=({"seed": 7},))[0]
        attempt = self.service.start_job_attempt(refs=refs(), trial_id=trial["trial_id"], executor="local", compute_target_id="cmp_local", idempotency_key="attempt-terminal")
        submitted = self.service.transition_attempt(refs=refs(), attempt_id=attempt["job_attempt_id"], target="submitted", expected_version=1, receipt=executor_receipt(attempt, "submit", "submitted"))
        running = self.service.transition_attempt(refs=refs(), attempt_id=attempt["job_attempt_id"], target="running", expected_version=submitted["version"], receipt=executor_receipt(submitted, "status", "running"))
        failed = self.service.transition_attempt(refs=refs(), attempt_id=attempt["job_attempt_id"], target="failed", expected_version=running["version"], receipt=executor_receipt(running, "status", "failed"))
        self.assertEqual(failed["state"], "failed")
        observed_trial = self.repository.require(kind="trial", record_id=trial["trial_id"], workspace_id="ws_1", project_id="prj_1")
        self.assertEqual(observed_trial["state"], "failed")
        retry = self.service.start_job_attempt(refs=refs(), trial_id=trial["trial_id"], executor="local", compute_target_id="cmp_local", idempotency_key="attempt-retry")
        self.assertEqual(retry["attempt_number"], 2)

    def test_failed_attempt_rejects_unbound_or_noncanonical_executor_receipt(self) -> None:
        experiment = self.service.create_experiment(refs=refs(), research_project_id="rsp_1", question_id="que_1", protocol=protocol(), idempotency_key="exp-failed-receipt")
        trial = self.service.create_trials(refs=refs(), experiment_id=experiment["experiment_id"], protocol=protocol(), matrix=({"seed": 7},))[0]
        attempt = self.service.start_job_attempt(refs=refs(), trial_id=trial["trial_id"], executor="local", compute_target_id="cmp", idempotency_key="failed-receipt")
        submitted = self.service.transition_attempt(refs=refs(), attempt_id=attempt["job_attempt_id"], target="submitted", expected_version=attempt["version"], receipt=executor_receipt(attempt, "submit", "submitted"))
        running = self.service.transition_attempt(refs=refs(), attempt_id=attempt["job_attempt_id"], target="running", expected_version=submitted["version"], receipt=executor_receipt(submitted, "status", "running"))
        with self.assertRaisesRegex(ResearchError, "does not bind|signature|canonical"):
            self.service.transition_attempt(refs=refs(), attempt_id=attempt["job_attempt_id"], target="failed", expected_version=running["version"], receipt={"attempt_id": "other", "state": "completed", "receipt_hash": "NOT-A-HASH"})

    def test_cross_workspace_read_isolated(self) -> None:
        self.service.create_project(refs=refs(), name="Private", research_contract={}, idempotency_key="private")
        self.assertEqual(self.repository.list(kind="research_project", workspace_id="ws_other", project_id="prj_1"), [])

    def test_cross_project_read_and_overwrite_are_isolated(self) -> None:
        self.core.valid_refs.add("prj_2")
        self.service.record_domain_object(refs=refs(), kind="research_question", record_id="rq_shared", value={"question": "private one"}, idempotency_key="p1")
        self.assertIsNone(self.repository.get(kind="research_question", record_id="rq_shared", workspace_id="ws_1", project_id="prj_2"))
        self.service.record_domain_object(refs=refs(project_id="prj_2"), kind="research_question", record_id="rq_shared", value={"question": "private two"}, idempotency_key="p2")
        self.assertEqual(self.repository.require(kind="research_question", record_id="rq_shared", workspace_id="ws_1", project_id="prj_1")["question"], "private one")

    def test_all_auxiliary_domain_objects_are_core_backed(self) -> None:
        self.core.add_core_record("artifact", "art_aux", run_id="run_1", sha256="b" * 64, sha256_verified=True)
        samples = {
            "research_contract": {"objective": "bounded"},
            "research_question": {"question": "Does it improve?"},
            "literature_evidence": {"verification_status": "unavailable"},
            "compute_target": {"state": "unavailable", "reason_code": "no_gpu_target"},
            "research_artifact": {"artifact_id": "art_aux", "sha256": "b" * 64},
        }
        for index, (kind, value) in enumerate(samples.items()):
            stored = self.service.record_domain_object(refs=refs(), kind=kind, record_id=f"rec_{index}", value=value, idempotency_key=f"idem_{index}")
            self.assertEqual(stored["workspace_id"], "ws_1")
        for kind in ("claim_evidence", "manuscript", "research_receipt"):
            with self.assertRaisesRegex(ResearchError, "not registered"):
                self.service.record_domain_object(refs=refs(), kind=kind, record_id=f"forged_{kind}", value={"canonical": True}, idempotency_key=f"forged_{kind}")

    def test_claim_self_review_is_forbidden(self) -> None:
        with self.assertRaisesRegex(ResearchError, "independent"):
            self.service.decide_claim(refs=refs(), claim_id="clm_1", statement="candidate wins", stage="confirmatory", evidence=[], reviewer_id="agt_c1")

    def test_claim_and_evidence_chain_require_core_readback(self) -> None:
        experiment = self.service.create_experiment(refs=refs(), research_project_id="rsp_1", question_id="que_1", protocol=protocol(), idempotency_key="claim-exp")
        trial_records = self.service.create_trials(
            refs=refs(), experiment_id=experiment["experiment_id"], protocol=protocol(),
            matrix=({"seed": 7, "role": "baseline"}, {"seed": 11, "role": "baseline"}, {"seed": 7, "role": "candidate"}, {"seed": 11, "role": "candidate"}),
        )
        evidence = []
        for trial, (role, seed) in zip(trial_records, (("baseline", 7), ("baseline", 11), ("candidate", 7), ("candidate", 11))):
            attempt = self.service.start_job_attempt(refs=refs(), trial_id=trial["trial_id"], executor="local", compute_target_id="cmp_local", idempotency_key=f"claim-{role}-{seed}")
            version = attempt["version"]
            for state in ("submitted", "running", "completed"):
                operation = {"submitted": "submit", "running": "status", "completed": "collect"}[state]
                attempt = self.service.transition_attempt(refs=refs(), attempt_id=attempt["job_attempt_id"], target=state, expected_version=version, receipt=executor_receipt(attempt, operation, state))
                version = attempt["version"]
            metric_id, figure_id, evaluation_id = f"art_metric_{role}_{seed}", f"art_figure_{role}_{seed}", f"eval_{role}_{seed}"
            self.core.add_core_record("artifact", metric_id, run_id="run_1", job_attempt_id=attempt["job_attempt_id"], sha256_verified=True)
            self.core.add_core_record("artifact", figure_id, run_id="run_1", job_attempt_id=attempt["job_attempt_id"], sha256_verified=True)
            self.core.add_core_record("evaluation", evaluation_id, run_id="run_1", job_attempt_id=attempt["job_attempt_id"], metric_artifact_id=metric_id, figure_table_artifact_id=figure_id, reviewer_id="usr_reviewer", claim_id="clm_supported", claim_statement_hash=canonical_hash({"statement": "candidate wins"}), protocol_hash=protocol().protocol_hash, metric_name="accuracy", metric_direction="maximize", supports_claim=True, support_strength="strong", status="passed")
            evidence.append({"evidence_id": f"ev_{role}_{seed}", "protocol_hash": protocol().protocol_hash, "code_commit": protocol().code_commit, "dataset_version": protocol().dataset_version, "environment_lock_hash": protocol().environment_lock_hash, "seed": seed, "run_id": "run_1", "job_attempt_id": attempt["job_attempt_id"], "metric_artifact_id": metric_id, "figure_table_artifact_id": figure_id, "evaluation_id": evaluation_id, "role": role})
        saved, decision = self.service.decide_claim(refs=refs(), claim_id="clm_supported", statement="candidate wins", stage="confirmatory", evidence=evidence, reviewer_id="usr_reviewer")
        self.assertTrue(decision.eligible)
        chain = self.service.validate_core_evidence_chain(refs=refs(), artifact_ids=[evidence[0]["metric_artifact_id"]], evaluation_ids=[evidence[0]["evaluation_id"]])
        self.assertTrue(chain["verified"])
        self.assertEqual(saved["reviewer_id"], "usr_reviewer")
        self.assertEqual(len(saved["claim_evidence_ids"]), 4)
        with self.assertRaisesRegex(ResearchError, "frozen Protocol"):
            self.service.decide_claim(refs=refs(), claim_id="clm_supported", statement="candidate wins", stage="smoke", evidence=evidence, reviewer_id="usr_reviewer", expected_version=saved["version"])
        with self.assertRaisesRegex(ResearchError, "Claim, Protocol"):
            self.service.decide_claim(refs=refs(), claim_id="clm_unrelated", statement="unrelated statement", stage="confirmatory", evidence=evidence, reviewer_id="usr_reviewer")
        missing = [dict(item) for item in evidence]
        missing[0]["evaluation_id"] = "eval_missing"
        with self.assertRaisesRegex(ResearchError, "readback failed"):
            self.service.decide_claim(refs=refs(), claim_id="clm_fake", statement="fake", stage="confirmatory", evidence=missing, reviewer_id="usr_reviewer")

        cross_run = [dict(item) for item in evidence]
        cross_run[0]["run_id"] = "run_other"
        self.core.add_core_record("run", "run_other", status="completed", plan_id="plan_1", task_id="tsk_tpl_v1_research_20260810")
        with self.assertRaisesRegex(ResearchError, "current MIS Run"):
            self.service.decide_claim(refs=refs(), claim_id="clm_cross_run", statement="fake", stage="confirmatory", evidence=cross_run, reviewer_id="usr_reviewer")


if __name__ == "__main__":
    unittest.main()
