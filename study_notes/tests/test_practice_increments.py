"""파일 단위 출제 — 새로 생긴 셀만 골라내는지."""

from __future__ import annotations

import json
import unittest

from study_notes.practice.increments import (
    BATCH,
    DAY_QUOTA,
    KIND_MIX,
    MAX_DAY,
    MIN_DAY,
    FileCoverage,
    day_quota,
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
    def test_quota_follows_new_content(self) -> None:
        big = notebook(("code", LONG * 4))
        mid = notebook(("code", LONG * 2))
        small = notebook(("code", LONG))
        plan = plan_day("d", [("big.ipynb", "c", big), ("mid.ipynb", "c", mid), ("small.ipynb", "c", small)], {}, quota=DAY_QUOTA)
        quotas = {f.path: f.quota for f in plan.targets}
        self.assertEqual(sum(quotas.values()), DAY_QUOTA)
        # 새 내용 4 : 2 : 1 — 파일당 상한 없이 새 내용이 많은 파일이 더
        self.assertEqual(quotas, {"big.ipynb": 8, "mid.ipynb": 3, "small.ipynb": 1})

    def test_one_small_file_gets_the_day_minimum(self) -> None:
        plan = plan_day("d", [("only.ipynb", "c", notebook(("code", LONG)))], {})
        self.assertEqual(plan.targets[0].quota, MIN_DAY)

    def test_materials_mark_new_part_and_coverage_grows(self) -> None:
        first = plan_day("2026-09-14", [("f.ipynb", "c1", notebook(*DAY1))], {})
        cov = first.coverage_after({})
        second = plan_day("2026-09-15", [("f.ipynb", "c2", notebook(*DAY1, *DAY2_EXTRA))], cov)
        text = second.materials()[0]["content"]
        self.assertIn("[앞서 배운 부분", text)
        self.assertIn("def extract_frames", text)  # 요약에 정의 이름만
        self.assertNotIn("cv2.VideoCapture", text)  # 앞부분 본문은 넘기지 않는다
        self.assertIn("extract_frame_no", text)
        self.assertIn(f"f.ipynb: {MIN_DAY}개", second.focus_note())
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
        # 작은 파일 하나면 하한 8문제 — 구성도 8개짜리, 처음부터 문제가 하나 들어간다
        plan = plan_day("d", [("only.ipynb", "c", notebook(("code", LONG)))], {})
        self.assertEqual(plan.total, MIN_DAY)
        self.assertEqual(sum(kind_mix(plan.total).values()), plan.total)
        self.assertEqual(kind_mix(plan.total).get("code_scratch"), 1)

    def test_mixed_day_gives_sql_only_the_sql_files_share(self) -> None:
        # 파이썬 파일 여럿 + .sql 하나 — SQL 문제는 .sql 몫만, 나머지는 파이썬 구성(web_crawling 07-01)
        files = [(f"f{i}.ipynb", "c", notebook(("code", LONG))) for i in range(7)]
        files.append(("book.sql", "c", "SELECT title FROM book WHERE price > 1000;\n" * 20))
        plan = plan_day("d", files, {})
        sql_share = sum(f.quota for f in plan.targets if f.path.endswith(".sql"))
        counts = plan.kind_counts()
        self.assertGreater(sql_share, 0)
        self.assertIn(f"sql_query {sql_share}개", counts)
        self.assertIn("code_output", counts)

    def test_file_without_code_gets_at_most_two_concepts(self) -> None:
        # LLM파트 09-07 — 설명만 있는 긴 노트북이 5문제를 받아 코드 문제를 못 냈다
        overview = notebook(("markdown", "# RunPod 소개\n" + "GPU 클라우드 설명 문장입니다. " * 300))
        lesson = notebook(*[("code", f"x{i} = {i}\n" * 40) for i in range(13)])
        plan = plan_day("d", [("01_overview.ipynb", "c", overview), ("02_sllm.ipynb", "c", lesson)], {})
        quota = {f.path: f.quota for f in plan.targets}
        self.assertEqual(quota["01_overview.ipynb"], 2)
        # 나머지는 코드 있는 수업 파일이 — 하루 몫은 새 내용 양으로
        self.assertEqual(plan.total, day_quota(sum(f.new_chars for f in plan.targets)))
        counts = plan.kind_counts()
        self.assertIn("concept 2개", counts)
        self.assertIn("01_overview.ipynb: 2개 (코드 없음 — concept 문제만)", plan.focus_note())

    def test_many_codeless_files_turn_code_slots_into_concepts(self) -> None:
        files = [(f"{i}.md", "c", f"# 제목 {i}\n" + "설명 " * 400) for i in range(3)]
        files.append(("lesson.py", "c", "\n\n".join(f"def f{i}(x):\n    return x + {i}" for i in range(40))))
        plan = plan_day("d", files, {})
        concept_only = sum(f.quota for f in plan.targets if not f.has_code)
        counts = dict(part.rsplit(" ", 1) for part in plan.kind_counts().split(", "))
        self.assertEqual(int(counts["concept"].rstrip("개")), concept_only)
        self.assertEqual(sum(int(v.rstrip("개")) for v in counts.values()), plan.total)

    def test_sql_only_day_is_all_sql(self) -> None:
        plan = plan_day("d", [("book.sql", "c", "SELECT title FROM book WHERE price > 1000;\n" * 40)], {})
        self.assertNotIn("code_output", plan.kind_counts())
        self.assertIn("sql_query", plan.kind_counts())

    def test_late_commit_uses_only_what_is_left(self) -> None:
        files = [(f"f{i}.ipynb", "c", notebook(("code", LONG))) for i in range(4)]
        self.assertEqual(plan_day("d", files, {}, quota=3).total, 3)
        spent = plan_day("d", files, {}, quota=0)
        self.assertEqual(spent.total, 0)
        self.assertEqual({f.skipped for f in spent.files}, {"하루 몫을 다 냄"})


if __name__ == "__main__":
    unittest.main()


class DayQuotaTests(unittest.TestCase):
    """하루 문제 수 — 새 내용 양으로(8 ~ 25). 34기 실제 수업일 새 내용으로 맞춘 값"""

    def test_real_days(self) -> None:
        real = {3331: 8, 4177: 8, 9626: 9, 16578: 12, 34056: 18, 46517: 20, 82318: 25}
        self.assertEqual(real, {n: day_quota(n) for n in real})
        self.assertEqual(0, day_quota(0))

    def test_late_commit_adds_only_what_it_brought(self) -> None:
        # 같은 날 12문제를 낸 뒤 조금 더 올림 — 하한 8 을 다시 채우지 않는다
        self.assertEqual(2, day_quota(500, already=12))
        self.assertEqual(MAX_DAY - 20, day_quota(80_000, already=20))
        self.assertEqual(0, day_quota(5_000, already=MAX_DAY))

    def test_big_mix_keeps_the_ratio(self) -> None:
        mix = kind_mix(25)
        self.assertEqual(25, sum(mix.values()))
        self.assertEqual(KIND_MIX.keys(), mix.keys())
        self.assertTrue(all(mix[k] >= 2 * KIND_MIX[k] for k in KIND_MIX))
        js = kind_mix(25, js=True)
        self.assertEqual(25, sum(js.values()))
        self.assertEqual(8, js["concept"])

    def test_big_day_is_split_into_batches(self) -> None:
        files = [(f"f{i}.ipynb", "c", notebook(("code", LONG * 12))) for i in range(5)]
        plan = plan_day("d", files, {})
        self.assertGreater(plan.total, BATCH)
        parts = plan.batches()
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(p.total <= BATCH for p in parts))
        self.assertEqual(plan.total, sum(p.total for p in parts))
        # 출제 기록은 나누기 전 계획 그대로
        self.assertEqual(5, len(plan.coverage_after({})))

    def test_one_huge_file_is_cut_by_cells_and_later_part_sees_the_earlier(self) -> None:
        # 셀끼리 90% 넘게 같으면 같은 셀로 본다 — 서로 다른 내용으로
        cells = [("code", "".join(f"step{i}_{j} = {i * j} + {j}\n" for j in range(150))) for i in range(10)]
        plan = plan_day("d", [("big.ipynb", "c", notebook(*cells))], {})
        self.assertGreater(plan.total, BATCH)
        parts = plan.batches()
        self.assertEqual(2, len(parts))
        self.assertEqual(plan.total, sum(p.total for p in parts))
        first, second = parts[0].targets[0], parts[1].targets[0]
        self.assertEqual(10, len(first.new_cells) + len(second.new_cells))
        self.assertEqual(first.new_cells, second.seen_cells)
        self.assertIn("[앞서 배운 부분", parts[1].materials()[0]["content"])
