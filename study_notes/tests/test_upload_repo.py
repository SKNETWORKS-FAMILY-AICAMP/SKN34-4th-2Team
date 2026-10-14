"""폴더 올리기 — 서버 안 저장소에 날짜별로 커밋하면, GitHub 저장소를 읽던 코드(RepoCache)가 그대로 읽는다."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from study_notes import upload_repo
from study_notes.git_tools import EMPTY_REPO_MESSAGE, GitToolError, RepoCache, parse_repo_url


class UploadRepoTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.dict("os.environ", {"STUDY_NOTES_CACHE_DIR": self.tmp.name})
        patch.start()
        self.addCleanup(patch.stop)
        self.cache = RepoCache("cohort_34", "99", parse_repo_url("upload://cohort_34/python_basic"), "main")

    def day(self, date: str, files: dict[str, str]):
        return upload_repo.commit_day(self.cache, date, {p: b.encode() for p, b in files.items()})

    def test_lesson_dates_and_files_of_the_day(self) -> None:
        self.day("2026-06-18", {"01_variable/exercise.ipynb": "x = 1", "02_data-type/exercise.ipynb": "a = '3'"})
        self.day("2026-06-19", {"04_function/exercise.ipynb": "def f(): pass"})
        self.cache.sync()
        self.assertEqual(["2026-06-19", "2026-06-18"], self.cache.recent_lesson_dates([]))
        _shas, files = self.cache.changed_files_on("2026-06-18", [])
        self.assertEqual(["01_variable/exercise.ipynb", "02_data-type/exercise.ipynb"], [f.path for f in files])
        _shas, files = self.cache.changed_files_on("2026-06-19", [])
        self.assertEqual(["04_function/exercise.ipynb"], [f.path for f in files])
        self.assertEqual("def f(): pass", self.cache.read_file(files[0].commit, files[0].path))

    def test_same_content_is_skipped_and_grown_file_is_that_days_lesson(self) -> None:
        self.day("2026-06-19", {"04_function/exercise.ipynb": "def f(): pass"})
        # 6/23 — 같은 노트북에 셀을 더했다(작은 주제를 며칠에 걸쳐), 다른 파일은 그대로 다시 올림
        out = self.day("2026-06-23", {"04_function/exercise.ipynb": "def f(): pass\nlambda x: x", "01_variable/a.py": "x = 1"})
        self.assertEqual(["01_variable/a.py", "04_function/exercise.ipynb"], out.changed)
        again = self.day("2026-06-24", {"04_function/exercise.ipynb": "def f(): pass\nlambda x: x"})
        self.assertIsNone(again.sha, "바뀐 게 없으면 커밋하지 않는다")
        self.assertEqual(["04_function/exercise.ipynb"], again.skipped)
        self.assertEqual(["2026-06-23", "2026-06-19"], self.cache.recent_lesson_dates([]))

    def test_late_upload_for_an_earlier_day_is_still_found(self) -> None:
        # 6/23 을 먼저 올리고, 깜빡한 6/22 를 나중에 올림 — 커밋 날짜가 순서대로가 아니다
        self.day("2026-06-23", {"09_exception/exercise.ipynb": "try: pass\nexcept: pass"})
        self.day("2026-06-22", {"08_file-io/exercise.ipynb": "open('a')"})
        _shas, files = self.cache.changed_files_on("2026-06-22", [])
        self.assertEqual(["08_file-io/exercise.ipynb"], [f.path for f in files])
        self.assertEqual(["2026-06-23", "2026-06-22"], self.cache.recent_lesson_dates([]))

    def test_nothing_uploaded_yet_reads_as_empty_repo(self) -> None:
        with self.assertRaises(GitToolError) as ctx:
            self.cache.sync()
        self.assertEqual(EMPTY_REPO_MESSAGE, str(ctx.exception))

    def test_only_lesson_files_and_safe_paths(self) -> None:
        out = self.day("2026-06-18", {"01_variable/a.py": "x = 1", "data/sample.csv": "a,b", ".DS_Store": "x"})
        self.assertEqual(["01_variable/a.py"], out.changed)
        for bad in ("../outside.py", ".git/hooks/post-commit.py", "a/.git/x.py"):
            with self.assertRaises(GitToolError, msg=bad):
                self.day("2026-06-18", {bad: "x"})

    def test_github_urls_are_unchanged(self) -> None:
        ref = parse_repo_url("https://github.com/skn-ai34-260616/python_basic")
        self.assertFalse(ref.upload)
        github = RepoCache("cohort_34", "10", ref, "main")
        self.assertEqual("refs/remotes/origin/main", github.ref)
        self.assertEqual("refs/heads/main", self.cache.ref)
        self.assertTrue(Path(self.tmp.name).exists())


if __name__ == "__main__":
    unittest.main()
