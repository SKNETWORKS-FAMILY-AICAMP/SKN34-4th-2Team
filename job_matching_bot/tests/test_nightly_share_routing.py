"""Check the isolated share step without loading crawler-only dependencies."""

import ast
import unittest
from pathlib import Path
from typing import Any


def _share_step():
    path = Path(__file__).resolve().parents[1] / "crawling" / "nightly.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "share_store_file"
    )
    namespace = {"Path": Path, "Any": Any}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), "exec"), namespace)
    return namespace["share_store_file"]


class NightlyShareRoutingTests(unittest.TestCase):
    def test_postgres_is_shared_source_without_firebase_upload(self):
        result = _share_step()(Path("job_store.sqlite"))
        self.assertEqual(result, {"skipped": True, "reason": "shared_postgresql_jobs"})
