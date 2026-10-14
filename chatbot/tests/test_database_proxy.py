from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from chatbot.database import connect
from chatbot.proxy_auth import valid_proxy_token


class DatabaseConnectionTests(unittest.TestCase):
    @patch("chatbot.database.psycopg.connect")
    def test_rds_settings_override_local_database_url(self, pg_connect):
        env = {
            "DB_HOST": "rds.example.invalid", "DB_PORT": "5432",
            "DB_NAME": "lms_validation", "DB_USER": "project_admin",
            "DB_PASSWORD": "secret", "DB_SSLMODE": "require",
            "DATABASE_URL": "postgresql://postgres@127.0.0.1:5432/lms",
        }
        with patch.dict(os.environ, env, clear=True):
            connect()
        self.assertEqual(pg_connect.call_args.kwargs["host"], env["DB_HOST"])
        self.assertEqual(pg_connect.call_args.kwargs["dbname"], env["DB_NAME"])
        self.assertEqual(pg_connect.call_args.kwargs["sslmode"], "require")

    @patch("chatbot.database.psycopg.connect")
    def test_local_url_remains_available_without_db_host(self, pg_connect):
        url = "postgresql://postgres@db:5432/lms"
        with patch.dict(os.environ, {"DATABASE_URL": url}, clear=True):
            connect()
        pg_connect.assert_called_once_with(url)

    def test_partial_rds_settings_fail_closed(self):
        with patch.dict(os.environ, {"DB_HOST": "rds.example.invalid"}, clear=True):
            with self.assertRaises(RuntimeError):
                connect()

    @patch("chatbot.database.psycopg.connect")
    def test_isolated_job_schema_ignores_rds_host(self, pg_connect):
        url = "postgresql://postgres@127.0.0.1:5432/test_jobs"
        with patch.dict(os.environ, {"DB_HOST": "rds.example.invalid", "DATABASE_URL": url}, clear=True):
            connect(use_db_host=False)
        pg_connect.assert_called_once_with(url)

    @patch("chatbot.database.psycopg.connect")
    def test_jobs_url_fallback_remains_available(self, pg_connect):
        url = "postgresql://postgres@127.0.0.1:5432/test_jobs"
        with patch.dict(os.environ, {}, clear=True):
            connect(fallback_url=url)
        pg_connect.assert_called_once_with(url)


class ProxyAuthenticationTests(unittest.TestCase):
    def test_missing_server_secret_rejects_all_requests(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(valid_proxy_token("anything"))

    def test_only_matching_secret_is_accepted(self):
        with patch.dict(os.environ, {"LMS_AI_SHARED_TOKEN": "private-test-token"}, clear=True):
            self.assertFalse(valid_proxy_token(None))
            self.assertFalse(valid_proxy_token("wrong"))
            self.assertTrue(valid_proxy_token("private-test-token"))
