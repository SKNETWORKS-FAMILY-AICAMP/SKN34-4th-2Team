"""Real DOCX parser + upload endpoint; external writes stay mocked."""
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from chatbot.tests.test_regulation_ingestion import regulation_bytes
from lms.cohort_documents import upload_document


class RegulationUploadTests(SimpleTestCase):
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
