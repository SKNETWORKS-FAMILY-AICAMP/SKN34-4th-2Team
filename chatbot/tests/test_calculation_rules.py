from dataclasses import replace
from datetime import date, timedelta
from unittest import TestCase
from unittest.mock import patch

from chatbot.attendance import enrich_unit_period_context
from chatbot.calculation_rules import CalculationRules, load_calculation_rules
from chatbot.unit_period import calculate_unit_period_context


class CalculationRulesTests(TestCase):
    def context(self, rules, statuses):
        start = date(2026, 1, 1)
        days = [start + timedelta(days=i) for i in range(len(statuses))]
        return calculate_unit_period_context(
            start, date(2026, 1, 31), today=start, rules=rules,
            scheduled_dates=days, attendance_records=dict(zip(days, statuses)),
        )

    def test_bundled_values_are_explicitly_unverified(self):
        context = self.context(load_calculation_rules(), ['present'])
        self.assertEqual(context['calculation_rules']['review_status'], 'unverified')
        self.assertEqual(context['schedule_status'], 'generated_unconfirmed')
        self.assertTrue(context['is_provisional'])

    def test_custom_rules_used_by_both_calculations_and_notes(self):
        rules = replace(load_calculation_rules(), attendance_threshold_percent=90, exceptions_per_absence=2)
        context = self.context(rules, ['late', 'late', 'late', 'late', 'present'])
        period = enrich_unit_period_context(context)['periods'][0]
        self.assertEqual(period['absence_equivalent_days'], 2)
        self.assertEqual(period['in_progress_estimate']['absence_equivalent_days'], 2)
        self.assertFalse(period['requirement_met'])
        self.assertFalse(period['in_progress_estimate']['requirement_met_so_far'])
        self.assertEqual(period['in_progress_estimate']['full_period_required_recognized_days'], 5)
        self.assertIn('90%', ' '.join(context['calculation_notes']))
        self.assertIn('2회', ' '.join(context['calculation_notes']))

    def test_rounding_does_not_change_eligibility(self):
        # 2/3 displays as 66.7%, but is still less than a 66.7% threshold.
        rules = replace(load_calculation_rules(), attendance_threshold_percent=66.7)
        period = self.context(rules, ['present', 'present', 'absent'])['periods'][0]
        self.assertEqual(period['attendance_rate'], 66.7)
        self.assertFalse(period['requirement_met'])
        self.assertTrue(rules.requirement_met(667, 1000))

    def test_missing_records_do_not_become_final_results(self):
        context = calculate_unit_period_context(date(2026, 1, 1), date(2026, 1, 31),
            today=date(2026, 1, 2), scheduled_dates=[date(2026, 1, 1)], attendance_records={})
        self.assertIsNone(context['periods'][0]['requirement_met'])
        self.assertIsNone(enrich_unit_period_context(context)['periods'][0]['in_progress_estimate']['requirement_met_so_far'])

    def test_missing_or_invalid_snapshot_never_uses_legacy_fallback(self):
        for metadata in (None, {}, {'attendance_threshold_percent': 80}):
            context = {'current_unit_period': 1, 'calculation_rules': metadata,
                       'periods': [{'number': 1, 'in_progress_estimate': {'old': True}}]}
            result = enrich_unit_period_context(context)
            self.assertNotIn('in_progress_estimate', result['periods'][0])
            self.assertIn('estimate_unavailable_reason', result)
            self.assertIn('in_progress_estimate', context['periods'][0])

    def test_invalid_configuration_is_rejected(self):
        for changes in ({'attendance_threshold_percent': 0}, {'attendance_threshold_percent': 101},
                        {'attendance_threshold_percent': True}, {'attendance_threshold_percent': float('nan')},
                        {'exceptions_per_absence': 0}, {'exceptions_per_absence': 2.5},
                        {'calendar_method': 'every_30_days'}, {'review_status': 'approved'}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(load_calculation_rules(), **changes)

    def test_missing_config_stops_calculation(self):
        with patch('chatbot.calculation_rules.Path.read_text', side_effect=FileNotFoundError), self.assertRaises(FileNotFoundError):
            self.context(load_calculation_rules(), ['present'])
