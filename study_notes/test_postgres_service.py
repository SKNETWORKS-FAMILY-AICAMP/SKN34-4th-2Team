"""Pure PostgreSQL study-note contract checks; no DB or AI call needed."""

import unittest
from unittest.mock import patch

from study_notes.postgres_service import StudyNotesError, _finish, _note_key, _public_note


class StudyNoteContractTests(unittest.TestCase):
    def test_note_key_is_unique_per_user_and_cohort(self):
        self.assertNotEqual(_note_key(1, "cohort_34", "note"), _note_key(2, "cohort_34", "note"))
        self.assertNotEqual(_note_key(1, "cohort_34", "note"), _note_key(1, "cohort_35", "note"))

    def test_ready_note_keeps_flutter_response_fields(self):
        row = {
            "status": "ready", "source_legacy_id": "src-1", "source_id": 7,
            "scope_type": "date", "scope_value": "2026-09-23", "error_message": None,
            "report_markdown": "report", "review_markdown": "review", "files": [{"path": "a.py"}],
        }
        result = _public_note("src-1_2026-09-23", row)
        self.assertEqual(result["sourceId"], "src-1")
        self.assertEqual(result["reportMarkdown"], "report")
        self.assertEqual(result["reviewMarkdown"], "review")
        self.assertEqual(result["files"], [{"path": "a.py"}])

    def test_missing_note_contract(self):
        self.assertEqual(_public_note("n1", None), {"noteId": "n1", "status": "missing"})

    @patch("study_notes.postgres_service.connect")
    def test_stale_generation_cannot_overwrite_newer_result(self, connect):
        connect.return_value.__enter__.return_value.execute.return_value.rowcount = 0
        with self.assertRaises(StudyNotesError) as caught:
            _finish(7, "old-token", "ready", report_markdown="stale")
        self.assertEqual(caught.exception.status_code, 409)
