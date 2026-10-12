from datetime import date
from unittest import TestCase
from unittest.mock import MagicMock, patch

from lms import commands  # Initialize the existing command registry first.
from lms.content_commands import op_replace_curriculum_sheet


def row(day, label):
    return {'dayIndex':day,'dateLabel':label,'subject':'수업','topic':'','detail':''}


class CurriculumSaveValidationTests(TestCase):
    def call(self, rows, start=date(2026,6,16), end=date(2026,12,8)):
        cur=MagicMock()
        cur.description=[('start_date',),('end_date',)]
        cur.fetchone.side_effect=[(start,end),(9,)]
        with patch('lms.content_commands._require_staff'), patch('lms.content_commands._cohort_for',return_value=1):
            try:
                result=op_replace_curriculum_sheet(cur,{'id':1},{'rows':rows,'cohortId':'cohort_34'})
            except ValueError:
                self.assertFalse(any(c.args[0].lstrip().upper().startswith(('DELETE','INSERT','UPDATE')) for c in cur.execute.call_args_list))
                raise
        return result,cur

    def test_actual_duplicate_is_rejected_before_any_write(self):
        with self.assertRaises(ValueError):
            self.call([row(101,'2026년 11월 11일 수요일'),row(110,'2026년 11월 24일 화요일'),row(111,'2026년 11월 11일 수요일')])

    def test_corrected_dates_are_saved_and_original_labels_preserved(self):
        rows=[row(101,'2026년 11월 11일 수요일'),row(110,'2026년 11월 24일 화요일'),row(111,'2026년 11월 25일 수요일')]
        _,cur=self.call(rows)
        inserts=[c for c in cur.execute.call_args_list if 'INSERT INTO curriculum_rows' in c.args[0]]
        self.assertEqual(len(inserts),3)
        self.assertEqual(inserts[-1].args[1][2],rows[-1]['dateLabel'])

    def test_same_day_multiple_subjects_allowed(self):
        self.call([row(1,'2026-06-16'),row(1,'2026-06-16')])

    def test_invalid_and_conflicting_inputs_leave_old_sheet(self):
        cases=[[],None,[None],[row(True,'2026-06-16')],[row(1.5,'2026-06-16')],
            [row(0,'2026-06-16')],[row(1,'2026-02-30')],[row(1,'2026년 6월 16일 월요일')],
            [row(1,'2026-06-15')],[row(1,'2026-06-17'),row(2,'2026-06-16')],
            [row(1,'2026-06-16'),row(1,'2026-06-17')],[row(1,'날짜 오기')]]
        for rows in cases:
            with self.subTest(rows=rows),self.assertRaises(ValueError):self.call(rows)

    def test_payload_order_does_not_override_day_index(self):
        self.call([row(2,'2026/06/17'),row(1,'2026.06.16')])

    def test_undated_plan_and_unique_yearless_date(self):
        self.call([row(1,'1일차'),row(2,'6/17'),row(3,'')])

    def test_ambiguous_yearless_date_rejected(self):
        with self.assertRaises(ValueError):self.call([row(1,'6/17')],date(2026,1,1),date(2027,12,31))
