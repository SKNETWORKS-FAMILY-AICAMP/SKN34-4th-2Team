import sys
from pathlib import Path
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from changed_scope import requires_verification


class ChangedScopeTests(unittest.TestCase):
    def setUp(self):
        self.push = {"before": "a" * 40, "after": "b" * 40}

    def test_documentation_only(self):
        paths = "README.md\0docs/report.md\0docs/report.pdf\0assets/readme_image/ui/screen.png\0lms_mobile/README.md\0"
        self.assertFalse(requires_verification("push", self.push, Mock(return_value=paths)))

    def test_runtime_and_configuration_always_verify(self):
        for path in ("lms_react/src/app.tsx", "lms_api/lms/commands.py", ".github/workflows/deploy.yml",
                     "deploy/changed_scope.py", "requirements.txt", "docker-compose.yml", ".env.example",
                     "chatbot/prompts/instructions.md", "docs/generate.py", "assets/readme_image/script.js"):
            with self.subTest(path=path):
                self.assertTrue(requires_verification("push", self.push, Mock(return_value="README.md\0" + path + "\0")))

    def test_rename_from_code_to_docs_is_not_skipped(self):
        self.assertTrue(requires_verification("push", self.push, Mock(return_value="src/old.py\0docs/old.md\0")))

    def test_push_compares_whole_push(self):
        diff = Mock(return_value="README.md\0")
        requires_verification("push", self.push, diff)
        diff.assert_called_once_with("a" * 40 + ".." + "b" * 40)

    def test_pr_compares_whole_branch(self):
        diff = Mock(return_value="README.md\0src/app.tsx\0")
        event = {"pull_request": {"base": {"sha": "a" * 40}, "head": {"sha": "b" * 40}}}
        self.assertTrue(requires_verification("pull_request", event, diff))
        diff.assert_called_once_with("a" * 40 + "..." + "b" * 40)

    def test_manual_and_initial_push_always_verify(self):
        diff = Mock()
        self.assertTrue(requires_verification("workflow_dispatch", {}, diff))
        self.assertTrue(requires_verification("push", {**self.push, "before": "0" * 40}, diff))
        diff.assert_not_called()

    def test_diff_failure_does_not_report_documentation_only(self):
        with self.assertRaises(RuntimeError):
            requires_verification("push", self.push, Mock(side_effect=RuntimeError("missing history")))

