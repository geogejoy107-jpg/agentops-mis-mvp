from __future__ import annotations

import json
import importlib
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from template_runtime.contracts import ContractViolation, validate_product_profile, validate_template_manifest
from templates.research_lab.manifest import build_manifest
from .c0_snapshot import exported_c0

ROOT = Path(__file__).resolve().parents[3]


class ContractManifestProfileTests(unittest.TestCase):
    def test_generated_and_committed_manifests_match_and_validate(self) -> None:
        generated = build_manifest()
        committed = json.loads((ROOT / "templates/research_lab/manifest.json").read_text())
        self.assertEqual(committed, generated)
        self.assertEqual(validate_template_manifest(committed)["id"], "research_lab")
        self.assertFalse(committed.get("canonical", False))
        names = {item["name"] for item in committed["domain_objects"] if item["authority"] == "template_domain"}
        self.assertEqual(len(names), 16)
        self.assertIn("ResearchReceipt", names)
        self.assertIn("JobAttempt", names)

    def test_profiles_validate_and_reference_research_namespace(self) -> None:
        for relative in ("profiles/bdci_2026_research/profile.json", "profiles/research_lab_full/profile.json"):
            with self.subTest(relative=relative):
                profile = json.loads((ROOT / relative).read_text())
                self.assertEqual(validate_product_profile(profile)["template_id"], "research_lab")
                self.assertTrue(all(item["id"].startswith("research_lab.") for field in ("policies", "evaluators") for item in profile[field]))

    def test_manifest_fails_closed_on_core_authority_duplication(self) -> None:
        manifest = build_manifest()
        manifest["domain_objects"].append({"id": "research_lab.domain.approval", "name": "Approval", "authority": "template_domain"})
        with self.assertRaisesRegex(ContractViolation, "duplicates MIS Core authority"):
            validate_template_manifest(manifest)

    def test_manifest_registers_all_ui_and_security_surfaces(self) -> None:
        manifest = build_manifest()
        self.assertEqual(len(manifest["ui_extensions"]), 1)
        self.assertEqual(manifest["ui_extensions"][0]["metadata"]["surfaces"], 18)
        self.assertEqual(len(manifest["api_routes"]), 41)
        self.assertEqual(len({(item["configuration"]["method"], item["configuration"]["path"]) for item in manifest["api_routes"]}), 41)
        self.assertTrue(any(item["id"] == "research_lab.tool.ssh_execute" and item["approval"] == "always" for item in manifest["tools"]))
        self.assertTrue(any(item["id"] == "research_lab.permission.compute_remote" and item["default"] == "deny" for item in manifest["permissions"]))

    def test_real_c0_sdk_mounts_exact_manifest_without_core_duplication(self) -> None:
        script = """
import json, os
from pathlib import Path
from templates.research_lab.production import build_research_production_composition
from tests.templates.research_lab.support import TEST_PUBLIC_KEY
store = Path(os.environ['AGENTOPS_CORE_RECEIPT_TRUST_STORE'])
composition = build_research_production_composition()
assert len(composition.mount['registrations']['api_route']) == 41
assert len(composition.mount['registrations']['domain_repository']) == 16
assert composition.mount['registrations']['memory_policy'] == ['research_lab.memory_policy.default']
assert composition.mount['mis_core_authority_duplicated'] is False
assert len(composition.mount['mounted']) > 0
"""
        with exported_c0(ROOT) as c0, tempfile.TemporaryDirectory() as raw:
            trust_store = Path(raw) / "trust.json"
            from .support import TEST_PUBLIC_KEY
            trust_store.write_text(json.dumps({"keys": {"mis-core-test-v1": {"algorithm": "ed25519", "revoked": False, "purposes": ["research.execution-authorization.v1"], "public_key_pem": TEST_PUBLIC_KEY.read_text()}}}), encoding="utf-8")
            trust_store.chmod(0o600)
            environment = {**os.environ, "AGENTOPS_CORE_RECEIPT_TRUST_STORE": str(trust_store), "PYTHONPATH": os.pathsep.join((str(c0), str(ROOT)))}
            completed = subprocess.run([sys.executable, "-P", "-W", "error", "-c", script], cwd="/tmp", env=environment, capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_every_declared_entrypoint_resolves_to_a_callable(self) -> None:
        manifest = build_manifest()
        fields = ("workflows", "agents", "skills", "tools", "policies", "evaluators", "ui_extensions", "reports", "api_routes", "cli_commands", "fixtures", "testing_hooks", "exports", "permissions", "migrations")
        for field in fields:
            for declaration in manifest[field]:
                with self.subTest(field=field, declaration=declaration["id"]):
                    module_name, separator, attribute = declaration["entrypoint"].partition(":")
                    self.assertEqual(separator, ":")
                    self.assertTrue(callable(getattr(importlib.import_module(module_name), attribute)))


if __name__ == "__main__":
    unittest.main()
