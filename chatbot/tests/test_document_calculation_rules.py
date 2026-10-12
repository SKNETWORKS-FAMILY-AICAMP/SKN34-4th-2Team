from dataclasses import replace
from datetime import date
import unittest

from chatbot.calculation_rules import load_calculation_rules
from chatbot.document_calculation_rules import (
    extract_candidates, PreviewPolicy, preview_threshold, select_candidate, unit_period_preview_rules,
)
from chatbot.unit_period import calculate_unit_period_context


def rows(cohort='cohort_34', threshold=80, conversion=3, digest='a'*64):
    texts = [f'96일 이상({threshold}% 이상) 이수하면 수료 기준. 전체 훈련기간의 출석률.',
             '단위기간 출석률 80% 이상이면 훈련장려금 지급 대상.',
             f'단위기간 내 지각·조퇴·외출 누적 {conversion}회는 결석 1일로 환산한다.']
    return [{'page_content': text, 'metadata': {'cohort': cohort, 'document_hash': digest,
        'article_number': str(i), 'structure': 'article', 'kind': 'policy',
        'approval_status': 'draft', 'source_name': 'synthetic fixture'}} for i, text in enumerate(texts, 1)]


def policy(cohort='cohort_34', threshold=80, conversion=3):
    return PreviewPolicy(cohort, 'a'*64, date(2026, 1, 1), None,
                         tuple(extract_candidates(rows(cohort, threshold, conversion))))


class DocumentCalculationTests(unittest.TestCase):
    def test_extract_preserves_source_and_unverified_status(self):
        candidates = extract_candidates(rows())
        self.assertEqual(len(candidates), 3)
        for c in candidates:
            self.assertIn(c.evidence, c.article_text)
            self.assertEqual(c.review_status, 'unverified')
            self.assertEqual(c.source_status, 'draft')

    def test_different_cohorts_same_day(self):
        policies = [policy(), policy('cohort_40', 90)]
        values = [preview_threshold(policies, cohort=c, purpose='completion', as_of=date(2026,10,8),
                  recognized=85, total=100, denominator='whole_course')['requirement_met']
                  for c in ('cohort_34', 'cohort_40')]
        self.assertEqual(values, [True, False])

    def test_completion_not_used_for_allowance(self):
        p = policy('cohort_40', 90)
        result = preview_threshold([p], cohort=p.cohort, purpose='allowance', as_of=date(2026,10,8),
            recognized=85, total=100, denominator='unit_period')
        self.assertTrue(result['requirement_met'])
        with self.assertRaises(ValueError):
            preview_threshold([p], cohort=p.cohort, purpose='completion', as_of=date(2026,10,8),
                recognized=85, total=100, denominator='unit_period')

    def test_exact_boundary_without_rounding(self):
        p = policy(threshold=66.7)
        result = preview_threshold([p], cohort=p.cohort, purpose='completion', as_of=date(2026,10,8),
            recognized=2, total=3, denominator='whole_course')
        self.assertFalse(result['requirement_met'])

    def test_missing_and_conflicting_rules_stop(self):
        p = policy()
        for policies in ([], [replace(p, candidates=())], [p,p],
                         [replace(p, candidates=p.candidates+(p.candidates[0],))]):
            with self.subTest(policies=policies), self.assertRaises(ValueError):
                select_candidate(policies, cohort=p.cohort, purpose='completion', as_of=date(2026,10,8))

    def test_date_ranges_and_version_isolation(self):
        p = policy()
        old = replace(p, effective_until=date(2026,10,8))
        new = replace(policy(threshold=90), effective_from=date(2026,10,8))
        self.assertEqual(select_candidate([old,new],cohort=p.cohort,purpose='completion',as_of=date(2026,10,7)).value,'80')
        self.assertEqual(select_candidate([old,new],cohort=p.cohort,purpose='completion',as_of=date(2026,10,8)).value,'90')
        with self.assertRaises(ValueError):
            replace(p, candidates=policy('cohort_40').candidates)
        with self.assertRaises(ValueError):
            replace(p, effective_from=None)

    def test_unsupported_wording_is_not_guessed(self):
        source = rows()
        source[0]['page_content'] = '출석률은 개별 협의한다.'
        self.assertFalse(any(c.purpose == 'completion' for c in extract_candidates(source)))
        with self.assertRaises(ValueError):
            extract_candidates(source+source)

    def test_changed_conversion_reaches_existing_engine(self):
        p = policy(conversion=2)
        rules = unit_period_preview_rules([p], cohort=p.cohort, as_of=date(2026,1,1),
            period_start=date(2026,1,1),period_end=date(2026,1,31),calendar_rules=load_calculation_rules())
        days = [date(2026,1,n) for n in range(1,6)]
        context = calculate_unit_period_context(days[0], date(2026,1,31), today=days[0],
            scheduled_dates=days, attendance_records=dict(zip(days,['late']*4+['present'])),rules=rules)
        self.assertEqual(context['periods'][0]['absence_equivalent_days'],2)
        self.assertFalse(context['periods'][0]['requirement_met'])

    def test_mid_period_change_stops(self):
        old = replace(policy(), effective_until=date(2026,1,15))
        new = replace(policy(conversion=2),effective_from=date(2026,1,15))
        with self.assertRaises(ValueError):
            unit_period_preview_rules([old,new],cohort=old.cohort,as_of=date(2026,1,20),
                period_start=date(2026,1,1),period_end=date(2026,1,31),calendar_rules=load_calculation_rules())

    def test_invalid_counts_stop(self):
        for recognized,total in ((1,0),(2,1),(-1,10),(True,10)):
            with self.subTest(recognized=recognized,total=total), self.assertRaises(ValueError):
                preview_threshold([policy()],cohort='cohort_34',purpose='completion',as_of=date(2026,10,8),
                    recognized=recognized,total=total,denominator='whole_course')
