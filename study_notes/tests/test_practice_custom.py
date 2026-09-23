"""학생 자료로 복습 문제 — 연습장 파일을 자료로 바꾸고, 문제 수만큼 종류를 나눠 부르는지."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from study_notes.pipeline import MAX_CHARS_PER_FILE
from study_notes.practice import custom
from study_notes.practice.build import BuildResult
from study_notes.practice.generate import Usage
from study_notes.practice.models import PracticeProblem


class UploadMaterialsTests(unittest.TestCase):
    def test_notebook_becomes_text_and_py_stays(self) -> None:
        nb = json.dumps({"cells": [{"cell_type": "markdown", "source": "# 풀링"}, {"cell_type": "code", "source": "x = max(1, 2)"}]})
        out = custom.upload_materials([{"name": "lesson.ipynb", "content": nb}, {"name": "a.py", "content": "# %%\nprint(1)\n"}])
        self.assertEqual([m["path"] for m in out], ["lesson.ipynb", "a.py"])
        self.assertIn("x = max(1, 2)", out[0]["content"])
        self.assertNotIn('"cell_type"', out[0]["content"])  # JSON 이 아니라 셀 글
        self.assertEqual(out[1]["content"], "# %%\nprint(1)\n")

    def test_long_file_is_cut_and_empty_skipped(self) -> None:
        out = custom.upload_materials([{"name": "big.py", "content": "y = 1\n" * 5000}, {"name": "empty.py", "content": "  \n"}])
        self.assertEqual(len(out), 1)
        self.assertEqual(len(out[0]["content"]), MAX_CHARS_PER_FILE)
        self.assertTrue(out[0]["truncated"])


class MakeProblemsTests(unittest.TestCase):
    def test_asks_for_count_problems_and_returns_verified_ones(self) -> None:
        result = BuildResult(problems=[PracticeProblem(kind="concept", prompt="q", topic="t", choices=["a", "b", "c"], answer_index=0)],
                             stats={}, usage=Usage())
        with mock.patch.object(custom, "build_practice_set", return_value=result) as fake:
            out = custom.make_problems([{"path": "a.py", "commit": "", "content": "x", "truncated": False}],
                                       scope_label="내 노트", count=6, runner=object())
        kinds = fake.call_args.kwargs["kind_counts"]
        self.assertEqual(sum(int(part.split()[-1].rstrip("개")) for part in kinds.split(", ")), 6)
        self.assertEqual(len(out["problems"]), 1)
        self.assertEqual(out["problems"][0]["kind"], "concept")

    def test_empty_materials_is_an_error(self) -> None:
        with self.assertRaises(ValueError):
            custom.make_problems([], scope_label="x", count=6, runner=object())


if __name__ == "__main__":
    unittest.main()
