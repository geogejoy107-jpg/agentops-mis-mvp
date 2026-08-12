from __future__ import annotations

import json
import unittest
from pathlib import Path

from template_runtime.contracts import ContractViolation, validate_product_profile, validate_template_manifest
from templates.research_lab.manifest import build_manifest

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
        self.assertGreaterEqual(len(manifest["api_routes"][0]["configuration"]["routes"]), 15)
        self.assertTrue(any(item["id"] == "research_lab.tool.ssh_execute" and item["approval"] == "always" for item in manifest["tools"]))
        self.assertTrue(any(item["id"] == "research_lab.permission.compute_remote" and item["default"] == "deny" for item in manifest["permissions"]))


if __name__ == "__main__":
    unittest.main()
