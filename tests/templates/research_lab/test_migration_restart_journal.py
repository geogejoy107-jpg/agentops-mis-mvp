from __future__ import annotations

import multiprocessing
import tempfile
import unittest
from pathlib import Path

from templates.research_lab.contracts import ResearchError
from templates.research_lab.migration_journal import MigrationRestartJournal


def reopen_and_read(path: str, request_hash: str, output: multiprocessing.Queue) -> None:
    output.put(MigrationRestartJournal(Path(path)).read(request_hash))


class MigrationRestartJournalTests(unittest.TestCase):
    def test_backup_and_apply_survive_process_restart_without_replay(self):
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "migration.sqlite3"; request_hash = "a" * 64
            first = MigrationRestartJournal(path)
            self.assertEqual(first.record_backup_once(request_hash, {"backup_receipt_id": "bkp_1"})["backup_receipt_id"], "bkp_1")
            self.assertEqual(first.record_backup_once(request_hash, {"backup_receipt_id": "bkp_evil"})["backup_receipt_id"], "bkp_1")
            first.record_apply_once(request_hash, {"transaction_id": "txn_1"})
            queue = multiprocessing.Queue(); process = multiprocessing.Process(target=reopen_and_read, args=(str(path), request_hash, queue))
            process.start(); process.join(10)
            self.assertEqual(process.exitcode, 0)
            self.assertEqual(queue.get(timeout=2), {"backup": {"backup_receipt_id": "bkp_1"}, "apply": {"transaction_id": "txn_1"}})
            self.assertEqual(MigrationRestartJournal(path).record_apply_once(request_hash, {"transaction_id": "txn_evil"})["transaction_id"], "txn_1")

    def test_apply_before_backup_fails_closed(self):
        with tempfile.TemporaryDirectory() as raw, self.assertRaisesRegex(ResearchError, "backup"):
            MigrationRestartJournal(Path(raw) / "migration.sqlite3").record_apply_once("b" * 64, {"transaction_id": "txn"})


if __name__ == "__main__":
    unittest.main()
