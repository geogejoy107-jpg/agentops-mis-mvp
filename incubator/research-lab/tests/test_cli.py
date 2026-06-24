from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, "-m", "research_lab", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    payload = json.loads(proc.stdout)
    return proc.returncode, payload


class CLITests(unittest.TestCase):
    def test_validate_local_confirmatory_spec(self) -> None:
        code, payload = run_cli("validate-spec", "--spec", "examples/confirmatory_experiment.json")
        self.assertEqual(code, 0, payload)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["operation"], "validate_spec")
        self.assertEqual(payload["executor"], "local")
        self.assertEqual(payload["trial_count"], 2)
        self.assertTrue(payload["protocol_hash"])
        self.assertTrue(payload["provenance_hash"])
        self.assertTrue(payload["token_omitted"])

    def test_validate_ssh_spec_requires_server_registry(self) -> None:
        code, payload = run_cli("validate-spec", "--spec", "examples/ssh_experiment.json")
        self.assertEqual(code, 2)
        self.assertFalse(payload["ok"])
        self.assertIn("--servers", payload["message"])
        self.assertTrue(payload["token_omitted"])

    def test_server_list_and_probe_are_read_only(self) -> None:
        code, listed = run_cli("server-list", "--servers", "examples/servers.example.json")
        self.assertEqual(code, 0, listed)
        self.assertTrue(listed["ok"])
        self.assertEqual(listed["operation"], "server_list")
        self.assertEqual(len(listed["profiles"]), 1)
        profile = listed["profiles"][0]["name"]

        code, probed = run_cli("server-probe", "--servers", "examples/servers.example.json", "--profile", profile)
        self.assertEqual(code, 0, probed)
        self.assertTrue(probed["ok"])
        self.assertEqual(probed["operation"], "server_probe")
        self.assertFalse(probed["network_probe_performed"])
        self.assertFalse(probed["ssh_command_executed"])
        self.assertTrue(probed["token_omitted"])


if __name__ == "__main__":
    unittest.main()
