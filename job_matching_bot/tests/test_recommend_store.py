"""The managed jobs store must not depend on a local SQLite file."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from job_matching_bot.api.service import RecommendService
from job_matching_bot.retrieval.search import Hit


class RecommendStoreTest(unittest.TestCase):
    def test_reviewable_hits_open_managed_store_without_local_file(self):
        hit = Hit(job_id="JOB-1", score=0.9, rank=1, metadata={})
        job = object()
        store = MagicMock()
        store.__enter__.return_value = store
        store.get.return_value = SimpleNamespace(status="OPEN", job=job)

        with tempfile.TemporaryDirectory() as directory:
            missing_path = Path(directory) / "job_store.sqlite"
            with patch("job_matching_bot.ingest.DEFAULT_STORE", missing_path), patch(
                "job_matching_bot.ingestion.sqlite_store.SqliteJobStore", return_value=store
            ) as open_store:
                warnings = []
                resolved = RecommendService._load_reviewable_hits([hit], warnings)

        self.assertEqual(resolved, [(hit, job)])
        self.assertEqual(warnings, [])
        open_store.assert_called_once_with(missing_path)


if __name__ == "__main__":
    unittest.main()
