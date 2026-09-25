"""Connection routing checks without opening a PostgreSQL connection."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from job_matching_bot.ingestion.sqlite_store import SqliteJobStore


class ConnectionRoutingTests(unittest.TestCase):
    def test_managed_jobs_schema_uses_db_host_configuration(self):
        with tempfile.TemporaryDirectory() as folder, patch(
            "job_matching_bot.ingestion.sqlite_store.connect_postgres",
            side_effect=RuntimeError("connection intercepted"),
        ) as connect:
            with self.assertRaisesRegex(RuntimeError, "connection intercepted"):
                SqliteJobStore(Path(folder) / "job_store.sqlite")
        self.assertTrue(connect.call_args.kwargs["use_db_host"])

    def test_isolated_schema_keeps_local_connection(self):
        with tempfile.TemporaryDirectory() as folder, patch(
            "job_matching_bot.ingestion.sqlite_store.connect_postgres",
            side_effect=RuntimeError("connection intercepted"),
        ) as connect:
            with self.assertRaisesRegex(RuntimeError, "connection intercepted"):
                SqliteJobStore(Path(folder) / "test_store.sqlite")
        self.assertFalse(connect.call_args.kwargs["use_db_host"])
