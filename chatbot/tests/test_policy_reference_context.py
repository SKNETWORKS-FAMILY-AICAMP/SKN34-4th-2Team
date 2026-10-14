"""Exercise scoped reference retrieval without embedding or network calls."""
import copy
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from langchain_core.documents import Document

from chatbot.cohort_document_rag import document_namespace, expand_policy_context
from chatbot.tests.test_regulation_ingestion import regulation_bytes, upload_records


class PolicyReferenceContextTests(unittest.TestCase):
    def setUp(self):
        self.records = upload_records(regulation_bytes([
            ("제1조(기준)", ["제2조의 예외를 함께 적용한다."]),
            ("제2조(예외)", ["제1조에 따른 신청 후 증빙을 제출한다."]),
        ]))
        self.key = self.records[0].metadata['storage_key']
        self.namespace = document_namespace(self.key)
        self.seed = self.as_document(self.records[0])
        self.index = Mock()
        self.index.fetch.return_value = SimpleNamespace(vectors={
            r.vector_id: SimpleNamespace(metadata={**r.metadata, 'page_content': r.page_content})
            for r in self.records
        })

    @staticmethod
    def as_document(record):
        return Document(id=record.vector_id, page_content=record.page_content,
                        metadata=copy.deepcopy(record.metadata))

    def expand(self, docs=None, **kwargs):
        return expand_policy_context(self.index, self.namespace, 'cohort_34',
                                     docs if docs is not None else [self.seed], **kwargs)

    def test_reference_fetch_is_single_hop_and_cycle_does_not_duplicate(self):
        result = self.expand()
        self.assertEqual([d.id for d in result], ['doc-0', 'doc-1'])
        self.index.fetch.assert_called_once_with(ids=['doc-1'], namespace=self.namespace)
        self.assertIn('증빙을 제출한다', result[1].page_content)

    def test_already_retrieved_reference_is_not_fetched_again(self):
        result = self.expand([self.seed, self.as_document(self.records[1])])
        self.assertEqual(len(result), 2)
        self.index.fetch.assert_not_called()

    def test_foreign_cohort_seed_is_rejected(self):
        self.seed.metadata['cohort'] = 'cohort_40'
        self.assertEqual(self.expand(), [])
        self.index.fetch.assert_not_called()

    def test_same_cohort_other_upload_seed_is_rejected(self):
        self.seed.metadata['storage_key'] = self.key.replace('a' * 32, 'b' * 32)
        self.assertEqual(self.expand(), [])
        self.index.fetch.assert_not_called()

    def test_fetched_wrong_cohort_version_hash_or_kind_is_rejected(self):
        original = self.index.fetch.return_value.vectors['doc-1'].metadata.copy()
        for field, value in [('cohort', 'cohort_40'), ('storage_key', self.key + '.old'),
                             ('document_hash', 'b' * 64), ('kind', 'curriculum')]:
            with self.subTest(field=field):
                self.index.fetch.return_value.vectors['doc-1'].metadata = {**original, field: value}
                self.assertEqual([d.id for d in self.expand()], ['doc-0'])

    def test_reference_count_limit_is_enforced(self):
        self.seed.metadata['reference_vector_ids'] = [f'doc-{i}' for i in range(1, 30)]
        self.expand(max_extra=3)
        self.assertEqual(len(self.index.fetch.call_args.kwargs['ids']), 3)

    def test_reference_char_budget_keeps_whole_article_or_marks_omission(self):
        result = self.expand(max_chars=1)
        self.assertEqual([d.id for d in result], ['doc-0'])
        self.assertTrue(result[0].metadata['context_truncated'])

    def test_missing_referenced_vector_marks_incomplete_context(self):
        self.index.fetch.return_value.vectors = {}
        result = self.expand()
        self.assertTrue(result[0].metadata['context_truncated'])

    def test_prompt_does_not_present_draft_or_incomplete_context_as_final(self):
        from chatbot.student_chatbot import ANSWER_PROMPT
        self.assertIn('approval_status', ANSWER_PROMPT)
        self.assertIn('context_truncated', ANSWER_PROMPT)

    def test_legacy_namespace_does_not_fetch_graph_edges(self):
        result = expand_policy_context(self.index, 'policy', 'cohort_34', [self.seed])
        self.assertEqual(len(result), 1)
        self.index.fetch.assert_not_called()

    def test_live_retriever_path_invokes_reference_expansion(self):
        from chatbot.student_chatbot import LmsStudentChatbot
        bot = object.__new__(LmsStudentChatbot)
        bot.index = self.index; bot.embeddings = Mock(); bot.k = 4
        bot.embeddings.embed_query.return_value = [0.1, 0.2]
        self.index.query.return_value = SimpleNamespace(matches=[SimpleNamespace(
            id=self.records[0].vector_id,
            metadata={**self.records[0].metadata, 'page_content': self.records[0].page_content},
        )])
        with patch('chatbot.cohort_document_rag.active_policy_namespace', return_value=self.namespace):
            result = bot._retriever('policy', 'cohort_34').invoke('예외 조건은?')
        self.assertEqual([d.id for d in result], ['doc-0', 'doc-1'])
        bot.embeddings.embed_query.assert_called_once()
        self.index.query.assert_called_once()
        self.index.fetch.assert_called_once()
        self.assertEqual(self.index.query.call_args.kwargs['filter'], {'cohort': {'$eq': 'cohort_34'}})


if __name__ == '__main__':
    unittest.main()
