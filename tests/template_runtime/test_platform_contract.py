from __future__ import annotations

import json
import unittest
from pathlib import Path

from template_runtime.contracts import (
    CORE_AUTHORITY_IDS,
    EVENT_SCHEMA_VERSION,
    MANIFEST_SCHEMA_VERSION,
    MIGRATION_CONTRACT_VERSION,
    PROFILE_CONTRACT_VERSION,
    RUNTIME_CONTRACT_VERSION,
    SHARED_API_VERSION,
)
from template_runtime.protocols import (
    OpenJiuwenRuntimePort,
    TemplateLifecyclePort,
    TemplateMigrationPort,
    TemplateRegistryPort,
    TemplateSDKPort,
    TransactionalOutboxPort,
)

ROOT = Path(__file__).resolve().parents[2]


class PlatformContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(
            (ROOT / "template_runtime/platform-contract-v1.json").read_text(
                encoding="utf-8"
            )
        )

    def test_machine_contract_versions_match_python(self) -> None:
        self.assertEqual(
            self.contract["versions"],
            {
                "manifest": MANIFEST_SCHEMA_VERSION,
                "api": SHARED_API_VERSION,
                "event": EVENT_SCHEMA_VERSION,
                "runtime": RUNTIME_CONTRACT_VERSION,
                "migration": MIGRATION_CONTRACT_VERSION,
                "profile": PROFILE_CONTRACT_VERSION,
                "sdk": "template-sdk/v1",
            },
        )

    def test_machine_authority_ids_match_python(self) -> None:
        self.assertEqual(set(self.contract["authority"]["ids"]), set(CORE_AUTHORITY_IDS))
        self.assertEqual(self.contract["authority"]["owner"], "mis_core")

    def test_all_shared_ports_are_runtime_checkable_contracts(self) -> None:
        for port in (
            TemplateRegistryPort,
            TemplateLifecyclePort,
            TransactionalOutboxPort,
            TemplateMigrationPort,
            OpenJiuwenRuntimePort,
            TemplateSDKPort,
        ):
            self.assertTrue(getattr(port, "_is_runtime_protocol", False))

    def test_production_contract_has_required_gates(self) -> None:
        families = set(self.contract["required_test_families"])
        self.assertTrue(
            {
                "lifecycle_receipts",
                "migration_backup_rollback",
                "outbox_replay_dlq",
                "permission_approval",
                "runtime_real_compatibility",
                "cross_template_isolation",
                "real_domain_e2e",
                "release_readback",
            }.issubset(families)
        )
        self.assertEqual(self.contract["runtime"]["false_success"], "deny")
        self.assertTrue(self.contract["signature_trust"]["trust_store_required"])

    def test_domain_paths_are_disjoint(self) -> None:
        owners: dict[str, str] = {}
        for line, paths in self.contract["domain_paths"].items():
            for path in paths:
                self.assertNotIn(path, owners)
                owners[path] = line
                self.assertNotIn("..", path)


if __name__ == "__main__":
    unittest.main()
