"""과목 전체 요약 — 수업 파일을 직접 읽어 주제(맨 위 폴더)별로. LLM 은 부르지 않는다(_invoke 를 바꿔 끼운다)."""

from __future__ import annotations

import tempfile
import unittest
from unittest import mock

from study_notes import subject, upload_repo
from study_notes.git_tools import RepoCache, parse_repo_url
from study_notes.subject import Topic


def material(path: str, size: int = 100):
    return {"path": path, "commit": "c", "content": "x" * size, "truncated": False}


class TopicTests(unittest.TestCase):
    def test_heading_has_dates_or_past(self) -> None:
        self.assertEqual("### 04_function · 6/19~6/23", Topic("04_function", ["2026-06-19", "2026-06-23"]).heading)
        self.assertEqual("### 01_variable · 6/18", Topic("01_variable", ["2026-06-18"]).heading)
        self.assertEqual("### 09_exception · 지난 자료", Topic("09_exception").heading)

    def test_invented_topic_headings_go_down_a_level(self) -> None:
        topics = [Topic("05_langchain", ["2026-08-24"])]
        text = "### 05_langchain · 8/24\n- a\n### LCEL\n- b"
        self.assertEqual({"### 05_langchain · 8/24": "- a\n#### LCEL\n- b"}, subject.topic_blocks(text, topics))


class TopicBlocksTests(unittest.TestCase):
    def test_topics_found_even_without_the_section_heading_and_stop_at_next_section(self) -> None:
        # 모델이 「## 주제별 핵심 정리」 줄을 빼먹고 바로 ### 주제부터 썼다(LLM파트 10_sllm_finetuning 이 빠졌던 까닭)
        topics = [Topic("10_sllm", ["2026-09-08"]), Topic("맨 위 파일")]
        text = "### 10_sllm · 9/8\n- 로라\n### 맨 위 파일 · 지난 자료\n- 연습\n## 비교로 기억하기\n| a | b |"
        self.assertEqual({"### 10_sllm · 9/8": "- 로라", "### 맨 위 파일 · 지난 자료": "- 연습"}, subject.topic_blocks(text, topics))


class GenerateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.topics = [Topic(f"0{i}_t", [f"2026-08-1{i}"], [f"0{i}_t/a.py"]) for i in range(1, 4)]
        self.materials = [material(f"0{i}_t/a.py") for i in range(1, 4)]
        self.calls: list[str] = []

    def fake(self, drop: set[str]):
        def invoke(prompt, **values):
            self.calls.append("whole" if prompt is subject.WHOLE else "topics" if prompt is subject.TOPICS_ONLY else "overview")
            if prompt is subject.OVERVIEW:
                return "## 과목 한눈에 보기\n요약\n## 수업 흐름\n| 날짜 | 주제 |"
            names = [t.name for t in self.topics if t.heading in values["topics"] and t.name not in drop]
            body = "\n".join(f"{t.heading}\n- {t.name} 정리" for t in self.topics if t.name in names)
            head = "## 과목 한눈에 보기\n요약\n" if prompt is subject.WHOLE else ""
            return f"{head}## 주제별 핵심 정리\n{body}"
        return invoke

    def test_small_subject_is_one_call_in_topic_order(self) -> None:
        with mock.patch.object(subject, "_invoke", side_effect=self.fake(set())):
            report, _check = subject.generate_subject_from_files(subject="s", topics=self.topics, materials=self.materials)
        self.assertEqual(["whole"], self.calls)
        order = [report.index(t.heading) for t in self.topics]
        self.assertEqual(sorted(order), order)
        self.assertTrue(report.startswith("## 과목 한눈에 보기"))

    def test_missing_topic_is_filled_by_one_more_call(self) -> None:
        dropped = {"02_t"}
        fake = self.fake(dropped)

        def once(prompt, **values):
            out = fake(prompt, **values)
            dropped.clear()  # 다시 부르면 그 주제를 쓴다
            return out

        with mock.patch.object(subject, "_invoke", side_effect=once):
            report, check = subject.generate_subject_from_files(subject="s", topics=self.topics, materials=self.materials)
        self.assertEqual(["whole", "topics"], self.calls)
        self.assertIn("### 02_t · 8/12\n- 02_t 정리", report)
        self.assertLess(report.index("01_t ·"), report.index("02_t ·"))
        self.assertNotIn("못 채운", check)

    def test_big_subject_goes_by_topic_batches_then_overview(self) -> None:
        with mock.patch.object(subject, "SUBJECT_BATCH_CHARS", 150), \
                mock.patch.object(subject, "_invoke", side_effect=self.fake(set())):
            report, _check = subject.generate_subject_from_files(subject="s", topics=self.topics, materials=self.materials)
        self.assertEqual(["topics", "topics", "topics", "overview"], self.calls)
        self.assertIn("## 주제별 핵심 정리\n### 01_t · 8/11", report)
        self.assertIn("## 수업 흐름", report)


class SubjectTopicsTests(unittest.TestCase):
    def test_topics_are_top_folders_with_lesson_dates_and_past_material(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        with mock.patch.dict("os.environ", {"STUDY_NOTES_CACHE_DIR": tmp.name}):
            cache = RepoCache("c", "1", parse_repo_url("upload://c/python_basic"), "main")
            upload_repo.import_all(
                cache,
                {"2026-06-18": {"01_variable/a.py": b"x = 1"}, "2026-06-19": {"04_function/f.py": b"def f(): pass"}},
                past={"09_exception/e.py": b"try: pass\nexcept: pass", "readme.md": b"# hi"},
            )
            upload_repo.commit_day(cache, "2026-06-23", {"04_function/g.py": b"lambda: 1"})
            topics, dates, _head = subject.subject_topics(cache, [])
        self.assertEqual(["2026-06-18", "2026-06-19", "2026-06-23"], dates)
        self.assertEqual(
            [("01_variable", ["2026-06-18"]), ("04_function", ["2026-06-19", "2026-06-23"]), ("09_exception", []), ("맨 위 파일", [])],
            [(t.name, t.dates) for t in topics],
        )


if __name__ == "__main__":
    unittest.main()
