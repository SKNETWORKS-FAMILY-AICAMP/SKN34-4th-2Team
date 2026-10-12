"""Offline evaluator contracts: no production publication and honest metrics."""
from copy import deepcopy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from chatbot.evaluation.evaluate_policy_rag import (
    prepare_corpora, validate_cases, score_evidence, retrieve, parser, run, paired_comparison,
)
from chatbot.tests.test_regulation_ingestion import regulation_bytes


class PolicyRagEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'rules.docx'
        self.path.write_bytes(regulation_bytes([
            ('제1조(기준)', ['기준 조건은 제2조에 따른다.']),
            ('제2조(예외)', ['증빙 서류를 제출해야 한다.']),
        ]))
        self.specs = [f'cohort_34={self.path}', f'cohort_40={self.path}']
        self.corpora = prepare_corpora(self.specs)
        self.case = {'id': 'fixture', 'cohort': 'cohort_34', 'question': '기준 조건',
            'required_articles': ['1', '2'], 'evidence': [
                {'article': '1', 'quote': '제2조에 따른다.'},
                {'article': '2', 'quote': '증빙 서류를 제출해야 한다.'}],
            'expected_behavior': 'answer', 'answer_checks': ['증빙 조건'], 'category': 'reference'}

    def test_same_sources_and_reproducible_corpora(self):
        self.assertEqual(self.corpora, prepare_corpora(self.specs))
        self.assertEqual(self.corpora['cohort_34']['B'], self.corpora['cohort_34']['C'])
        for variant in ('A', 'B', 'C'):
            self.assertEqual({r['metadata']['cohort'] for r in self.corpora['cohort_34'][variant]}, {'cohort_34'})

    def test_quote_validation_detects_drift_before_api_calls(self):
        validate_cases([self.case], self.corpora)
        changed = deepcopy(self.case)
        changed['evidence'][0]['quote'] = '원문에 없는 규정'
        with self.assertRaises(ValueError):
            validate_cases([changed], self.corpora)

    def test_duplicate_case_and_missing_cohort_fail_closed(self):
        with self.assertRaises(ValueError):
            validate_cases([self.case, self.case], self.corpora)
        changed = {**self.case, 'cohort': 'cohort_99'}
        with self.assertRaises(ValueError):
            validate_cases([changed], self.corpora)

    def test_article_hit_without_needed_sentence_is_not_evidence_success(self):
        rows = deepcopy(self.corpora['cohort_34']['B'])
        rows[1]['page_content'] = '제2조 이름만 검색됐다.'
        metrics = score_evidence(self.case, rows)
        self.assertEqual(metrics['article_recall'], 1)
        self.assertEqual(metrics['evidence_recall'], .5)
        self.assertFalse(metrics['all_evidence'])

    def test_wrong_cohort_quote_cannot_count_as_success(self):
        metrics = score_evidence(self.case, self.corpora['cohort_40']['B'])
        self.assertEqual(metrics['cross_cohort_count'], 2)
        self.assertEqual(metrics['article_recall'], 0)
        self.assertEqual(metrics['evidence_recall'], 0)

    def test_abstention_is_not_scored_as_perfect_retrieval(self):
        case = {**self.case, 'expected_behavior': 'abstain', 'required_articles': [], 'evidence': []}
        metrics = score_evidence(case, [])
        self.assertIsNone(metrics['article_recall'])
        self.assertIsNone(metrics['all_evidence'])

    def test_improved_mean_does_not_hide_single_question_regression(self):
        rows = [{'case_id': key, 'variant': variant, 'metrics': {'article_recall': score, 'evidence_recall': score}}
                for key, variant, score in [('one', 'A', 1), ('one', 'B', .5), ('two', 'A', 0), ('two', 'B', 1)]]
        result = paired_comparison(rows, 'A', 'B')
        self.assertEqual(result['evidence_recall']['regressed_case_ids'], ['one'])
        self.assertEqual(result['evidence_recall']['improved_case_ids'], ['two'])

    def test_c_runs_real_reference_expansion_without_changing_b_seed(self):
        vectors = {self.case['question']: [1., 0.]}
        for variants in self.corpora.values():
            for row in variants['B']:
                vectors[row['page_content']] = [1., 0.] if row['metadata']['article_number'] == '1' else [0., 1.]
        baseline, _ = retrieve(self.case, 'B', self.corpora, 1, vectors)
        expanded, _ = retrieve(self.case, 'C', self.corpora, 1, vectors)
        self.assertEqual([r['metadata']['article_number'] for r in baseline], ['1'])
        self.assertEqual([r['metadata']['article_number'] for r in expanded], ['1', '2'])
        self.assertEqual(score_evidence(self.case, expanded)['evidence_recall'], 1)

    def test_prepare_and_lexical_never_call_embedding_or_publish(self):
        cases = self.root / 'cases.json'
        cases.write_text(json.dumps([self.case]), encoding='utf-8')
        with patch('chatbot.evaluation.evaluate_policy_rag.embed_texts', side_effect=AssertionError('network')), \
             patch('chatbot.cohort_document_rag.index_document', side_effect=AssertionError('publication')):
            for mode in ('prepare', 'lexical'):
                output = self.root / mode
                args = parser().parse_args(['--document', self.specs[0], '--cases', str(cases),
                                            '--output', str(output), '--mode', mode])
                run(args)
                self.assertTrue((output / 'manifest.json').exists())
                with self.assertRaises(ValueError):
                    run(args)
        reviews = json.loads((self.root / 'lexical/blind-review.json').read_text(encoding='utf-8'))
        self.assertEqual(len(reviews), 3)
        self.assertTrue(all('variant' not in row for row in reviews))
        self.assertTrue(all(row['answer'] is None for row in reviews))


if __name__ == '__main__':
    unittest.main()
