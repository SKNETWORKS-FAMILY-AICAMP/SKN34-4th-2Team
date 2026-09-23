"""파일 단위 출제 — 새로 생긴 셀만 골라내는지."""

from __future__ import annotations

import json
import unittest

from study_notes.practice.increments import (
    DAY_QUOTA,
    KIND_MIX,
    MAX_PER_FILE,
    FileCoverage,
    diff_file,
    kind_mix,
    plan_day,
    split_cells,
)


def notebook(*cells: tuple[str, str]) -> str:
    return json.dumps({
        "cells": [{"cell_type": kind, "source": text.splitlines(keepends=True)} for kind, text in cells],
    })


LONG = "x = 1\n" * 60  # 새 내용 기준(200자)을 넘기는 코드
DAY1 = [
    ("markdown", "# 프레임 추출\n동영상에서 일정 간격으로 프레임을 저장한다"),
    ("code", "import cv2\nimport os"),
    ("code", "def extract_frames(video_dir, frame_interval=1):\n    cap = cv2.VideoCapture(path)\n" + LONG),
    ("code", ""),
]
DAY2_EXTRA = [
    ("markdown", "## 프레임 번호 뽑기\n파일명에서 정규식으로 번호를 뽑는다"),
    ("code", "import re\ndef extract_frame_no(f):\n    return int(re.search(r'_frame(\\d+)', f).group(1))\n" + LONG),
]


class SplitTests(unittest.TestCase):
    def test_notebook_cells_drop_empty(self) -> None:
        cells = split_cells("a.ipynb", notebook(*DAY1))
        self.assertEqual([c.kind for c in cells], ["markdown", "code", "code"])

    def test_py_splits_on_blank_lines(self) -> None:
        cells = split_cells("a.py", "import re\n\n\ndef f():\n    return 1\n\n# 끝")
        self.assertEqual(len(cells), 3)


class DiffTests(unittest.TestCase):
    def cover(self, raw: str) -> FileCoverage:
        plan = plan_day("2026-09-14", [("rag/frames.ipynb", "c1", raw)], {})
        return plan.coverage_after({})["rag/frames.ipynb"]

    def test_first_time_everything_is_new(self) -> None:
        inc = diff_file("rag/frames.ipynb", "c1", notebook(*DAY1), None)
        self.assertEqual(len(inc.new_cells), 3)
        self.assertFalse(inc.continues)
        self.assertEqual(inc.skipped, "")

    def test_next_day_only_appended_cells(self) -> None:
        # 실제 34기 9/14 → 9/15: 앞 셀은 그대로, 뒤에 셀이 붙었다
        cov = self.cover(notebook(*DAY1))
        inc = diff_file("rag/frames.ipynb", "c2", notebook(*DAY1[:3], *DAY2_EXTRA, DAY1[3]), cov)
        self.assertEqual([c.text.splitlines()[0] for c in inc.new_cells], ["## 프레임 번호 뽑기", "import re"])
        self.assertEqual(len(inc.seen_cells), 3)
        self.assertTrue(inc.continues)

    def test_typo_fix_is_not_new(self) -> None:
        cov = self.cover(notebook(*DAY1))
        edited = [DAY1[0], DAY1[1], ("code", DAY1[2][1].replace("frame_interval=1", "frame_interval=2"))]
        inc = diff_file("rag/frames.ipynb", "c2", notebook(*edited), cov)
        self.assertEqual(inc.new_cells, [])
        self.assertEqual(inc.skipped, "새로 생긴 셀 없음")

    def test_tiny_addition_is_skipped(self) -> None:
        cov = self.cover(notebook(*DAY1))
        inc = diff_file("rag/frames.ipynb", "c2", notebook(*DAY1, ("code", "print(len(frames))")), cov)
        self.assertEqual(len(inc.new_cells), 1)
        self.assertIn("적음", inc.skipped)


