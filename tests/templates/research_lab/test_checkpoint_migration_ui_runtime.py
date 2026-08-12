from __future__ import annotations

import tempfile
import unittest
import zipfile
from pathlib import Path

from templates.research_lab.checkpoints import CheckpointCatalog, PyTorchCheckpointAdapter
from templates.research_lab.contracts import ResearchError, canonical_hash
from templates.research_lab.migrations import ResearchMigrationAdapter, dry_run_legacy, rollback_plan, transform_legacy, verify_migration
from templates.research_lab.migration_journal import MigrationRestartJournal
from template_runtime.protocols import InstallationIdentity, LifecycleCommand, LifecycleReceipt, TemplateMigrationPort
from templates.research_lab.observability import external_preflight, queue_health, structured_event, usage_metrics
from templates.research_lab.ui import extension_pages, resolve_view_state, validate_action
from .support import TEST_TRUST, signed


class CheckpointMigrationUIRuntimeTests(unittest.TestCase):
    class MigrationCore:
        def __init__(self):
            self.source = [{"kind": "experiment", "id": "exp_old", "value": {"status": "completed"}}]
            self.backups = {}
            self.migrations = {}
            self.apply_count = 0
        def load_legacy_records(self, identity): return self.source
        def create_backup(self, identity):
            value = signed({"backup_receipt_id":"bkp_1", "backup_sha256":"a" * 64, "verified":True, "workspace_id":identity.workspace_id, "template_id":identity.template_id}, "research.migration-backup/v1")
            return value
        def create_backup_once(self, **kwargs):
            request_hash = kwargs["request_hash"]
            if request_hash not in self.backups:
                self.backups[request_hash] = signed({"backup_receipt_id":"bkp_1", "backup_sha256":"a" * 64, "verified":True, "request_hash":request_hash, "workspace_id":kwargs["identity"].workspace_id, "template_id":kwargs["identity"].template_id}, "research.migration-backup-once/v1")
            return self.backups[request_hash]
        def find_migration_by_request_hash(self, **kwargs): return self.migrations.get(kwargs["request_hash"])
        def authorize_migration(self, **kwargs): return signed({"decision":"allow", "executed_once":True, "request_hash":kwargs["request_hash"], "backup_receipt_id":"bkp_1", "project_id":"prj_1", "task_id":"tsk_1", "run_id":"run_1", "workspace_id":kwargs["command"].workspace_id, "template_id":kwargs["command"].template_id}, "research.migration-authorization/v1")
        def apply_domain_migration_once(self, **kwargs):
            self.apply_count += 1
            value = signed({"transaction_id":"txn_1", "committed":True, "request_hash":kwargs["request_hash"], "backup_receipt_id":kwargs["backup_receipt_id"], "workspace_id":kwargs["command"].workspace_id, "template_id":kwargs["command"].template_id}, "research.migration-apply/v1")
            self.migrations[kwargs["request_hash"]] = value
            return value
        def readback_domain_migration(self, **kwargs): return signed({"verified":True, "readback_hash":"c" * 64, "workspace_id":kwargs["identity"].workspace_id, "template_id":kwargs["identity"].template_id}, "research.migration-readback/v1")
        def restore_backup_once(self, **kwargs): return signed({"restored":True, "readback_hash":"d" * 64, "request_hash":kwargs["request_hash"], "backup_receipt_id":kwargs["backup_receipt_id"], "workspace_id":kwargs["command"].workspace_id, "template_id":kwargs["command"].template_id}, "research.migration-restore/v1")
        def get_lifecycle_receipt(self, **kwargs):
            return LifecycleReceipt("rcp_1", "upgrade", "ws_1", "research_lab", "installed", "installed", "a" * 64, "idem", kwargs["transaction_id"], kwargs["readback_hash"], "b" * 64, "apr_1", "run_1", "aud_1", (), "2026-08-12T00:00:00Z")
        def attest_lifecycle_receipt(self, **kwargs):
            return signed({"transaction_id":kwargs["transaction_id"], "readback_hash":kwargs["readback_hash"], "lifecycle_receipt_hash":kwargs["lifecycle_receipt_hash"], "template_id":"research_lab", "verified":True}, "research.migration-lifecycle-receipt/v1")
    def test_pytorch_checkpoint_validated_without_deserialization(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "model.pt"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("archive/data.pkl", b"metadata-only-test")
                archive.writestr("archive/version", b"3")
            receipt = PyTorchCheckpointAdapter.validate_container(path)
            self.assertTrue(receipt["deserialization_performed"] is False)
            compatibility = {"torch_version": "2.6", "python_version": "3.11", "model_schema_hash": "c" * 64, "optimizer_schema_hash": "d" * 64}
            descriptor = CheckpointCatalog().describe(path, protocol_hash="a" * 64, code_commit="b" * 40, step=10, compatibility=compatibility)
            self.assertEqual(CheckpointCatalog().latest_valid([descriptor], protocol_hash="a" * 64, code_commit="b" * 40), descriptor)
            path.write_bytes(b"tampered")
            with self.assertRaisesRegex(ResearchError, "no valid"):
                CheckpointCatalog().latest_valid([descriptor], protocol_hash="a" * 64, code_commit="b" * 40)

    def test_corrupt_and_legacy_pickle_checkpoints_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "legacy.pt"
            path.write_bytes(b"not a zip pickle")
            with self.assertRaisesRegex(ResearchError, "legacy pickle"):
                PyTorchCheckpointAdapter.validate_container(path)

    def test_migration_dry_run_transform_readback_and_rollback(self) -> None:
        legacy = [{"kind": "experiment", "id": "exp_1", "value": {"name": "x"}}, {"kind": "attempt", "id": "att_1", "value": {"state": "completed"}}]
        dry = dry_run_legacy(legacy)
        self.assertTrue(dry["valid"])
        migrated = [transform_legacy(item, workspace_id="ws_1", project_id="prj_1", task_id="tsk_tpl_v1_research_20260810", run_id="run_1") for item in legacy]
        self.assertTrue(verify_migration(legacy, migrated)["verified"])
        corrupted = [dict(item) for item in migrated]
        corrupted[0] = {**corrupted[0], "value": {"name": "poisoned"}}
        self.assertFalse(verify_migration(legacy, corrupted)["verified"])
        self.assertTrue(rollback_plan(backup_receipt_id="rcp_backup", backup_sha256="a" * 64)["requires_approval"])

    def test_complete_migration_port_requires_core_approval_and_readback(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            adapter = ResearchMigrationAdapter(self.MigrationCore(), TEST_TRUST, MigrationRestartJournal(Path(raw) / "migration.sqlite3"))
            self.assertIsInstance(adapter, TemplateMigrationPort)
            identity = InstallationIdentity("ws_1", "research_lab")
            self.assertTrue(adapter.dry_run(identity, "1.0.0")["valid"])
            self.assertTrue(adapter.backup(identity)["verified"])
            command = LifecycleCommand("upgrade", "ws_1", "research_lab", "1.0.0", "idem", "a" * 64, "usr_1", "apr_1", "run_1")
            applied = adapter.apply_once(command, (adapter.migration_id,))
            self.assertTrue(applied["committed"])
            replay = adapter.apply_once(command, (adapter.migration_id,))
            self.assertEqual((adapter.core.apply_count, applied["request_hash"], replay["request_hash"]), (1, applied["request_hash"], applied["request_hash"]))
            restarted = ResearchMigrationAdapter(adapter.core, TEST_TRUST, MigrationRestartJournal(Path(raw) / "new-process.sqlite3"))
            self.assertEqual(restarted.apply_once(command, (adapter.migration_id,))["transaction_id"], "txn_1")
            self.assertTrue(adapter.readback(identity, (adapter.migration_id,))["verified"])
            self.assertTrue(adapter.rollback(command, "bkp_1")["restored"])
            self.assertEqual(adapter.receipt("txn_1", "c" * 64).transaction_id, "txn_1")

    def test_migration_detects_duplicates_and_unknown_kinds(self) -> None:
        result = dry_run_legacy([{"kind": "unknown", "id": "x"}, {"kind": "unknown", "id": "x"}])
        self.assertFalse(result["valid"])
        self.assertTrue(any(item["code"] == "duplicate_identity" for item in result["errors"]))

    def test_ui_pages_have_api_state_deep_links_and_action_guards(self) -> None:
        pages = extension_pages()
        self.assertEqual(len(pages), 18)
        self.assertTrue(all(page["api_resource"].startswith("/api/") and page["deep_link"] for page in pages))
        self.assertEqual(resolve_view_state(authorized=False, loading=False, data=[], error_code=None), "permission_denied")
        self.assertEqual(resolve_view_state(authorized=True, loading=False, data=[], error_code=None), "empty")
        with self.assertRaisesRegex(ResearchError, "action hash"):
            validate_action({"operation": "resume", "endpoint": "/api/x"})

    def test_observability_reports_external_unavailable_and_stale(self) -> None:
        health = external_preflight(openjiuwen_health=None, gpu_inventory=[], ssh_targets=[], slurm_required=True)
        self.assertEqual(health["state"], "degraded")
        self.assertIn("openjiuwen", health["external_blockers"])
        queue = queue_health([{"job_attempt_id": "att_1", "state": "running", "heartbeat_at": "2026-01-01T00:00:00Z"}], stale_before="2026-08-12T00:00:00Z")
        self.assertEqual(queue["state"], "degraded")
        event = structured_event(level="info", event="attempt.heartbeat", correlation_id="run_1", fields={"secret_ref": "vault://x", "state": "running"})
        self.assertEqual(event["fields"]["secret_ref"], "[REDACTED]")
        nested = structured_event(level="info", event="nested", correlation_id="run_1", fields={"request": {"headers": {"api_token": "literal"}}, "items": [{"password": "literal"}]})
        self.assertEqual(nested["fields"]["request"]["headers"]["api_token"], "[REDACTED]")
        self.assertEqual(nested["fields"]["items"][0]["password"], "[REDACTED]")
        self.assertEqual(usage_metrics(token_input=10, token_output=2, cost_usd=0.1, gpu_seconds=1, artifact_bytes=20)["gpu_seconds"], 1)


if __name__ == "__main__":
    unittest.main()
