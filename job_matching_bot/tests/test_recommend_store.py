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
        job = SimpleNamespace(title="백엔드 개발자 채용")
        store = MagicMock()
        store.__enter__.return_value = store
        # 추천 필터는 검색 결과를 한 번에 읽는다(get_many — 한 건씩이면 RDS 왕복이 25번)
        store.get_many.return_value = {"JOB-1": SimpleNamespace(status="OPEN", job=job)}

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

    def test_training_programs_are_not_recommended(self):
        hits = [Hit(job_id="JOB-1", score=0.9, rank=1, metadata={}), Hit(job_id="JOB-2", score=0.8, rank=2, metadata={})]
        hiring = SimpleNamespace(title="백엔드 개발자 채용")
        store = MagicMock()
        store.__enter__.return_value = store
        store.get_many.return_value = {
            "JOB-1": SimpleNamespace(status="OPEN", job=SimpleNamespace(title="[IBM] Cloud Native Dev base AI agent 6기")),
            "JOB-2": SimpleNamespace(status="OPEN", job=hiring),
        }
        with patch("job_matching_bot.ingestion.sqlite_store.SqliteJobStore", return_value=store):
            warnings = []
            resolved = RecommendService._load_reviewable_hits(hits, warnings)

        self.assertEqual([job for _, job in resolved], [hiring])
        self.assertEqual(warnings, ["채용이 아닌 교육 과정 모집 1건을 제외했습니다."])


if __name__ == "__main__":
    unittest.main()
