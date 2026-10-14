"""파일이 많은 날의 노트 — 묶음마다 부분 노트를 만들고 하나로 합친다(pipeline._note_in_batches).

LLM 을 부르지 않는다. 부분 노트(_note)와 합치기 호출(_llm)을 바꿔 끼워 묶는 법과 합친 모양을 본다.
"""

from __future__ import annotations

import unittest
from unittest import mock

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from study_notes import pipeline


def material(path: str) -> pipeline.Material:
    return {"path": path, "commit": "c1", "content": f"<{path}>", "truncated": False}


def part_note(label: str) -> str:
    return "\n".join(f"## {h}\n{label} {h}" for h in pipeline.NOTE_HEADS)


class BatchTests(unittest.TestCase):
    def test_splits_evenly_by_path(self) -> None:
        files = [material(f"02_css/{i:02}.html") for i in range(13)] + [material(f"01_html/{i:02}.html") for i in range(26)]
        batches = pipeline._batches(files)
        self.assertEqual([len(b) for b in batches], [8, 8, 8, 8, 7])
        self.assertEqual(batches[0][0]["path"], "01_html/00.html")
        self.assertEqual(batches[-1][-1]["path"], "02_css/12.html")

    def test_nine_files_make_two_batches(self) -> None:
        self.assertEqual([len(b) for b in pipeline._batches([material(f"{i}.py") for i in range(9)])], [5, 4])


class SectionsTests(unittest.TestCase):
    def test_unknown_heading_stays_in_previous_section(self) -> None:
        sections = pipeline._sections("## 개념별 정리\na\n## 따로 붙인 제목\nb\n## 자주 하는 실수\nc")
        self.assertEqual(sections["개념별 정리"], "a\n## 따로 붙인 제목\nb")
        self.assertEqual(sections["자주 하는 실수"], "c")

    def test_legacy_headings_are_still_read(self) -> None:
        # 다시 만들기 전 예전 형식 노트도 「이전 수업」으로 읽는다
        sections = pipeline._sections("## 오늘의 핵심 한 문장\nx\n## 파일별 학습 내용\ny")
        self.assertEqual(sections, {"오늘의 핵심 한 문장": "x", "파일별 학습 내용": "y"})


class NoteInBatchesTests(unittest.TestCase):
    def run_batches(self, merged: str, count: int = 10) -> tuple[str, str, list[str]]:
        labels: list[str] = []
        self.code_limits: list[int] = []

        def fake_note(label: str, packed: str, previous: str, code_limit: int) -> str:
            labels.append(label)
            self.code_limits.append(code_limit)
            return part_note(label.rsplit(" ", 1)[-1])

        llm = RunnableLambda(lambda _prompt: AIMessage(content=merged))
        with mock.patch.object(pipeline, "_note", side_effect=fake_note), mock.patch.object(pipeline, "_llm", return_value=llm):
            report, packed = pipeline._note_in_batches("2026-09-23", [material(f"{i:02}.html") for i in range(count)])
        return report, packed, labels

    def test_merge_rewrites_the_whole_note_by_concept(self) -> None:
        # 개념 중심이라 부분 노트를 이어 붙이지 않는다 — 합치는 호출이 개념을 모아 하나로 다시 쓴다
        merged = "머리글\n" + "\n".join(f"## {h}\n합친 {h}" for h in pipeline.NOTE_HEADS)
        report, packed, labels = self.run_batches(merged)
        self.assertEqual(sorted(labels), ["2026-09-23 — 파일 묶음 1/2", "2026-09-23 — 파일 묶음 2/2"])
        self.assertEqual(self.code_limits, [6, 6], "하루 코드 블록 수를 묶음끼리 나눈다")
        self.assertIn("## 개념별 정리\n합친 개념별 정리", report)
        self.assertNotIn("1/2 개념별 정리", report)
        self.assertTrue(report.startswith("## 오늘 꼭 알아야 할 것"))
        # 소제목은 NOTE_HEADS 순서 그대로
        order = [report.index(f"## {h}") for h in pipeline.NOTE_HEADS]
        self.assertEqual(order, sorted(order))
        # 대조(grounding)용 자료에는 모든 파일이 들어 있다
        self.assertIn("<00.html>", packed)
        self.assertIn("<09.html>", packed)

    def test_missing_summary_heading_falls_back_to_parts(self) -> None:
        report, _packed, _labels = self.run_batches("## 오늘 꼭 알아야 할 것\n합친 요점")
        self.assertIn("## 오늘 꼭 알아야 할 것\n합친 요점", report)
        # 합친 답에 개념 정리가 빠지면 부분 노트의 개념을 이어 붙인다(빠지는 것보다 낫다)
        self.assertIn("## 개념별 정리\n1/2 개념별 정리\n\n2/2 개념별 정리", report)

    def test_few_files_use_single_call(self) -> None:
        with mock.patch.object(pipeline, "_note", return_value="## 오늘 꼭 알아야 할 것\n하나") as note, \
                mock.patch.object(pipeline, "_note_in_batches") as batches:
            pipeline.generate_study_note(scope_label="d", commits=[], materials=[material(f"{i}.py") for i in range(8)])
        note.assert_called_once()
        batches.assert_not_called()


