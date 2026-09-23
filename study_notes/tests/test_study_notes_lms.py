"""LMS(Django) 창구 — Firestore 없이 저장소 정보를 받아 노트를 만든다.

저장소를 실제로 받거나 LLM 을 부르지 않는다. build_note 만 바꿔 끼워 범위 검사와 돌려주는 모양을 본다.
"""

from __future__ import annotations

import unittest
from unittest import mock

from fastapi import HTTPException

from study_notes import service
from study_notes.git_tools import GitToolError

SOURCE = {
    "id": "multimodal",
    "title": "멀티모달",
    "repoUrl": "https://github.com/skn34/multimodal",
    "branch": "main",
    "allowedPrefixes": ["/01_cnn/", "02_rag", "../secret"],
}
READY = {"status": "ready", "commits": ["c1"], "files": [{"path": "01_cnn/a.ipynb", "commit": "c1"}],
         "reportMarkdown": "요약", "reviewMarkdown": "복습"}


class SourceFromPayloadTests(unittest.TestCase):
    def test_normalizes_prefixes_and_drops_parent_paths(self) -> None:
        source = service.source_from_payload(SOURCE)
        self.assertEqual(source.allowed_prefixes, ["01_cnn", "02_rag"])
        self.assertEqual(source.branch, "main")

    def test_rejects_non_github_url(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            service.source_from_payload({**SOURCE, "repoUrl": "https://example.com/x"})
        self.assertEqual(ctx.exception.status_code, 422)


class BuildNoteForLmsTests(unittest.TestCase):
    def build(self, scope_type: str, value: object, result: dict | Exception = READY) -> dict:
        source = service.source_from_payload(SOURCE)
        effect = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
        with mock.patch.object(service, "build_note", **effect) as fake:
            out = service.build_note_for_lms("cohort_34", source, scope_type, value)
        self.fake = fake
        return out

    def test_files_are_sorted_and_keyed_like_firestore_notes(self) -> None:
        out = self.build("files", ["02_rag/b.py", "01_cnn/a.ipynb", "01_cnn/a.ipynb"])
        self.assertEqual(out["scopeValue"], ["01_cnn/a.ipynb", "02_rag/b.py"])
        self.assertEqual(out["scopeKey"], service.build_scope_key("files", ["01_cnn/a.ipynb", "02_rag/b.py"]))
        self.assertEqual(out["reportMarkdown"], "요약")
        self.assertEqual(self.fake.call_args.args[2:], ("files", ["01_cnn/a.ipynb", "02_rag/b.py"]))

    def test_scope_outside_allowed_folders_is_rejected_before_building(self) -> None:
        source = service.source_from_payload(SOURCE)
        with mock.patch.object(service, "build_note") as fake, self.assertRaises(HTTPException) as ctx:
            service.build_note_for_lms("cohort_34", source, "prefix", "03_private")
        self.assertEqual(ctx.exception.status_code, 422)
        fake.assert_not_called()

    def test_too_broad_passes_through(self) -> None:
        broad = {"status": "too_broad", "message": "파일을 선택하세요.", "files": []}
        out = self.build("date", "2026-09-11", broad)
        self.assertEqual(out["status"], "too_broad")
        self.assertEqual(out["scopeKey"], "2026-09-11")

    def test_git_failure_becomes_502_with_reason(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.build("date", "2026-09-11", GitToolError("저장소를 받지 못했습니다."))
        self.assertEqual(ctx.exception.status_code, 502)
        self.assertIn("저장소", ctx.exception.detail)


class LmsScopeParityTests(unittest.TestCase):
    """Django(lms_api/lms/study_scope.py)가 만드는 노트 키가 여기 규칙과 같아야 한다 —
    어긋나면 같은 범위를 눌러도 노트를 못 찾고 매번 새로 만든다."""

    def test_same_key_and_value_as_ai_server(self) -> None:
        import importlib.util
        from pathlib import Path

        path = Path(__file__).resolve().parents[2] / "lms_api" / "lms" / "study_scope.py"
        spec = importlib.util.spec_from_file_location("lms_study_scope", path)
        lms = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(lms)

        cases = [
            ("date", "2026-09-11"),
            ("prefix", "01_cnn/"),
            ("prefix", "수업 자료/1주차"),
            ("files", ["02_rag/b.py", "\\01_cnn\\a.ipynb", "01_cnn/a.ipynb"]),
        ]
        for scope_type, raw in cases:
            ours = service.normalize_scope_value(scope_type, raw)
            theirs = lms.normalize_scope(scope_type, raw)
            self.assertEqual(theirs, ours, raw)
            self.assertEqual(lms.scope_key(scope_type, theirs), service.build_scope_key(scope_type, ours), raw)

        for scope_type, raw in [("date", "2026-02-30"), ("files", []), ("prefix", "../x"), ("week", "1")]:
            with self.assertRaises(HTTPException):
                service.normalize_scope_value(scope_type, raw) if scope_type != "week" else service.parse_scope_type(scope_type)
            with self.assertRaises(lms.ScopeError):
                lms.normalize_scope(scope_type, raw)


if __name__ == "__main__":
    unittest.main()
