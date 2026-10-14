"""`sync --index-only` 가 --dry-run 을 지키고 runs 에 실행을 남기는지. DB·Pinecone 없이 본다."""

from __future__ import annotations

import tempfile
import unittest
from argparse import Namespace
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from job_matching_bot import sync


class IndexOnlyTests(unittest.TestCase):
    def _run(self, *, dry_run: bool):
        index = MagicMock()
        index.describe_index_stats.return_value = {"total_vector_count": 3}
        tracker = MagicMock()
        upsert = MagicMock(return_value=2)
        delete_ids = MagicMock()
        record_run = MagicMock()
        with tempfile.TemporaryDirectory() as folder, patch(
            "job_matching_bot.retrieval.pinecone_index.ensure_index", return_value={"name": "jobs"}
        ), patch("job_matching_bot.retrieval.pinecone_index.client") as client, patch(
            "job_matching_bot.retrieval.upsert.load_store", return_value=([], tracker)
        ), patch(
            "job_matching_bot.retrieval.upsert.plan", return_value=(["a", "b"], ["c"], {"대상": 2})
        ), patch("job_matching_bot.retrieval.upsert.upsert", upsert), patch(
            "job_matching_bot.retrieval.upsert.delete_ids", delete_ids
        ), patch.object(sync, "record_run", record_run):
            client.return_value.Index.return_value = index
            args = Namespace(store=Path(folder) / "job_store.sqlite", report=Path(folder) / "r.json", dry_run=dry_run)
            now = datetime.now(sync.KST)
            code = sync._index(args, {}, now, now)
        self.assertEqual(code, 0)
        tracker.close.assert_called_once()
        return upsert, delete_ids, record_run

    def test_dry_run_touches_nothing(self):
        upsert, delete_ids, record_run = self._run(dry_run=True)
        upsert.assert_not_called()
        delete_ids.assert_not_called()
        record_run.assert_not_called()

    def test_records_run_with_aware_start(self):
        upsert, delete_ids, record_run = self._run(dry_run=False)
        upsert.assert_called_once()
        delete_ids.assert_called_once()
        record_run.assert_called_once()
        _, run, started = record_run.call_args.args
        self.assertEqual(run.source, "INDEX")
        self.assertEqual(record_run.call_args.kwargs["vectors"], 2)
        self.assertIsNotNone(started.tzinfo)


if __name__ == "__main__":
    unittest.main()
