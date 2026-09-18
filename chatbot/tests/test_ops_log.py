from __future__ import annotations

import json
import unittest

from chatbot.ops_log import (
    build_done_event,
    build_generation_log_payload,
    request_id_hash,
)


class OpsLogTests(unittest.TestCase):
    def test_done_event_has_ops_without_question(self) -> None:
        payload = build_generation_log_payload(
            cohort_id="cohort_34",
            created_by="uid-1",
            latency_ms=1200,
            status="success",
            snapshot={
                "promptVersion": "student_chatbot_v2",
                "model": "gpt-5.6-sol",
                "route": "lms",
                "namespaces": ["policy", "notice"],
                "student_scopes": ["student_private"],
                "question": "내 출석률 알려줘",
                "answer": "비밀",
            },
            thread_id="abc.thread-1",
        )
        event = build_done_event("log123", payload)
        dumped = json.dumps(event, ensure_ascii=False)
        self.assertEqual(event["type"], "done")
        self.assertEqual(event["ops"]["logId"], "log123")
        self.assertEqual(event["ops"]["promptVersion"], "student_chatbot_v2")
        self.assertEqual(event["ops"]["route"], "lms")
        self.assertNotIn("question", dumped)
        self.assertNotIn("answer", dumped)
        self.assertNotIn("내 출석률", dumped)

    def test_admin_payload_has_no_question_or_answer_keys(self) -> None:
        payload = build_generation_log_payload(
            cohort_id="cohort_34",
            created_by="uid-1",
            latency_ms=800,
            status="success",
            snapshot={
                "route": "lms",
                "namespaces": ["notice"],
                "question": "오늘 공지 뭐야",
                "answer": "공지입니다",
                "content": "본문",
            },
            thread_id="thread-1",
        )
        lowered = {key.lower() for key in payload}
        self.assertTrue({"question", "answer", "content"}.isdisjoint(lowered))
        self.assertEqual(payload["type"], "student_chatbot")
        self.assertEqual(payload["promptVersion"], "student_chatbot_v2")
        self.assertEqual(payload["namespaces"], "notice")
        self.assertEqual(payload["requestIdHash"], request_id_hash("thread-1"))
        self.assertIn("route", payload)
        self.assertIn("latencyMs", payload)


if __name__ == "__main__":
    unittest.main()
