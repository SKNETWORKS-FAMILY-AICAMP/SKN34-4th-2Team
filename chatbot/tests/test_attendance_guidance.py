from datetime import date, timedelta
from unittest import TestCase

from chatbot.attendance import enrich_unit_period_context
from chatbot.unit_period import calculate_unit_period_context


class AttendanceGuidanceTests(TestCase):
    def estimate(self, statuses, today_offset=14):
        start = date(2026, 1, 1)
        days = [start + timedelta(days=i) for i in range(18)]
        context = calculate_unit_period_context(start, date(2026,1,31),
            today=start+timedelta(days=today_offset), scheduled_dates=days,
            attendance_records={days[i]: s for i,s in enumerate(statuses) if s})
        return enrich_unit_period_context(context)['periods'][0]['in_progress_estimate']

    def test_two_more_normal_days_and_one_exception_warning(self):
        e = self.estimate(['late']*5+['present']*8+['officialLeave'], today_offset=13)
        self.assertEqual(e['recognized_attendance_days'],13)
        self.assertEqual(e['full_period_required_recognized_days'],15)
        self.assertEqual(e['additional_normal_attendance_days_needed'],2)
        self.assertEqual(e['unrecorded_future_days'],4)
        self.assertEqual(e['additional_absence_equivalent_if_one_more_exception'],1)

    def test_new_normal_day_reduces_remaining_requirement(self):
        e = self.estimate(['late']*5+['present']*9+['officialLeave'],today_offset=14)
        self.assertEqual(e['additional_normal_attendance_days_needed'],1)
        self.assertEqual(e['unrecorded_future_days'],3)

    def test_new_late_day_adds_record_and_absence_conversion(self):
        e = self.estimate(['late']*6+['present']*8+['officialLeave'],today_offset=14)
        self.assertEqual(e['absence_equivalent_days'],2)
        self.assertEqual(e['recognized_attendance_days'],13)
        self.assertEqual(e['additional_normal_attendance_days_needed'],2)
        self.assertEqual(e['exception_count_until_next_absence_equivalent'],3)

    def test_missing_past_or_today_and_future_records_block_projection(self):
        for statuses,offset in ((['present']*12+[None,'present'],13),
                                (['present']*14,14), (['present']*15,13)):
            with self.subTest(statuses=statuses,offset=offset):
                e = self.estimate(statuses,today_offset=offset)
                self.assertIsNone(e['additional_normal_attendance_days_needed'])
                self.assertEqual(e['projection_status'],'records_need_review')

    def test_next_day_scenarios_match_engine_with_new_record(self):
        statuses = ['late']*5+['present']*8+['officialLeave']
        original = self.estimate(statuses,today_offset=13)
        for status, scenario in original['next_scheduled_day_scenarios'].items():
            with self.subTest(status=status):
                actual = self.estimate(statuses+[status],today_offset=14)
                for key in ('exception_count','absence_equivalent_days','recognized_attendance_days',
                            'additional_normal_attendance_days_needed','reachable_with_future_normal_attendance'):
                    self.assertEqual(scenario[key],actual[key])
        late = original['next_scheduled_day_scenarios']['late']
        self.assertEqual(late['recorded_days'],15)
        self.assertEqual(late['recognized_attendance_days'],13)
        self.assertEqual(late['additional_normal_attendance_days_needed'],2)

    def test_incomplete_or_finished_schedule_has_no_scenarios(self):
        for statuses,offset in ((['present']*12+[None,'present'],13),
                                (['present']*14,14), (['present']*15,13), (['present']*18,17)):
            with self.subTest(offset=offset,statuses=statuses):
                self.assertEqual(self.estimate(statuses,today_offset=offset)['next_scheduled_day_scenarios'],{})

    def test_next_day_can_make_target_unreachable(self):
        statuses=['absent']*3+['present']*13
        scenarios=self.estimate(statuses,today_offset=15)['next_scheduled_day_scenarios']
        self.assertTrue(scenarios['present']['reachable_with_future_normal_attendance'])
        self.assertFalse(scenarios['absent']['reachable_with_future_normal_attendance'])
