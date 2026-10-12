import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import patch

from chatbot.evaluation.evaluate_policy_answers import cases_for_review, LocalRetriever, run


class PolicyAnswerEvaluationTests(unittest.TestCase):
    def test_six_cases_keep_ground_truth_and_cohort(self):
        path = Path(__file__).parents[1]/'evaluation/policy_rag_cases_20.json'
        original = json.loads(path.read_text(encoding='utf-8'))
        selected = cases_for_review(original)
        self.assertEqual(len(selected), 6)
        self.assertEqual(sum(c['question_origin'] == 'existing' for c in selected), 2)
        by_id = {c['id']: c for c in original}
        for case in selected:
            self.assertEqual(case['evidence'], by_id[case['id']]['evidence'])
            self.assertEqual(case['cohort'], by_id[case['id']]['cohort'])

    def test_empty_notice_does_not_touch_embeddings(self):
        self.assertEqual(LocalRetriever('notice', 'cohort_34', [], None, 'vector', 8).invoke('공지'), [])

    def test_unsupported_namespace_stops(self):
        with self.assertRaises(ValueError):
            LocalRetriever('project_reference', 'cohort_34', [], None, 'vector', 8).invoke('프로젝트')

    def test_prepare_does_not_construct_network_clients(self):
        path = Path(__file__).parents[1]/'evaluation/policy_rag_cases_20.json'
        original = json.loads(path.read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'manifest.json').write_text('{}', encoding='utf-8')
            args = SimpleNamespace(output=root/'prepared', baseline_run=root,
                                   cases=path, execute=False, model='unused')
            with patch('chatbot.evaluation.evaluate_policy_answers.load_inputs', return_value=(original, {}, {}, {}, {})), \
                 patch('chatbot.evaluation.evaluate_policy_answers.build_bot') as network:
                result = run(args)
                network.assert_not_called()
                self.assertEqual(sum(result['attempted_calls'].values()), 0)
                self.assertEqual(result['status'], 'prepared')
                with self.assertRaises(ValueError):
                    run(args)


if __name__ == '__main__':
    unittest.main()
