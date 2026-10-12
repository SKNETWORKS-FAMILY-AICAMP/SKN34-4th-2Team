from concurrent.futures import ThreadPoolExecutor
from unittest import TestCase
from unittest.mock import Mock, patch
from types import SimpleNamespace
from chatbot.student_chatbot import RequestQueryEmbeddings, LmsStudentChatbot


class RequestQueryBatchTests(TestCase):
    def test_real_retrieval_keeps_all_namespace_queries_and_cohort_filters(self):
        bot = object.__new__(LmsStudentChatbot)
        bot.k = 4
        bot.embeddings = Mock()
        bot.embeddings.embed_documents.return_value = [[1.0], [2.0]]
        bot.index = Mock()
        bot.index.query.return_value = SimpleNamespace(matches=[])
        state = {'cohort':'cohort_34', 'query':'combined', 'namespaces':['policy','notice'],
            'tasks':[{'query':q,'namespaces':['policy']} for q in ['first','second']]}
        with patch('chatbot.cohort_document_rag.active_policy_namespace',return_value='policy'):
            result = bot._retrieve_namespaces(state,['policy','notice'])
        bot.embeddings.embed_documents.assert_called_once_with(['first','second'])
        self.assertEqual(result['embedding_calls'],1)
        self.assertEqual(result['vector_calls'],4)
        self.assertCountEqual([(c.kwargs['namespace'],c.kwargs['vector']) for c in bot.index.query.call_args_list],
            [('policy',[1.0]),('policy',[2.0]),('notice',[1.0]),('notice',[2.0])])
        for call in bot.index.query.call_args_list:
            self.assertEqual(call.kwargs['filter'],{'cohort':{'$eq':'cohort_34'}})

    def test_parallel_searches_share_one_ordered_batch(self):
        embedder = Mock()
        embedder.embed_documents.return_value = [[1.0], [2.0]]
        batch = RequestQueryEmbeddings(embedder, ['policy', 'attendance', 'policy'])
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(batch.embed_query, ['attendance', 'policy', 'policy', 'attendance']))
        self.assertEqual(results, [[2.0], [1.0], [1.0], [2.0]])
        embedder.embed_documents.assert_called_once_with(['policy', 'attendance'])
        other_request = RequestQueryEmbeddings(embedder, ['policy', 'attendance'])
        other_request.embed_query('policy')
        self.assertEqual(embedder.embed_documents.call_count, 2)

    def test_failure_does_not_retry_per_namespace(self):
        embedder = Mock()
        embedder.embed_documents.side_effect = ValueError('failed')
        batch = RequestQueryEmbeddings(embedder, ['query'])
        for _ in range(3):
            with self.assertRaises(ValueError):
                batch.embed_query('query')
        embedder.embed_documents.assert_called_once()

    def test_repeated_private_scope_is_read_once_but_files_keep_queries(self):
        bot = object.__new__(LmsStudentChatbot)
        calls = []
        def loader(uid, cohort, scopes, query):
            calls.append((scopes, query))
            return {'requested_scopes': scopes[:], 'data': {s: {'items': []} for s in scopes}}
        bot.student_context_loader = loader
        result = bot._student_tools({'student_uid': 'a', 'cohort': 'cohort_34', 'query': 'combined',
            'student_scopes': ['student_private', 'assignment_files'], 'tasks': [
                {'query': q, 'student_scopes': ['student_private', 'assignment_files']} for q in ['first', 'second']]})
        self.assertEqual(calls, [(['student_private', 'assignment_files'], 'first'), (['assignment_files'], 'second')])
        self.assertCountEqual(result['student_context']['requested_scopes'], ['student_private', 'assignment_files'])