class PlanTests(unittest.TestCase):
    def test_quota_follows_new_content_and_sums_to_day_quota(self) -> None:
        big = notebook(("code", LONG * 4))
        mid = notebook(("code", LONG * 2))
        small = notebook(("code", LONG))
        plan = plan_day("d", [("big.ipynb", "c", big), ("mid.ipynb", "c", mid), ("small.ipynb", "c", small)], {})
        quotas = {f.path: f.quota for f in plan.targets}
        self.assertEqual(sum(quotas.values()), DAY_QUOTA)
        # 새 내용 4 : 2 : 1 — 큰 파일이 파일당 상한(8)까지 받는다
        self.assertEqual(quotas, {"big.ipynb": 8, "mid.ipynb": 3, "small.ipynb": 1})
        self.assertTrue(all(1 <= q <= MAX_PER_FILE for q in quotas.values()))

    def test_one_file_caps_at_max(self) -> None:
        plan = plan_day("d", [("only.ipynb", "c", notebook(("code", LONG)))], {})
        self.assertEqual(plan.targets[0].quota, MAX_PER_FILE)

    def test_materials_mark_new_part_and_coverage_grows(self) -> None:
        first = plan_day("2026-09-14", [("f.ipynb", "c1", notebook(*DAY1))], {})
        cov = first.coverage_after({})
        second = plan_day("2026-09-15", [("f.ipynb", "c2", notebook(*DAY1, *DAY2_EXTRA))], cov)
        text = second.materials()[0]["content"]
        self.assertIn("[앞서 배운 부분", text)
        self.assertIn("def extract_frames", text)  # 요약에 정의 이름만
        self.assertNotIn("cv2.VideoCapture", text)  # 앞부분 본문은 넘기지 않는다
        self.assertIn("extract_frame_no", text)
        self.assertIn(f"f.ipynb: {MAX_PER_FILE}개", second.focus_note())
        after = second.coverage_after(cov)["f.ipynb"]
        self.assertEqual(len(after.fingerprints), 5)
        self.assertEqual(after.last_date, "2026-09-15")
        # 원래 기록은 건드리지 않는다
        self.assertEqual(len(cov["f.ipynb"].fingerprints), 3)

    def test_coverage_round_trips_json(self) -> None:
        cov = plan_day("d", [("f.ipynb", "c1", notebook(*DAY1))], {}).coverage_after({})
        again = FileCoverage.from_json(json.loads(json.dumps(cov["f.ipynb"].to_json())))
        self.assertEqual(again, cov["f.ipynb"])


class QuotaTests(unittest.TestCase):
    def test_day_mix_is_two_concepts_and_ten_code(self) -> None:
        self.assertEqual(DAY_QUOTA, 12)
        self.assertEqual(kind_mix(12), KIND_MIX)
        self.assertEqual(KIND_MIX["concept"], 2)
        self.assertEqual(KIND_MIX["code_scratch"], 1)
        self.assertEqual(sum(n for k, n in KIND_MIX.items() if k != "concept"), 10)

    def test_smaller_mix_fills_light_code_first(self) -> None:
        self.assertEqual(kind_mix(3), {"code_output": 1, "code_blank": 1, "concept": 1})
        self.assertEqual(kind_mix(0), {})

    def test_fill_order_adds_up_to_day_mix(self) -> None:
        # 채우는 순서를 끝까지 가면 하루 구성과 같아야 한다 — 둘을 따로 고치다 어긋나지 않게
        from study_notes.practice.increments import _FILL_ORDER
        self.assertEqual(len(_FILL_ORDER), DAY_QUOTA)
        self.assertEqual({k: _FILL_ORDER.count(k) for k in set(_FILL_ORDER)}, KIND_MIX)

    def test_plan_kind_counts_match_total(self) -> None:
        # 파일 하나면 파일당 상한(8)에 걸려 8문제 — 구성도 8개짜리, 처음부터 문제가 하나 들어간다
        plan = plan_day("d", [("only.ipynb", "c", notebook(("code", LONG)))], {})
        self.assertEqual(plan.total, MAX_PER_FILE)
        self.assertEqual(sum(kind_mix(plan.total).values()), plan.total)
        self.assertEqual(kind_mix(plan.total).get("code_scratch"), 1)

    def test_late_commit_uses_only_what_is_left(self) -> None:
        files = [(f"f{i}.ipynb", "c", notebook(("code", LONG))) for i in range(4)]
        self.assertEqual(plan_day("d", files, {}, quota=3).total, 3)
        spent = plan_day("d", files, {}, quota=0)
        self.assertEqual(spent.total, 0)
        self.assertEqual({f.skipped for f in spent.files}, {"하루 몫을 다 냄"})


if __name__ == "__main__":
    unittest.main()
