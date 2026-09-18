""".env 로더 검증.

실제 키 값은 절대 확인하지 않는다. 파싱 규칙과 "셸 환경변수가 파일보다
우선한다"는 원칙만 본다.
"""

import os
import tempfile
import unittest
from pathlib import Path

from job_matching_bot.env import DEFAULT_ENV_PATH, load_env, parse_env


class ParseTest(unittest.TestCase):
    def test_basic_pairs(self):
        self.assertEqual({"A": "1", "B": "2"}, parse_env("A=1\nB=2"))

    def test_comments_and_blank_lines_are_skipped(self):
        self.assertEqual({"A": "1"}, parse_env("# 주석\n\nA=1\n  \n"))

    def test_export_prefix_is_stripped(self):
        self.assertEqual({"A": "1"}, parse_env("export A=1"))

    def test_surrounding_quotes_are_stripped(self):
        self.assertEqual({"A": "1", "B": "2"}, parse_env('A="1"\nB=\'2\''))

    def test_value_may_contain_equals(self):
        # 키에 =가 들어간 토큰(base64 패딩 등)이 잘리면 안 된다.
        self.assertEqual({"K": "abc=def=="}, parse_env("K=abc=def=="))

    def test_line_without_equals_is_ignored(self):
        self.assertEqual({}, parse_env("그냥 텍스트"))

    def test_empty_value_is_kept(self):
        self.assertEqual({"A": ""}, parse_env("A="))


class LoadTest(unittest.TestCase):
    def setUp(self):
        self.key = "JOB_MATCHING_BOT_TEST_KEY"
        os.environ.pop(self.key, None)

    def tearDown(self):
        os.environ.pop(self.key, None)

    def _write(self, temp_dir, text):
        path = Path(temp_dir) / ".env"
        path.write_text(text, encoding="utf-8")
        return path

    def test_loads_into_environ(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write(temp_dir, f"{self.key}=from_file")
            applied = load_env(path)
            self.assertIn(self.key, applied)
            self.assertEqual("from_file", os.environ[self.key])

    def test_shell_environment_wins_over_the_file(self):
        os.environ[self.key] = "from_shell"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write(temp_dir, f"{self.key}=from_file")
            applied = load_env(path)
            self.assertNotIn(self.key, applied)
            self.assertEqual("from_shell", os.environ[self.key])

    def test_override_flag_forces_the_file_value(self):
        os.environ[self.key] = "from_shell"
        with tempfile.TemporaryDirectory() as temp_dir:
            path = self._write(temp_dir, f"{self.key}=from_file")
            load_env(path, override=True)
            self.assertEqual("from_file", os.environ[self.key])

    def test_missing_file_is_not_an_error(self):
        self.assertEqual([], load_env(Path("존재하지_않는_경로.env")))


class LocationTest(unittest.TestCase):
    def test_default_path_points_at_repository_env(self):
        # Python 서비스의 단일 원본은 레포 루트 환경 파일이다.
        # 폴더 이름으로 확인하지 않는다. 다른 이름으로 체크아웃하면 멀쩡한데도 깨졌다.
        # 레포 루트는 앱(`pubspec.yaml`)과 이 패키지를 함께 담은 곳이다.
        root = DEFAULT_ENV_PATH.parent
        self.assertTrue((root / "pubspec.yaml").is_file(), root)
        self.assertTrue((root / "job_matching_bot" / "__init__.py").is_file(), root)
        self.assertEqual(".env", DEFAULT_ENV_PATH.name)

    def test_env_file_is_gitignored(self):
        gitignore = (DEFAULT_ENV_PATH.parent / ".gitignore").read_text(
            encoding="utf-8", errors="replace"
        )
        # 키 파일이 커밋되면 안 된다.
        self.assertIn(".env", gitignore)


if __name__ == "__main__":
    unittest.main()
