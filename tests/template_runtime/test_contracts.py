from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError:  # Production validator stays dependency-free; CI may add schema checks.
    Draft202012Validator = None

from template_runtime.contracts import (
    canonical_json_sha256,
    ContractViolation,
    EVENT_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    PROFILE_CONTRACT_VERSION,
    TEMPLATE_LIFECYCLE_TRANSITIONS,
    manifest_content_sha256,
    validate_lifecycle_transition,
    validate_event_envelope,
    validate_product_profile,
    validate_template_manifest,
)

ROOT = Path(__file__).resolve().parents[2]


def manifest() -> dict:
    template_id = "research_lab"
    def declaration(suffix: str, **extra: object) -> dict:
        return {
            "id": f"{template_id}.{suffix}",
            "version": "1.0.0",
            "contract_version": "template-sdk/v1",
            "entrypoint": f"research_lab.{suffix}",
            **extra,
        }
    candidate = {
        "schema_version": MANIFEST_SCHEMA_VERSION,
        "id": template_id,
        "name": "Research Lab",
        "version": "1.0.0",
        "category": "research",
        "description": "Governed research workflow.",
        "publisher": "agentops-mis",
        "license": "Proprietary",
        "min_mis_version": "1.6.0",
        "runtime_dependencies": [],
        "capabilities": ["research"],
        "domain_objects": [
            {
                "id": "research_lab.domain.experiment",
                "name": "Experiment",
                "authority": "template_domain",
            },
            {
                "name": "Run",
                "authority": "mis_core_reference",
                "core_authority_id": "mis_core.run",
            },
        ],
        "workflows": [declaration("workflow.default")],
        "agents": [declaration("agent.lead")],
        "skills": [declaration("skill.plan")],
        "tools": [
            declaration(
                "tool.local", risk="low", side_effect="none", approval="never"
            )
        ],
        "policies": [declaration("policy.claim_gate")],
        "evaluators": [declaration("evaluator.evidence")],
        "memory": {
            "candidate_only": True,
            "source_refs_required": True,
            "shared_memory": "deny_by_default",
            "conflict_policy": "stale_or_superseded",
        },
        "ui_extensions": [
            declaration(
                "ui.home",
                route="/solutions/research_lab/home",
                nav_label="Research Home",
                permission="research_lab.permission.read",
            )
        ],
        "reports": [declaration("report.receipt")],
        "fixtures": [declaration("fixture.smoke")],
        "migrations": [
            declaration(
                "migration.1_0_0",
                from_version="0.0.0",
                to_version="1.0.0",
                checksum="c" * 64,
                reversible=True,
            )
        ],
        "permissions": [
            declaration(
                "permission.read",
                action="research_lab.permission.read",
                scope="template",
                risk="low",
                default="allow",
            )
        ],
        "api_routes": [declaration("api.experiments")],
        "cli_commands": [declaration("cli.experiments")],
        "testing_hooks": [declaration("testing.contract")],
        "exports": [declaration("export.reproducibility")],
        "upgrade_policy": {
            "preview_required": True,
            "approval_required": True,
            "backup_required": True,
            "rollback_required": True,
            "readback_required": True,
            "receipt_required": True,
            "compatibility": "semver",
        },
        "uninstall_policy": {
            "preview_required": True,
            "approval_required": True,
            "readback_required": True,
            "receipt_required": True,
            "archive_history": True,
            "data_policy": "archive",
        },
        "provenance": {
            "source_repository": "geogejoy107-jpg/agentops-mis-mvp",
            "source_commit": "a" * 40,
            "built_at": "2026-08-10T00:00:00Z",
        },
        "integrity": {
            "algorithm": "sha256",
            "content_sha256": "0" * 64,
            "signature": {"status": "unsigned_candidate"},
        },
    }
    candidate["integrity"]["content_sha256"] = manifest_content_sha256(candidate)
    return candidate


