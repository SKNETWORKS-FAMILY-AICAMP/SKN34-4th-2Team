from copy import deepcopy
from datetime import date
from unittest import TestCase

from chatbot.active_policy_rules import allowance_rules, completion_progress
from chatbot.tests.test_active_policy_rules import uploaded
from chatbot.unit_period import calculate_unit_period_context


class PolicyCalendarRuntimeTests(TestCase):
    def context(self, start=date(2026,6,16), end=date(2026,12,8), snapshot=None, numeric=True):
        snapshot = uploaded() if snapshot is None else snapshot
        return calculate_unit_period_context(start, end, today=start,
            scheduled_dates=[start], attendance_records={start:'present'},
            rules=allowance_rules(snapshot) if numeric else None,
            calendar_basis=snapshot.get('calendar_basis'), require_policy=True)

    def test_sixteenth_anchor_and_partial_final_period(self):
        result=self.context()
        self.assertEqual([(p['start_date'],p['end_date']) for p in result['periods']],[
            ('2026-06-16','2026-07-15'),('2026-07-16','2026-08-15'),
            ('2026-08-16','2026-09-15'),('2026-09-16','2026-10-15'),
            ('2026-10-16','2026-11-15'),('2026-11-16','2026-12-08')])
        self.assertEqual(result['calculation_rules']['calendar_method'],'anchored_month_strict')

    def test_undefined_month_end_is_not_clamped(self):
        for start,end in [(date(2026,1,31),date(2026,3,31)),(date(2026,1,30),date(2026,3,30)),(date(2026,1,29),date(2026,3,29))]:
            with self.subTest(start=start):
                result=self.context(start,end)
                self.assertEqual(result['periods'],[])
                self.assertIsNone(result['current_unit_period'])
                self.assertTrue(result['calendar_unavailable_reason'])

    def test_short_final_period_does_not_need_nonexistent_next_anchor(self):
        result=self.context(date(2026,1,31),date(2026,2,10))
        self.assertEqual(len(result['periods']),1)
        self.assertEqual(result['periods'][0]['end_date'],'2026-02-10')

    def test_leap_day_boundary_exists(self):
        result=self.context(date(2028,1,29),date(2028,3,1))
        self.assertEqual(result['periods'][0]['end_date'],'2028-02-28')
        self.assertEqual(result['periods'][1]['start_date'],'2028-02-29')

    def test_missing_or_conflicting_basis_does_not_generate_periods(self):
        for basis in (None,{'status':'missing'},{'status':'conflicting'}):
            s=uploaded();s['calendar_basis']=basis
            with self.subTest(basis=basis):
                with self.assertRaises(ValueError): allowance_rules(s)
                result=self.context(snapshot=s,numeric=False)
                self.assertEqual(result['periods'],[])
                self.assertEqual(result['schedule_status'],'unavailable')

    def test_calendar_can_show_dates_without_numeric_criteria(self):
        result=self.context(numeric=False)
        self.assertEqual(len(result['periods']),6)
        self.assertIsNone(result['calculation_rules'])
        self.assertIsNone(result['periods'][0]['requirement_met'])

    def test_other_policy_calendar_cannot_be_used_with_numeric_criteria(self):
        s=uploaded();s['calendar_basis']=uploaded('cohort_40')['calendar_basis']
        with self.assertRaises(ValueError): allowance_rules(s)
        s=uploaded();s['calendar_basis']=deepcopy(s['calendar_basis']);s['calendar_basis']['document_hash']='f'*64
        with self.assertRaises(ValueError): allowance_rules(s)

    def test_completion_also_stops_without_calendar(self):
        s=uploaded();s['calendar_basis']={'status':'missing'}
        result=completion_progress(s,date(2026,1,1),date(2026,1,31),date(2026,1,2),[date(2026,1,1)],{date(2026,1,1):'present'})
        self.assertIn('unavailable_reason',result)