class PackMaterialsTests(unittest.TestCase):
    def test_every_file_gets_a_share_and_short_files_stay_whole(self) -> None:
        # LLM파트 08-19 — 앞 파일이 예산을 다 써 뒤 파일이 생략되던 날
        sizes = [("a.ipynb", 19_000), ("b.ipynb", 8_700), ("c.ipynb", 15_600), ("d.ipynb", 5_600), ("e.ipynb", 3_700), ("f.ipynb", 320)]
        mats = [{"path": p, "commit": "c", "content": p[0] * n, "truncated": False} for p, n in sizes]
        packed = pipeline.pack_materials(mats)
        self.assertNotIn("분량 제한으로 생략", packed)
        body = {p: packed.split(f"### {p}")[1].split("\n", 1)[1].split("\n\n###")[0] for p, _ in sizes}
        self.assertEqual(len(body["f.ipynb"]), 320)
        self.assertEqual(len(body["e.ipynb"]), 3_700)
        self.assertLessEqual(sum(len(b) for b in body.values()), pipeline.MAX_TOTAL_CHARS)
        self.assertGreater(len(body["d.ipynb"]), 5_000)
        self.assertIn("### a.ipynb (일부만)", packed)

    def test_small_day_is_untouched(self) -> None:
        mats = [{"path": "a.py", "commit": "c", "content": "x = 1", "truncated": False}]
        self.assertEqual(pipeline.pack_materials(mats), "### a.py\nx = 1")


class TidyHeadingsTests(unittest.TestCase):
    def test_extra_h2_becomes_a_concept_heading_and_path_label_is_dropped(self) -> None:
        note = "## 개념별 정리\n## 리스트\n## 파일 경로: `01_html/09_iframe.html`\n### 파일 경로: `a.css`\n## 자주 하는 실수"
        self.assertEqual(pipeline.tidy_headings(note),
                         "## 개념별 정리\n### 리스트\n### `01_html/09_iframe.html`\n### `a.css`\n## 자주 하는 실수")

    def test_preface_before_first_heading_is_dropped(self) -> None:
        self.assertEqual(pipeline.tidy_headings("핵심은 변수입니다.\n\n## 오늘 꼭 알아야 할 것\n- a"), "## 오늘 꼭 알아야 할 것\n- a")


class PreviousTests(unittest.TestCase):
    def test_takes_recent_days_in_order_with_summary_sections_only(self) -> None:
        days = [{"date": f"2026-06-{d}", "report": part_note(d)} for d in ("22", "18", "19", "23")]
        text = pipeline.pack_previous(days)
        self.assertEqual([line for line in text.split("\n") if line.startswith("### ")],
                         ["### 2026-06-19", "### 2026-06-22", "### 2026-06-23"])
        self.assertIn("22 오늘 꼭 알아야 할 것", text)
        self.assertNotIn("개념별 정리", text)
        # 예전 형식 노트(다시 만들기 전)도 요점만 읽는다
        legacy = pipeline.pack_previous([{"date": "2026-06-17", "report": "## 오늘의 핵심 한 문장\n옛 요점\n## 파일별 학습 내용\n긴 해설"}])
        self.assertIn("옛 요점", legacy)
        self.assertNotIn("긴 해설", legacy)

    def test_nothing_before_is_marked(self) -> None:
        self.assertEqual(pipeline.pack_previous([]), pipeline.NO_PREVIOUS)
        self.assertEqual(pipeline.pack_previous([{"date": "2026-06-18", "report": "소제목 없는 글"}]), pipeline.NO_PREVIOUS)

    def test_previous_reaches_prompt(self) -> None:
        seen: dict = {}
        with mock.patch.object(pipeline, "_note", side_effect=lambda label, packed, prev: seen.update(prev=prev) or "") as note:
            pipeline.generate_study_note(scope_label="d", commits=[], materials=[material("a.py")],
                                         previous=[{"date": "2026-06-18", "report": part_note("18")}])
        note.assert_called_once()
        self.assertIn("### 2026-06-18\n18 오늘 꼭 알아야 할 것", seen["prev"])


if __name__ == "__main__":
    unittest.main()