class ContractTests(unittest.TestCase):
    def test_manifest_accepts_namespaced_domain_contract(self) -> None:
        self.assertEqual(validate_template_manifest(manifest())["id"], "research_lab")

    def test_manifest_rejects_cross_template_namespace(self) -> None:
        for field in ("tools", "permissions", "workflows", "ui_extensions"):
            with self.subTest(field=field):
                candidate = manifest()
                candidate[field][0]["id"] = "quant_research.foreign"
                with self.assertRaisesRegex(ContractViolation, "safe namespace under research_lab"):
                    validate_template_manifest(candidate)

    def test_manifest_rejects_path_like_namespace(self) -> None:
        candidate = manifest()
        candidate["tools"][0]["id"] = "research_lab../../foreign"
        candidate["integrity"]["content_sha256"] = manifest_content_sha256(candidate)
        with self.assertRaisesRegex(ContractViolation, "safe namespace"):
            validate_template_manifest(candidate)

    def test_manifest_rejects_unknown_field(self) -> None:
        candidate = manifest()
        candidate["production_override"] = True
        with self.assertRaisesRegex(ContractViolation, "unknown top-level"):
            validate_template_manifest(candidate)

    def test_manifest_rejects_duplicate_core_authority(self) -> None:
        candidate = manifest()
        candidate["domain_objects"][1]["authority"] = "template_domain"
        with self.assertRaisesRegex(ContractViolation, "duplicates MIS Core authority Run"):
            validate_template_manifest(candidate)

    def test_manifest_rejects_spaced_core_authority_alias(self) -> None:
        candidate = manifest()
        candidate["domain_objects"].append(
            {
                "id": "research_lab.domain.memory_review",
                "name": "Memory Review",
                "authority": "template_domain",
            }
        )
        candidate["integrity"]["content_sha256"] = manifest_content_sha256(candidate)
        with self.assertRaisesRegex(ContractViolation, "duplicates MIS Core authority"):
            validate_template_manifest(candidate)

    def test_manifest_rejects_nested_shape_drift(self) -> None:
        candidates = []
        for field, value in (
            ("runtime_dependencies", [1]),
            ("capabilities", [1, "x", "x"]),
            ("domain_objects", [1]),
            ("domain_objects", [{}]),
        ):
            candidate = manifest()
            candidate[field] = value
            candidate["integrity"]["content_sha256"] = manifest_content_sha256(candidate)
            candidates.append(candidate)
        candidate = manifest()
        candidate["provenance"]["extra"] = True
        candidate["integrity"]["content_sha256"] = manifest_content_sha256(candidate)
        candidates.append(candidate)
        for index, candidate in enumerate(candidates):
            with self.subTest(index=index), self.assertRaises(ContractViolation):
                validate_template_manifest(candidate)

    @unittest.skipIf(Draft202012Validator is None, "jsonschema is not installed")
    def test_json_schema_and_python_align_on_security_boundaries(self) -> None:
        schema = json.loads(
            (ROOT / "template_runtime/schemas/template-manifest-v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        candidates = []
        candidate = manifest()
        candidate["integrity"]["signature"] = {
            "status": "verified",
            "algorithm": "rsa",
            "key_id": "release-key-1",
            "value": "signed-value",
        }
        candidates.append(candidate)
        candidate = manifest()
        candidate["runtime_dependencies"] = [
            {"id": "openjiuwen", "kind": "runtime", "version": "01.2.3"}
        ]
        candidates.append(candidate)
        candidate = manifest()
        candidate["domain_objects"][1]["core_authority_id"] = "mis_core.fake"
        candidates.append(candidate)
        for index, candidate in enumerate(candidates):
            candidate["integrity"]["content_sha256"] = manifest_content_sha256(
                candidate
            )
            with self.subTest(index=index):
                self.assertTrue(list(validator.iter_errors(candidate)))
                with self.assertRaises(ContractViolation):
                    validate_template_manifest(candidate)

    def test_manifest_rejects_executable_and_identity_drift(self) -> None:
        candidates = []
        candidate = manifest()
        candidate["domain_objects"][0]["exec"] = "run"
        candidates.append(candidate)
        candidate = manifest()
        candidate["domain_objects"].append(dict(candidate["domain_objects"][0]))
        candidates.append(candidate)
        candidate = manifest()
        candidate["domain_objects"][1]["core_authority_id"] = "mis_core.task"
        candidates.append(candidate)
        candidate = manifest()
        candidate["tools"][0]["entrypoint"] = "../../outside:run"
        candidates.append(candidate)
        candidate = manifest()
        candidate["runtime_dependencies"] = [
            {"id": "openjiuwen", "kind": "python", "version": "latest"}
        ]
        candidates.append(candidate)
        candidate = manifest()
        candidate["permissions"][0]["action"] = "read"
        candidates.append(candidate)
        candidate = manifest()
        candidate["ui_extensions"][0]["route"] += "?redirect=https://example.com"
        candidates.append(candidate)
        for index, candidate in enumerate(candidates):
            candidate["integrity"]["content_sha256"] = manifest_content_sha256(candidate)
            with self.subTest(index=index), self.assertRaises(ContractViolation):
                validate_template_manifest(candidate)

    def test_manifest_rejects_invalid_provenance(self) -> None:
        candidate = manifest()
        candidate["provenance"]["source_commit"] = "not-a-commit"
        candidate["provenance"]["built_at"] = "tomorrow"
        candidate["integrity"]["content_sha256"] = manifest_content_sha256(candidate)
        with self.assertRaisesRegex(ContractViolation, "source_commit"):
            validate_template_manifest(candidate)

    def test_manifest_rejects_unverified_signature_claim(self) -> None:
        candidate = manifest()
        candidate["integrity"]["signature"] = {"status": "verified"}
        with self.assertRaisesRegex(ContractViolation, "required when verified"):
            validate_template_manifest(candidate)

    def test_manifest_verified_signature_requires_trusted_verifier(self) -> None:
        candidate = manifest()
        candidate["integrity"]["signature"] = {
            "status": "verified",
            "algorithm": "ed25519",
            "key_id": "release-key-1",
            "value": "signed-value",
        }
        with self.assertRaisesRegex(ContractViolation, "trusted signature verifier"):
            validate_template_manifest(candidate)
        seen_payloads = []

        def verifier(payload, signature):
            seen_payloads.append(payload)
            return {
                "verified": True,
                "algorithm": "ed25519",
                "key_id": "release-key-1",
                "payload_sha256": candidate["integrity"]["content_sha256"],
                "trust_store_hash": "d" * 64,
                "revocation_checked": True,
                "receipt_id": "sig_rcp_1",
                "receipt_hash": "e" * 64,
            }

        self.assertEqual(
            validate_template_manifest(
                candidate,
                signature_verifier=verifier,
            )["id"],
            "research_lab",
        )
        self.assertEqual(len(seen_payloads), 1)
        self.assertNotIn("integrity", seen_payloads[0])
        self.assertEqual(
            canonical_json_sha256(seen_payloads[0]),
            candidate["integrity"]["content_sha256"],
        )
        with self.assertRaisesRegex(ContractViolation, "trusted signature"):
            validate_template_manifest(
                candidate, signature_verifier=lambda payload, signature: {"verified": True}
            )

    def test_manifest_rejects_tampered_payload(self) -> None:
        candidate = manifest()
        candidate["description"] = "Tampered after hashing"
        with self.assertRaisesRegex(ContractViolation, "does not match"):
            validate_template_manifest(candidate)

    def test_manifest_enforces_tool_risk_and_permission_references(self) -> None:
        candidates = []
        candidate = manifest()
        candidate["tools"][0].update(
            risk="high", side_effect="external_write", approval="never"
        )
        candidates.append(candidate)
        candidate = manifest()
        candidate["permissions"][0].update(risk="high", default="allow")
        candidates.append(candidate)
        candidate = manifest()
        candidate["ui_extensions"][0]["permission"] = (
            "research_lab.permission.missing"
        )
        candidates.append(candidate)
        for index, candidate in enumerate(candidates):
            candidate["integrity"]["content_sha256"] = manifest_content_sha256(
                candidate
            )
            with self.subTest(index=index), self.assertRaises(ContractViolation):
                validate_template_manifest(candidate)

    def test_event_requires_template_namespace_and_sequence(self) -> None:
        event = {
            "event_id": "evt_1",
            "event_type": "career_sim.month.completed",
            "schema_version": EVENT_SCHEMA_VERSION,
            "workspace_id": "ws_1",
            "project_id": "prj_1",
            "template_id": "career_sim",
            "profile_id": "bdci_2026_career",
            "task_id": "tsk_1",
            "run_id": "run_1",
            "actor": {"type": "agent", "id": "agt_1"},
            "occurred_at": "2026-08-10T00:00:00Z",
            "idempotency_key": "career_sim:month:1",
            "correlation_id": "corr_1",
            "sequence": 1,
            "payload": {},
            "evidence_refs": [],
        }
        self.assertEqual(validate_event_envelope(event)["sequence"], 1)
        invalid = copy.deepcopy(event)
        invalid["event_type"] = "research_lab.month.completed"
        with self.assertRaisesRegex(ContractViolation, "namespaced"):
            validate_event_envelope(invalid)

    def test_event_rejects_schema_drift(self) -> None:
        event = {
            "event_id": "",
            "event_type": "career_sim.month.completed",
            "schema_version": EVENT_SCHEMA_VERSION,
            "workspace_id": "",
            "project_id": None,
            "template_id": "career_sim",
            "profile_id": None,
            "task_id": None,
            "run_id": None,
            "actor": {},
            "occurred_at": "not-a-date",
            "idempotency_key": "",
            "correlation_id": "",
            "sequence": True,
            "payload": {},
            "evidence_refs": [1],
            "unexpected": True,
        }
        with self.assertRaises(ContractViolation) as raised:
            validate_event_envelope(event)
        message = str(raised.exception)
        for expected in (
            "unknown event fields",
            "sequence",
            "workspace_id",
            "occurred_at",
            "evidence_refs",
        ):
            self.assertIn(expected, message)

    def test_event_rejects_path_namespace_and_nullable_id_types(self) -> None:
        event = {
            "event_id": "evt_1",
            "event_type": "career_sim../../foreign",
            "schema_version": EVENT_SCHEMA_VERSION,
            "workspace_id": "ws_1",
            "project_id": 123,
            "template_id": "career_sim",
            "profile_id": 123,
            "task_id": 123,
            "run_id": 123,
            "actor": {},
            "occurred_at": "2026-08-10 00:00:00+00:00",
            "idempotency_key": "key",
            "correlation_id": "corr",
            "sequence": 1,
            "payload": {},
            "evidence_refs": ["   "],
        }
        with self.assertRaises(ContractViolation) as raised:
            validate_event_envelope(event)
        message = str(raised.exception)
        for expected in ("namespaced", "project_id", "occurred_at", "evidence_refs"):
            self.assertIn(expected, message)

    def test_product_profile_contract(self) -> None:
        profile = {
            "schema_version": PROFILE_CONTRACT_VERSION,
            "id": "bdci_2026_quant",
            "template_id": "quant_research",
            "name": "BDCI Quant",
            "version": "1.0.0",
            "description": "Research-only quant profile.",
            "configuration": {"live_trading": False},
            "budgets": {"model_usd": 3},
            "policies": [],
            "evaluators": [],
            "submission": {"format": "zip"},
        }
        self.assertEqual(validate_product_profile(profile)["id"], "bdci_2026_quant")

    def test_product_profile_rejects_schema_drift(self) -> None:
        profile = {
            "schema_version": PROFILE_CONTRACT_VERSION,
            "id": "bdci_2026_quant",
            "template_id": "quant_research",
            "name": "",
            "version": "1.0.0",
            "description": "",
            "configuration": {},
            "budgets": {},
            "policies": [{"id": "career_sim.foreign"}],
            "evaluators": ["not-an-object"],
            "submission": {},
            "unexpected": True,
        }
        with self.assertRaises(ContractViolation) as raised:
            validate_product_profile(profile)
        message = str(raised.exception)
        for expected in ("unknown profile", "name", "description", "safe namespace"):
            self.assertIn(expected, message)

    def test_lifecycle_has_no_implicit_success_or_terminal_escape(self) -> None:
        self.assertNotIn("installed", TEMPLATE_LIFECYCLE_TRANSITIONS["pending_approval"])
        self.assertNotIn("installed", TEMPLATE_LIFECYCLE_TRANSITIONS["installing"])
        self.assertNotIn("active", TEMPLATE_LIFECYCLE_TRANSITIONS["upgrading"])
        self.assertNotIn("archived", TEMPLATE_LIFECYCLE_TRANSITIONS["uninstalling"])
        self.assertIn("install_readback", TEMPLATE_LIFECYCLE_TRANSITIONS["installing"])
        self.assertIn(
            "uninstall_receipt_pending",
            TEMPLATE_LIFECYCLE_TRANSITIONS["uninstall_readback"],
        )
        self.assertEqual(TEMPLATE_LIFECYCLE_TRANSITIONS["archived"], frozenset())

    def test_lifecycle_success_edges_require_evidence(self) -> None:
        with self.assertRaisesRegex(ContractViolation, "approval_id"):
            validate_lifecycle_transition("pending_approval", "installing")
        validate_lifecycle_transition(
            "pending_approval",
            "installing",
            {
                "approval_id": "apr_1",
                "approval_status": "approved",
                "action_hash": "a" * 64,
            },
        )
        with self.assertRaisesRegex(ContractViolation, "action_hash must"):
            validate_lifecycle_transition(
                "pending_approval",
                "installing",
                {
                    "approval_id": "apr_1",
                    "approval_status": "approved",
                    "action_hash": "not-a-hash",
                },
            )
        with self.assertRaisesRegex(ContractViolation, "transaction_id"):
            validate_lifecycle_transition("installing", "install_readback")
        with self.assertRaisesRegex(ContractViolation, "receipt_id"):
            validate_lifecycle_transition("install_receipt_pending", "installed")
        validate_lifecycle_transition(
            "install_receipt_pending",
            "installed",
            {"receipt_id": "rcp_1", "receipt_hash": "b" * 64},
        )
        with self.assertRaisesRegex(ContractViolation, "previous_state"):
            validate_lifecycle_transition("upgrade_rejected", "active")
        validate_lifecycle_transition(
            "upgrade_rejected",
            "active",
            {
                "previous_state": "active",
                "state_snapshot_hash": "c" * 64,
                "receipt_id": "rcp_reject_1",
                "receipt_hash": "d" * 64,
            },
        )
        for current in ("disable_rejected", "disable_approval_expired", "disable_failed"):
            with self.subTest(current=current), self.assertRaisesRegex(
                ContractViolation, "previous_state"
            ):
                validate_lifecycle_transition(current, "active")


if __name__ == "__main__":
    unittest.main()
