"""Real DOCX parser + upload endpoint; external writes stay mocked."""
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from chatbot.tests.test_regulation_ingestion import regulation_bytes
from lms.cohort_documents import upload_document


class RegulationUploadTests(SimpleTestCase):
    def test_uploaded_file_is_the_runtime_calculation_source(self):
        from io import BytesIO
        from datetime import date, timedelta
        from chatbot.active_policy_rules import _read_snapshot, load_active_snapshot, allowance_rules
        from chatbot.unit_period import calculate_unit_period_context
        from unittest.mock import MagicMock
        for term, percent, count, expected in [(3, 80, 3, True), (4, 90, 2, False)]:
            cohort = f'cohort-test00{term}'
            data = regulation_bytes([
                ('제1조(출결)', [f'단위기간 내 지각·조퇴·외출 누적 {count}회는 결석 1일로 환산한다.']),
                ('제2조(장려금)', [f'단위기간 출석률 {percent}% 이상이면 훈련장려금 지급 대상이다.']),
                ('제3조(수료)', [f'전체 훈련기간의 100일 이상({percent}% 이상) 이수하면 수료 기준을 충족한다.']),
            ], title=f'엔코아 AI 캠프 {term}기 테스트 규정')
            with patch('lms.cohort_documents.put_object') as put, \
                 patch('lms.cohort_documents.connection') as conn, \
                 patch('lms.cohort_documents.transaction.atomic'), \
                 patch('lms.cohort_documents.index_document'):
                conn.cursor.return_value.__enter__.return_value.fetchone.side_effect = [(term, cohort), (term, cohort), None]
                file = Mock(name='file'); file.name = 'test.docx'; file.read.return_value = data
                result = upload_document(Mock(auth={'id': 1, 'role': 'admin', 'is_active': True}), cohort, 'policy', file)
            self.assertEqual(result['calculationCriteria']['allowance']['value'], str(percent))
            self.assertEqual(result['calculationIssues'], {})
            key, stored = put.call_args.args[:2]
            cur = MagicMock()
            cur.execute.return_value.fetchone.side_effect = [None, {'storage_key': key, 'source_name': 'test.docx'}]
            _read_snapshot.cache_clear()
            with patch('boto3.client') as s3:
                s3.return_value.get_object.return_value = {'Body': BytesIO(stored)}
                snapshot = load_active_snapshot(cur, cohort)
            start = date(2026, 1, 1)
            days = [start + timedelta(days=i) for i in range(10)]
            context = calculate_unit_period_context(start, date(2026, 1, 31), today=days[-1],
                scheduled_dates=days, attendance_records=dict(zip(days, ['late']*4+['present']*6)),
                require_policy=True, rules=allowance_rules(snapshot))
            self.assertEqual(context['periods'][0]['requirement_met'], expected)
        _read_snapshot.cache_clear()

    def test_formal_docx_reaches_indexer_before_database_publication(self):
        with patch('lms.cohort_documents.put_object') as put, \
             patch('lms.cohort_documents.connection') as conn, \
             patch('lms.cohort_documents.transaction.atomic'), \
             patch('lms.cohort_documents.index_document') as index:
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.side_effect = [(34, 'cohort_34'), (34, 'cohort_34'), None]
            events = []
            cur.execute.side_effect = lambda sql, *args: events.append('activate' if 'INSERT INTO policy_documents' in sql else 'read')
            put.side_effect = lambda *args: events.append('store')
            index.side_effect = lambda *args: events.append('index')
            file = Mock(); file.name = 'rules.docx'; file.read.return_value = regulation_bytes()
            result = upload_document(Mock(auth={'id': 1, 'role': 'admin', 'is_active': True}),
                                     'cohort_34', 'policy', file)
        self.assertEqual(result['chunks'], 3)
        records, key = index.call_args.args
        self.assertEqual(records[1].metadata['reference_vector_ids'], [records[2].vector_id])
        self.assertEqual({r.metadata['approval_status'] for r in records}, {'draft'})
        self.assertTrue(key.startswith('cohorts/cohort_34/policy/rag/'))
        self.assertLess(events.index('index'), events.index('activate'))

    def test_invalid_regulation_is_rejected_before_storage_or_indexing(self):
        with patch('lms.cohort_documents.put_object') as put, \
             patch('lms.cohort_documents.connection') as conn, \
             patch('lms.cohort_documents.index_document') as index, \
             self.assertLogs('lms.cohort_documents', level='ERROR'):
            cur = conn.cursor.return_value.__enter__.return_value
            cur.fetchone.return_value = (34, 'cohort_34')
            file = Mock(); file.name = 'rules.docx'
            file.read.return_value = regulation_bytes([('제1조(가)', ['원문']), ('제1조(나)', ['중복'])])
            result = upload_document(Mock(auth={'id': 1, 'role': 'admin', 'is_active': True}),
                                     'cohort_34', 'policy', file)
        self.assertEqual(result.status_code, 400)
        put.assert_not_called()
        index.assert_not_called()
