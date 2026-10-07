"""같은 기수 학생이 노트를 나눠 보고, 수업 파일이 바뀌면 다시 만드는 데 필요한 것들.

- 노트에는 문제를 넣지 않는다(복습 문제는 매일 출제 세트가 맡는다)
- 범위를 LLM 없이 파일 · 내용 해시로 풀어 준다(/proxy/resolve)
- Django 는 그 해시로 「같은 자료로 만든 노트인가」를 가른다(lms/study_scope.same_material)
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException

from study_notes import pipeline, service
from study_notes.git_tools import RepoCache, parse_repo_url

SOURCE = {
    "id": "multimodal",
    "title": "멀티모달",
    "repoUrl": "https://github.com/skn34/multimodal",
    "branch": "main",
    "allowedPrefixes": ["01_cnn"],
}


def _lms_scope():
    path = Path(__file__).resolve().parents[2] / "lms_api" / "lms" / "study_scope.py"
    spec = importlib.util.spec_from_file_location("lms_study_scope_shared", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class NoteHasNoProblemsTests(unittest.TestCase):
    def _generate(self, text: str) -> tuple[str, str]:
        with mock.patch.object(pipeline, "NOTE_PROMPT") as prompt, mock.patch.object(pipeline, "_llm"):
            prompt.__or__.return_value.invoke.return_value = SimpleNamespace(content=text)
            return pipeline.generate_study_note(
                scope_label="2026-09-11",
                commits=["c1"],
                materials=[{"path": "a.py", "commit": "c1", "content": "print(1)", "truncated": False}],
            )

    def test_prompt_asks_for_no_problems(self) -> None:
        human = pipeline.NOTE_PROMPT.messages[1].prompt.template
        self.assertNotIn("복습 문제", human)
        self.assertNotIn("정답과 해설", human)

    def test_problems_the_model_adds_anyway_are_cut(self) -> None:
        report, review = self._generate("## 오늘 꼭 알아야 할 것\n요약\n\n---\n\n## 복습 문제\n1. 문제")
        self.assertEqual("## 오늘 꼭 알아야 할 것\n요약", report)
        self.assertEqual("", review)


class BlobIdsTests(unittest.TestCase):
    """내용 해시는 파일 본문을 받지 않고 트리에서 읽는다. 같은 내용이면 커밋이 달라도 같다."""

    def setUp(self) -> None:
        if shutil.which("git") is None:
            self.skipTest("git 없음")
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

        def git(*args: str) -> str:
            return subprocess.run(["git", *args], cwd=self.dir, check=True, capture_output=True, text=True).stdout.strip()

        git("init", "-q")
        git("config", "user.email", "t@example.com")
        git("config", "user.name", "t")
        (self.dir / "01_cnn").mkdir()
        (self.dir / "01_cnn" / "a.py").write_text("print('a')\n", encoding="utf-8")
        (self.dir / "01_cnn" / "b.py").write_text("print('b')\n", encoding="utf-8")
        git("add", ".")
        git("commit", "-qm", "첫 수업")
        self.first = git("rev-parse", "HEAD")
        (self.dir / "01_cnn" / "b.py").write_text("print('b2')\n", encoding="utf-8")
        git("commit", "-qam", "b 고침")
        self.second = git("rev-parse", "HEAD")
        self.cache = RepoCache("cohort_34", "multimodal", parse_repo_url(SOURCE["repoUrl"]), "main")
        self.cache.dir = self.dir

    def test_same_content_same_blob_across_commits(self) -> None:
        files = [
            {"path": "01_cnn/a.py", "commit": self.first},
            {"path": "01_cnn/a.py", "commit": self.second},
            {"path": "01_cnn/b.py", "commit": self.first},
            {"path": "01_cnn/b.py", "commit": self.second},
        ]
        blobs = self.cache.blob_ids(files)
        self.assertEqual(blobs[(self.first, "01_cnn/a.py")], blobs[(self.second, "01_cnn/a.py")])
        self.assertNotEqual(blobs[(self.first, "01_cnn/b.py")], blobs[(self.second, "01_cnn/b.py")])


class ResolveForLmsTests(unittest.TestCase):
    def resolve(self, collected, blobs=None):
        source = service.source_from_payload(SOURCE)
        cache = mock.MagicMock()
        cache.blob_ids.return_value = blobs or {}
        with mock.patch.object(service, "repo_cache", return_value=cache), \
                mock.patch.object(service, "_collect", return_value=collected):
            out = service.resolve_note_for_lms("cohort_34", source, "date", "2026-09-11")
        return out, cache

    def test_files_come_with_content_hash_and_no_llm(self) -> None:
        with mock.patch.object(service, "generate_study_note") as llm:
            out, _ = self.resolve((["c1"], [{"path": "01_cnn/a.py", "commit": "c1"}], False),
                                  {("c1", "01_cnn/a.py"): "blob-a"})
        llm.assert_not_called()
        self.assertEqual("ready", out["status"])
        self.assertEqual([{"path": "01_cnn/a.py", "commit": "c1", "blob": "blob-a"}], out["files"])
        self.assertEqual("2026-09-11", out["scopeKey"])

    def test_too_broad_skips_hashing(self) -> None:
        files = [{"path": f"01_cnn/{i}.py", "commit": "c1"} for i in range(9)]
        out, cache = self.resolve((["c1"], files, True))
        self.assertEqual("too_broad", out["status"])
        self.assertIn("최대", out["message"])
        cache.blob_ids.assert_not_called()

    def test_empty_scope_is_404(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.resolve((["c1"], [], False))
        self.assertEqual(404, ctx.exception.status_code)


class SameMaterialTests(unittest.TestCase):
    """Django 가 「이 노트를 나눠 줘도 되나 / 다시 만들어야 하나」를 가르는 규칙."""

    def setUp(self) -> None:
        self.same = _lms_scope().same_material

    def test_same_blobs_match_even_if_commits_differ(self) -> None:
        stored = [{"path": "a.py", "commit": "c1", "blob": "x"}]
        self.assertTrue(self.same(stored, [{"path": "a.py", "commit": "c9", "blob": "x"}]))

    def test_changed_file_content_does_not_match(self) -> None:
        stored = [{"path": "a.py", "commit": "c1", "blob": "x"}]
        self.assertFalse(self.same(stored, [{"path": "a.py", "commit": "c1", "blob": "y"}]))

    def test_added_or_removed_file_does_not_match(self) -> None:
        stored = [{"path": "a.py", "commit": "c1", "blob": "x"}]
        both = [{"path": "a.py", "commit": "c1", "blob": "x"}, {"path": "b.py", "commit": "c1", "blob": "z"}]
        self.assertFalse(self.same(stored, both))
        self.assertFalse(self.same(both, stored))

    def test_old_notes_without_hash_compare_commits(self) -> None:
        stored = '[{"path": "a.py", "commit": "c1"}]'  # Django 는 jsonb 를 글자로 주기도 한다
        self.assertTrue(self.same(stored, [{"path": "a.py", "commit": "c1", "blob": "x"}]))
        self.assertFalse(self.same(stored, [{"path": "a.py", "commit": "c2", "blob": "x"}]))

    def test_nothing_to_compare_is_not_a_match(self) -> None:
        self.assertFalse(self.same([], [{"path": "a.py", "commit": "c1"}]))
        self.assertFalse(self.same(None, None))



class SubjectSummaryTests(unittest.TestCase):
    """과목 전체 요약 — 날짜별 노트를 모아 한 번 더 정리한다."""

    def test_days_are_packed_in_date_order_within_budget(self) -> None:
        days = [{"date": "2026-09-12", "report": "나" * 50_000}, {"date": "2026-09-11", "report": "가" * 10}]
        packed = pipeline.pack_days(days)
        self.assertLess(packed.index("### 2026-09-11"), packed.index("### 2026-09-12"))
        self.assertIn("### 2026-09-12 (일부만)", packed)
        self.assertLessEqual(len(packed), pipeline.MAX_SUBJECT_CHARS + 200)

    def test_summary_asks_for_no_problems_and_needs_notes(self) -> None:
        human = pipeline.SUBJECT_PROMPT.messages[1].prompt.template
        self.assertIn("날짜별 흐름", human)
        self.assertNotIn("복습 문제", human)
        with self.assertRaises(ValueError):
            pipeline.generate_subject_summary(subject="파이썬", days=[{"date": "2026-09-11", "report": "  "}])

    def test_summary_is_one_llm_call(self) -> None:
        with mock.patch.object(pipeline, "SUBJECT_PROMPT") as prompt, mock.patch.object(pipeline, "_llm"):
            prompt.__or__.return_value.invoke.return_value = SimpleNamespace(content="## 과목 한눈에 보기\n요약")
            out = pipeline.generate_subject_summary(
                subject="파이썬", days=[{"date": "2026-09-11", "report": "노트"}],
            )
        self.assertEqual("## 과목 한눈에 보기\n요약", out)
        prompt.__or__.return_value.invoke.assert_called_once()


if __name__ == "__main__":
    unittest.main()
