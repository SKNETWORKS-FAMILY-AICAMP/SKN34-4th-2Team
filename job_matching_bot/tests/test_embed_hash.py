"""embed_hash 기준 증분 적재 — 무엇이 바뀌면 다시 올리고, 무엇은 무시하는지.

핵심 약속: **마감일·수집 시각만 달라진 공고는 다시 임베딩하지 않는다.** 이게 깨지면
밤마다 다시 받은 공고를 전부 다시 올려 임베딩 비용과 Pinecone 쓰기가 매일 전량으로 나간다.
"""

from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from job_matching_bot.tests import AS_OF
from job_matching_bot.ingestion.mock_source import mock_jobs
from job_matching_bot.ingestion.sqlite_store import SqliteJobStore
from job_matching_bot.retrieval import documents as doc
from job_matching_bot.retrieval.pinecone_index import DIMENSION
from job_matching_bot.retrieval.upsert import delete_ids, plan, upsert

BODY = """주요업무
- FastAPI 기반 추천 API를 설계하고 운영합니다
- PostgreSQL 스키마와 배치 파이프라인을 관리합니다

자격요건
- Python 백엔드 개발 경력 3년 이상
- REST API 설계와 SQL 튜닝 경험

우대사항
- AWS 또는 GCP 운영 경험
- Docker, Kubernetes 배포 경험

근무조건
- 서울 성동구, 정규직
"""

LIVE_DEADLINE = (AS_OF + timedelta(days=3650)).isoformat()
PAST_DEADLINE = (AS_OF - timedelta(days=400)).isoformat()


def _job(**over):
    base = replace(mock_jobs()[0], description=BODY, deadline=None, status="OPEN")
    return replace(base, **over)


class EmbedHashTest(unittest.TestCase):
    def test_ignores_deadline_status_and_raw_hash(self):
        a = _job()
        b = replace(a, deadline=LIVE_DEADLINE, status="EXPIRED", content_hash="sha256:other", parser_version="x")
        self.assertEqual(doc.embed_hash(a), doc.embed_hash(b))

    def test_ignores_text_outside_requirement_sections(self):
        # 근무조건 아래 줄은 임베딩 텍스트가 아니다.
        a = _job()
        self.assertEqual(doc.embed_hash(a), doc.embed_hash(replace(a, description=BODY.replace("정규직", "계약직"))))

    def test_changes_with_requirements_or_filter_fields(self):
        a = _job()
        for changed in (
            replace(a, description=BODY.replace("3년", "5년")),
            replace(a, region="부산 해운대구"),
            replace(a, required_skills=["Go"]),
            replace(a, title="다른 제목"),
        ):
            self.assertNotEqual(doc.embed_hash(a), doc.embed_hash(changed))

    def test_metadata_carries_embed_hash(self):
        job = _job()
        self.assertEqual(doc.embed_hash(job), doc.to_metadata(job)["embed_hash"])


class FakeIndex:
    """Pinecone 대역. 저장소가 추적하는 동안에는 fetch가 불리면 안 된다."""

    def __init__(self):
        self.upserted: dict[str, dict] = {}
        self.deleted: list[str] = []

    def upsert(self, vectors):
        for vector in vectors:
            self.upserted[vector["id"]] = vector

    def delete(self, ids):
        self.deleted.extend(ids)
        for vector_id in ids:
            self.upserted.pop(vector_id, None)

    def fetch(self, ids):
        raise AssertionError("SQLite 저장소가 있으면 인덱스를 조회하지 않는다")


class FakeEmbeddings:
    def embed_documents(self, texts):
        return [[0.0] * DIMENSION for _ in texts]


class IncrementalPlanTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = SqliteJobStore(Path(self.temp.name) / "store.sqlite")
        self.index = FakeIndex()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def _plan(self, force=False):
        jobs = [record.job for record in self.store.all_records()]
        return plan(jobs, self.index, force, tracker=self.store)

    def _upsert(self, changed):
        return upsert(changed, self.index, tracker=self.store, embeddings=FakeEmbeddings())

    def _row(self, job_id):
        return self.store.conn.execute(
            "SELECT embed_hash, indexed_embed_hash FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()

    def test_first_run_uploads_then_nothing(self):
        job = _job()
        self.store.upsert([job], source="MOCK")
        changed, to_delete, stats = self._plan()
        self.assertEqual([job.job_id], [j.job_id for j in changed])
        self.assertEqual([], to_delete)
        self.assertEqual(0, stats["인덱스에 이미 있음"])

        self.assertEqual(1, self._upsert(changed))
        self.assertEqual(doc.embed_hash(job), self.index.upserted[job.job_id]["metadata"]["embed_hash"])
        self.assertEqual(doc.embed_hash(job), self._row(job.job_id)["indexed_embed_hash"])
        changed, to_delete, stats = self._plan()
        self.assertEqual(([], []), (changed, to_delete))
        self.assertEqual(1, stats["인덱스에 이미 있음"])

    def test_deadline_change_is_not_reuploaded_but_requirement_change_is(self):
        job = _job()
        self.store.upsert([job], source="MOCK")
        self._upsert(self._plan()[0])
        later = AS_OF + timedelta(days=1)

        # 마감일과 원본 해시만 바뀜 → 저장소는 '갱신'으로 세지만 인덱스는 그대로
        self.store.upsert([replace(job, deadline=LIVE_DEADLINE, content_hash="sha256:v2")], source="MOCK", as_of=later)
        self.assertEqual(1, self.store.get(job.job_id).revisions)
        self.assertEqual([], self._plan()[0])

        # 자격요건이 바뀜 → 다시 올린다
        self.store.upsert(
            [replace(job, description=BODY.replace("3년", "5년"), content_hash="sha256:v3")], source="MOCK", as_of=later
        )
        self.assertEqual([job.job_id], [j.job_id for j in self._plan()[0]])

    def test_expired_job_is_deleted_once_then_forgotten(self):
        job = _job(deadline=LIVE_DEADLINE)
        self.store.upsert([job], source="MOCK")
        self._upsert(self._plan()[0])

        self.store.upsert([replace(job, deadline=PAST_DEADLINE)], source="MOCK")
        changed, to_delete, _ = self._plan()
        self.assertEqual([], changed)
        self.assertEqual([job.job_id], to_delete)

        delete_ids(self.index, to_delete, tracker=self.store)
        self.assertEqual([job.job_id], self.index.deleted)
        self.assertIsNone(self._row(job.job_id)["indexed_embed_hash"])
        self.assertEqual([], self._plan()[1])

    def test_store_writes_embed_hash_and_keeps_indexed_hash_on_update(self):
        job = _job()
        self.store.upsert([job], source="MOCK")
        row = self._row(job.job_id)
        self.assertEqual(doc.embed_hash(job), row["embed_hash"])
        self.assertIsNone(row["indexed_embed_hash"])

        self.store.mark_indexed({job.job_id: row["embed_hash"]}, at=AS_OF)
        self.store.upsert([replace(job, content_hash="sha256:v2")], source="MOCK")
        self.assertEqual(row["embed_hash"], self._row(job.job_id)["indexed_embed_hash"])

    def test_missing_embed_hash_counts_as_changed_until_refreshed(self):
        job = _job()
        self.store.upsert([job], source="MOCK")
        with self.store.conn:
            self.store.conn.execute("UPDATE jobs SET embed_hash = NULL")
        self.assertEqual([job.job_id], [j.job_id for j in self._plan()[0]])
        self.assertEqual(1, self.store.refresh_embed_hashes())
        self.assertEqual(0, self.store.refresh_embed_hashes())
        self.assertEqual(doc.embed_hash(job), self._row(job.job_id)["embed_hash"])

    def test_force_reuploads_everything(self):
        job = _job()
        self.store.upsert([job], source="MOCK")
        self._upsert(self._plan()[0])
        self.assertEqual([job.job_id], [j.job_id for j in self._plan(force=True)[0]])


class WriteReadFingerprintTest(unittest.TestCase):
    """쓴 지문과 읽은 지문이 같아야 한다.

    저장소는 읽을 때 "글에 요건이 있으면 이미지 공고가 아니다"로 값을 뒤집는다. 쓰는
    쪽이 다른 값을 넣으면 같은 행의 지문이 쓸 때와 읽을 때 달라진다. 그러면 바뀐 것이
    없는데도 적재가 다시 올릴 대상으로 잡는다 — 실제로 4,316건이 그렇게 잡혀 있었다.
    """

    def test_load_time_image_rule_does_not_move_the_fingerprint(self):
        base = mock_jobs()[0]
        long_text = "자격요건 " + "Python으로 서비스를 만들어 본 분. " * 60
        job = replace(base, job_id="J-IMG", source_job_id="J-IMG", description=long_text, body_is_image=True)
        with tempfile.TemporaryDirectory() as tmp:
            store = SqliteJobStore(Path(tmp) / "store.sqlite")
            store.upsert([job], source="MOCK", as_of=AS_OF)
            stored = store.index_state()["J-IMG"][0]
            loaded = next(r.job for r in store.all_records() if r.job.job_id == "J-IMG")
            self.assertFalse(loaded.body_is_image, "읽을 때는 글이 있으니 이미지 공고가 아니다")
            self.assertEqual(stored, doc.embed_hash(loaded), "쓴 지문과 읽은 지문이 같아야 한다")
            store.close()


if __name__ == "__main__":
    unittest.main()
