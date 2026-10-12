from dataclasses import replace
from unittest import TestCase

from chatbot.active_policy_rules import extract_calendar_basis
from chatbot.tests.test_regulation_ingestion import regulation_bytes, upload_records


CLAUSES = [
    '단위기간은 훈련 시작일을 기준으로 매월 같은 일자부터 다음 달 같은 일자의 전날까지로 한다.',
    '마지막 단위기간은 훈련 종료일에 종료한다.',
    '단위기간 내 실제 수업일수는 해당 기수의 수업 일정에 따라 산정한다.',
]


def records(clauses=None, cohort='cohort_34'):
    return upload_records(regulation_bytes([('제5조(단위기간의 산정)', CLAUSES if clauses is None else clauses)]), cohort)


class CalendarBasisTests(TestCase):
    def test_actual_docx_parser_preserves_source_and_does_not_invent_month_end(self):
        result = extract_calendar_basis(records(), 'cohort_34')
        self.assertEqual(result['status'], 'extracted')
        self.assertEqual(result['article'], '5')
        self.assertEqual(result['month_end_handling'], 'unspecified')
        self.assertEqual(result['end'], 'next_start_minus_one_day')
        self.assertTrue(all(c in result['evidence'] for c in CLAUSES))

    def test_each_missing_clause_stays_missing(self):
        for i in range(3):
            with self.subTest(i=i):
                self.assertEqual(extract_calendar_basis(records(CLAUSES[:i]+CLAUSES[i+1:]), 'cohort_34')['status'], 'missing')

    def test_other_cohort_cannot_supply_basis(self):
        self.assertEqual(extract_calendar_basis(records(cohort='cohort_40'), 'cohort_34')['status'], 'missing')

    def test_identical_split_source_is_deduplicated(self):
        row = records()[0]
        self.assertEqual(extract_calendar_basis([row, replace(row, page_content='fragment')], 'cohort_34')['status'], 'extracted')

    def test_differing_duplicate_article_is_conflicting(self):
        row = records()[0]
        other = replace(row, source=replace(row.source, text=row.source.text+' 예외 규칙.'))
        self.assertEqual(extract_calendar_basis([row, other], 'cohort_34')['status'], 'conflicting')

    def test_different_documents_do_not_combine_partial_clauses(self):
        self.assertEqual(extract_calendar_basis(records(CLAUSES[:2])+records(CLAUSES[2:]), 'cohort_34')['status'], 'conflicting')

    def test_mismatched_metadata_does_not_extract(self):
        row = records()[0]
        row = replace(row, metadata={**row.metadata, 'document_hash':'f'*64})
        self.assertNotEqual(extract_calendar_basis([row], 'cohort_34')['status'], 'extracted')
