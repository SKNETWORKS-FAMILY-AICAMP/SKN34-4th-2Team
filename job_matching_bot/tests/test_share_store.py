"""공유 파일이 받는 쪽 코드에서 그대로 읽히는지.

핵심 약속: **용량을 줄이려고 뺀 것이 받는 쪽을 깨뜨리면 안 된다.** 개발용 기록은 비우되
컬럼은 남긴다. 실제로 한 번 이걸 놓쳐서 받은 파일로 피드백이 죽었다.
"""

from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore
from job_matching_bot.sharing.share_store import (
    EMPTY_COLUMNS,
    SHARE_COLUMNS,
    compress,
    decompress,
    download_if_newer,
    export,
)


class FakeBlob:
    def __init__(self, archive: Path):
        self.archive = archive
        self.generation = "generation-1"
        self.updated = datetime(2026, 9, 13, tzinfo=timezone.utc)
        self.size = archive.stat().st_size
        self.downloads = 0

    def exists(self):
        return True

    def reload(self):
        return None

    def download_to_filename(self, destination):
        self.downloads += 1
        Path(destination).write_bytes(self.archive.read_bytes())


class FakeBucket:
    def __init__(self, blob: FakeBlob):
        self.value = blob

    def blob(self, _remote):
        return self.value


class ExportTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "job_store.sqlite"
        base = mock_jobs()[0]
        self.job = replace(
            base,
            job_id="MOCK-1",
            source_job_id="MOCK-1",
            description="자격요건\n- Python 백엔드 개발 경험",
            required_certifications=["정보처리기사"],
            military_required=True,
            body_is_image=False,
            min_career_years=3,
            field_provenance={"career": {"method": "detail_dl", "evidence": "경력 3년"}},
        )
        with SqliteJobStore(self.source) as store:
            store.upsert([self.job], source="MOCK")

    def tearDown(self):
        self.temp.cleanup()

    def _export(self) -> Path:
        return export(self.source, self.root / "share.sqlite")

    def test_shared_file_is_readable_by_the_store_reader(self):
        """받는 쪽은 이 파일을 평소 저장소처럼 연다. 컬럼이 하나라도 빠지면 여기서 깨진다."""
        shared = self._export()
        with SqliteJobStore(shared) as store:
            record = store.get("MOCK-1")
        self.assertIsNotNone(record)
        self.assertEqual("MOCK-1", record.job.job_id)
        self.assertEqual(self.job.description, record.job.description)
        self.assertEqual(["정보처리기사"], record.job.required_certifications)
        self.assertTrue(record.job.military_required)
        self.assertFalse(record.job.body_is_image)
        self.assertEqual(3, record.job.min_career_years)

    def test_development_only_data_is_dropped_but_the_column_stays(self):
        shared = self._export()
        connection = sqlite3.connect(str(shared))
        try:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
            value = connection.execute("SELECT field_provenance FROM jobs").fetchone()[0]
        finally:
            connection.close()
        for name in EMPTY_COLUMNS:
            self.assertIn(name, columns, "컬럼은 남아야 받는 쪽이 읽는다")
        self.assertEqual({}, json.loads(value), "내용은 비워 용량을 아낀다")

    def test_index_tracking_and_tags_are_not_shared(self):
        """수집한 사람만 쓰는 것은 빼서 파일을 줄인다."""
        shared = self._export()
        connection = sqlite3.connect(str(shared))
        try:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            connection.close()
        self.assertNotIn("indexed_embed_hash", columns)
        self.assertNotIn("embed_hash", columns)
        self.assertNotIn("job_tags", tables)
        self.assertNotIn("runs", tables)

    def test_every_shared_column_survives(self):
        shared = self._export()
        connection = sqlite3.connect(str(shared))
        try:
            columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        finally:
            connection.close()
        for name in SHARE_COLUMNS:
            self.assertIn(name, columns)

    def test_source_store_is_left_alone(self):
        before = self.source.stat().st_mtime_ns
        self._export()
        self.assertEqual(before, self.source.stat().st_mtime_ns, "원본은 읽기만 한다")

    def test_compress_round_trip(self):
        shared = self._export()
        archive = compress(shared)
        restored = decompress(archive, self.root / "restored.sqlite")
        with SqliteJobStore(restored) as store:
            self.assertEqual("MOCK-1", store.get("MOCK-1").job.job_id)

    def test_download_if_newer_replaces_once_then_skips_same_generation(self):
        archive = compress(self._export())
        blob = FakeBlob(archive)
        destination = self.root / "received.sqlite"
        with patch("job_matching_bot.sharing.share_store.bucket", return_value=FakeBucket(blob)):
            self.assertTrue(download_if_newer("bucket", destination))
            self.assertFalse(download_if_newer("bucket", destination))
        self.assertEqual(1, blob.downloads)
        with SqliteJobStore(destination) as store:
            self.assertEqual("MOCK-1", store.get("MOCK-1").job.job_id)

    def test_invalid_download_does_not_replace_existing_database(self):
        destination = self.root / "received.sqlite"
        destination.write_bytes(b"existing database")
        corrupt = self.root / "corrupt.sqlite.gz"
        corrupt.write_bytes(b"not gzip")
        blob = FakeBlob(corrupt)
        with patch("job_matching_bot.sharing.share_store.bucket", return_value=FakeBucket(blob)):
            with self.assertRaises(Exception):
                download_if_newer("bucket", destination)
        self.assertEqual(b"existing database", destination.read_bytes())


if __name__ == "__main__":
    unittest.main()
