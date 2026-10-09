"""Offline hybrid experiment checks; no external clients or real corpora."""
import json
from pathlib import Path
import tempfile
import unittest

from chatbot.evaluation.policy_hybrid import tokenize, bm25_rank, rrf_rank
from chatbot.evaluation.evaluate_policy_hybrid import load_inputs, rank_case, sha, digest


def row(key, text, cohort='cohort_34'):
    return {'id': key, 'page_content': text, 'metadata': {
        'cohort': cohort, 'article_number': key, 'storage_key': 'version-one',
        'document_hash': 'source-hash', 'kind': 'policy', 'structure': 'article'}}


class PolicyHybridTests(unittest.TestCase):
    def test_token_normalization_and_word_boundaries(self):
        tokens = tokenize('ＡＢＣ 출석률 기준')
        self.assertIn('abc', tokens)
        self.assertIn('출석', tokens)
        self.assertNotIn('률기', tokens)

    def test_numeric_thresholds_remain_distinct(self):
        self.assertEqual(tokenize('80% 100% 15,000 80'), ['80%', '100%', '15,000', '80'])
        ranked = bm25_rank('80%', [row('a', '80%'), row('b', '100%')])
        self.assertEqual([r['id'] for _, r in ranked], ['a'])

    def test_bm25_no_overlap_and_empty_input(self):
        self.assertEqual(bm25_rank('환급', [row('a', '출석')]), [])
        self.assertEqual(bm25_rank('', [row('a', '출석')]), [])
        self.assertEqual(bm25_rank('출석', []), [])

    def test_bm25_ties_and_repeated_query(self):
        rows = [row('b', '출석'), row('a', '출석')]
        self.assertEqual(bm25_rank('출석', rows), bm25_rank('출석 출석', rows))
        self.assertEqual([r['id'] for _, r in bm25_rank('출석', rows)], ['a', 'b'])

    def test_bm25_invalid_input(self):
        with self.assertRaises(ValueError):
            bm25_rank('출석', [row('a', '출석'), row('a', '환급')])
        for limit in (0, -1, True, 1.5):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                bm25_rank('출석', [], limit=limit)

    def test_rrf_combines_ranks_not_score_scale(self):
        a, b = row('a', '출석'), row('b', '환급')
        ranked = rrf_rank([[(1000, a), (1, b)], [(-0.5, b)]])
        self.assertEqual(ranked[0][1]['id'], 'b')
        self.assertAlmostEqual(ranked[0][0], 1/62 + 1/61)

    def test_rrf_duplicate_ids_and_invalid_scores(self):
        a, b = row('a', '출석'), row('b', '환급')
        ranked = rrf_rank([[(1, a), (1, a), (1, b)]])
        self.assertAlmostEqual(ranked[0][0], 1/61)
        self.assertAlmostEqual(ranked[1][0], 1/62)
        for score in (float('nan'), float('inf'), True):
            with self.subTest(score=score), self.assertRaises(ValueError):
                rrf_rank([[(score, a)]])

    def test_rrf_empty_lexical_preserves_vector_order(self):
        a, b = row('a', '출석'), row('b', '환급')
        self.assertEqual([r['id'] for _, r in rrf_rank([[(1, b), (0, a)], []])], ['b', 'a'])

    def test_rank_case_rejects_cross_cohort(self):
        with self.assertRaises(ValueError):
            rank_case({'cohort': 'cohort_34'}, [row('a', '출석', 'cohort_40')], {})

    def test_cache_and_source_guards(self):
        case = {'id': 'q1', 'cohort': 'cohort_34', 'question': '출석 기준',
                'required_articles': ['1'], 'evidence': [{'article': '1', 'quote': '출석'}],
                'expected_behavior': 'answer', 'answer_checks': [], 'category': 'attendance'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def write(name, value):
                (root/name).write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
            write('cases.json', [case])
            write('manifest.json', {'mode': 'embedding', 'completed': True,
                'cases_sha256': sha(root/'cases.json'), 'embedding_model': 'fixture',
                'embedding_dimensions': 2, 'sources': [{'cohort': 'cohort_34', 'sha256': 'source-hash'}]})
            write('corpus-cohort_34-B.json', [row('1', '출석')])
            cache = {digest('fixture\0'+'2\0'+text): [1, 0] for text in ('출석', '출석 기준')}
            write('embedding-cache.json', cache)
            self.assertEqual(len(load_inputs(root, root/'cases.json')[0]), 1)
            write('embedding-cache.json', {})
            with self.assertRaisesRegex(ValueError, 'cached embedding'):
                load_inputs(root, root/'cases.json')
            write('embedding-cache.json', cache)
            write('corpus-cohort_34-B.json', [row('1', '출석', 'cohort_40')])
            with self.assertRaisesRegex(ValueError, 'Mixed cohort'):
                load_inputs(root, root/'cases.json')
            write('cases.json', [])
            with self.assertRaisesRegex(ValueError, 'exact case file'):
                load_inputs(root, root/'cases.json')


if __name__ == '__main__':
    unittest.main()
