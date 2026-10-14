"""Task queries must reach their own document stores."""

import unittest

from langchain_core.documents import Document

from chatbot.student_chatbot import LmsStudentChatbot


class TaskRetrievalTest(unittest.TestCase):
    def test_each_namespace_uses_its_task_query(self):
        bot = object.__new__(LmsStudentChatbot)
        bot.k = 4
        calls = []

        class Retriever:
            def __init__(self, namespace):
                self.namespace = namespace

            def invoke(self, query):
                calls.append((self.namespace, query))
                return [Document(page_content=query, metadata={"doc_id": self.namespace})]

        bot._retriever = lambda namespace, *_args, **_kwargs: Retriever(namespace)
        state = {
            "query": "제출 정책과 28기 프로젝트",
            "cohort": "34",
            "namespaces": ["policy", "project_reference"],
            "tasks": [
                {"query": "최종 프로젝트 제출 정책", "namespaces": ["policy"]},
                {"query": "28기 최종 프로젝트", "namespaces": ["project_reference"]},
            ],
            "documents": [],
        }
        result = bot._retrieve_namespaces(state, ["policy", "project_reference"])
        self.assertCountEqual(calls, [
            ("policy", "최종 프로젝트 제출 정책"),
            ("project_reference", "28기 최종 프로젝트"),
        ])
        self.assertEqual(len(result["documents"]), 2)

    def test_student_scopes_keep_separate_queries(self):
        bot = object.__new__(LmsStudentChatbot)
        calls = []

        def loader(_uid, _cohort, scopes, query):
            calls.append((scopes, query))
            return {"requested_scopes": scopes[:], "data": {scope: {"items": []} for scope in scopes}, "errors": {}}

        bot.student_context_loader = loader
        state = {
            "student_uid": "student", "cohort": "34", "query": "combined",
            "student_scopes": ["student_private", "assignment_files"],
            "tasks": [
                {"query": "내 출석률", "student_scopes": ["student_private"]},
                {"query": "내 과제 파일", "student_scopes": ["assignment_files"]},
            ],
        }
        result = bot._student_tools(state)
        self.assertEqual(calls, [
            (["student_private"], "내 출석률"),
            (["assignment_files"], "내 과제 파일"),
        ])
        self.assertCountEqual(result["student_context"]["data"], ["student_private", "assignment_files"])


if __name__ == "__main__":
    unittest.main()
