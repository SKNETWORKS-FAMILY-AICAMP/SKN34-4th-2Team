import unittest
from unittest.mock import Mock, patch
from io import BytesIO
from chatbot.cohort_document_rag import (document_records, document_namespace, active_policy_namespace,
    curriculum_context, valid_cohort_code, index_document)


class CohortRagTests(unittest.TestCase):
    def test_new_cohort_identity_and_versions_are_separate(self):
        self.assertTrue(valid_cohort_code('cohort-abc1234'))
        self.assertTrue(valid_cohort_code('cohort_34'))
        self.assertFalse(valid_cohort_code('../cohort_34'))
        self.assertNotEqual(document_namespace('cohorts/cohort_34/policy/a'), document_namespace('cohorts/cohort_40/policy/a'))
        self.assertNotEqual(document_namespace('cohorts/cohort_40/policy/a'), document_namespace('cohorts/cohort_40/policy/b'))

    def test_active_policy_uses_exact_version_and_legacy_fallback(self):
        key = 'cohorts/cohort-abc1234/policy/rag/' + 'a'*32 + '.docx'
        with patch('chatbot.cohort_document_rag.connect') as connect:
            cursor = connect.return_value.__enter__.return_value
            cursor.execute.return_value.fetchone.side_effect = [None, (key,)]
            self.assertEqual(active_policy_namespace('cohort-abc1234'), document_namespace(key))
            self.assertEqual(cursor.execute.call_args.args[1], ('cohort-abc1234',))
            cursor.execute.return_value.fetchone.side_effect = [None, None]
            self.assertEqual(active_policy_namespace('cohort_34'), 'policy')
            cursor.execute.return_value.fetchone.side_effect = [None, ('cohorts/cohort_40/policy/invalid.docx',)]
            with self.assertRaises(ValueError): active_policy_namespace('cohort_34')

    def test_deleting_cohort_never_falls_back_to_global_policy(self):
        with patch('chatbot.cohort_document_rag.connect') as connect:
            cursor = connect.return_value.__enter__.return_value
            cursor.execute.return_value.fetchone.return_value = (1,)
            with self.assertRaises(ValueError): active_policy_namespace('cohort_40')
            self.assertEqual(cursor.execute.call_count, 1)

    def test_pdf_tail_is_chunked_and_image_only_page_is_rejected(self):
        pages = [Mock(), Mock()]
        pages[0].extract_text.return_value = 'first ' * 2000
        pages[1].extract_text.return_value = 'last page unique curriculum'
        with patch('pypdf.PdfReader') as reader:
            reader.return_value.pages = pages
            records = document_records(b'%PDF', 'c.pdf', 'cohort_40', 'curriculum', 'cohorts/cohort_40/curriculum/a.pdf')
            self.assertIn('last page unique curriculum', records[-1].page_content)
            self.assertEqual(records[-1].metadata['page'], 2)
            pages[1].extract_text.return_value = ''
            with self.assertRaises(ValueError):
                document_records(b'%PDF', 'c.pdf', 'cohort_40', 'curriculum', 'cohorts/cohort_40/curriculum/a.pdf')

    def test_curriculum_uses_db_pointer_without_prefix_listing(self):
        cur = Mock()
        cur.execute.return_value.fetchone.side_effect = [None, {'storage_key':'cohorts/cohort_40/curriculum/current.pdf', 'original_filename':'current.pdf'}]
        page = Mock(); page.extract_text.return_value = 'late curriculum data science'
        with patch('boto3.client') as client, patch('pypdf.PdfReader') as reader:
            client.return_value.get_object.return_value = {'Body': BytesIO(b'%PDF')}
            reader.return_value.pages = [page]
            result = curriculum_context(cur, 40, 'cohort_40', 'data science')
            self.assertEqual(result['items'][0]['path'], 'cohorts/cohort_40/curriculum/current.pdf')
            client.return_value.list_objects_v2.assert_not_called()
            self.assertEqual(client.return_value.get_object.call_args.kwargs['Key'], 'cohorts/cohort_40/curriculum/current.pdf')

    def test_policy_retriever_keeps_authenticated_cohort_filter(self):
        from chatbot.student_chatbot import LmsStudentChatbot
        bot = LmsStudentChatbot.__new__(LmsStudentChatbot)
        bot.index = Mock(); bot.embeddings = Mock(); bot.k = 4
        with patch('chatbot.cohort_document_rag.active_policy_namespace', return_value='version-40'):
            retriever = bot._retriever('policy', 'cohort-abc1234')
            self.assertEqual(retriever.vectorstore._namespace, 'version-40')
            self.assertEqual(retriever.vectorstore.required_filter, {'cohort': {'$eq':'cohort-abc1234'}})

    def test_index_must_be_query_visible_before_activation(self):
        record = Mock(vector_id='doc-0', metadata={'cohort':'cohort_40'})
        with patch('chatbot.cohort_document_rag.upload_records', return_value={'upserted':1}), \
             patch('pinecone.Pinecone') as pc, patch('chatbot.cohort_document_rag.time.sleep'), \
             patch('chatbot.cohort_document_rag.time.monotonic', side_effect=[0,31]):
            pc.return_value.Index.return_value.fetch.return_value.vectors = {}
            with self.assertRaises(TimeoutError): index_document([record], 'key')

if __name__ == '__main__': unittest.main()
