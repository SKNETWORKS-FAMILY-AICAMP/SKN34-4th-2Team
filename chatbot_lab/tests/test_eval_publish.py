from __future__ import annotations

import unittest

from chatbot_lab.eval_publish import build_eval_run_payload


class EvalPublishTests(unittest.TestCase):
    def test_publish_payload_has_no_question_field(self) -> None:
        payload = build_eval_run_payload(
            prompt_version="student_chatbot_v2",
            model="test-model",
            total_cases=10,
            passed=8,
            avg_latency_ms=420,
            failed_ids=["case_a", "case_b"],
        )
        self.assertNotIn("question", payload)
        self.assertNotIn("questions", payload)
        self.assertNotIn("answer", payload)
        self.assertEqual(payload["source"], "chatbot_lab")
        self.assertEqual(payload["totalCases"], 10)
        self.assertEqual(payload["passed"], 8)
        self.assertEqual(payload["failedIds"], ["case_a", "case_b"])
        self.assertAlmostEqual(payload["accuracy"], 0.8)


if __name__ == "__main__":
    unittest.main()
