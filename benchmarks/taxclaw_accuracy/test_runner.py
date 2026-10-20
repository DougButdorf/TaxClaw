"""Regression: instrument the shipped backend without bypassing its schema path."""
import argparse
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import pymupdf

from .runner import run


class Response(dict):
    def model_dump(self, **kwargs):
        return dict(self)


class RunnerTests(unittest.TestCase):
    def test_current_backend_schema_and_host_are_used(self):
        from src import ollama_local
        calls = []
        hosts = []

        class FakeClient:
            def __init__(self, *, host, timeout=None):
                hosts.append(host)

            def list(self):
                return Response(models=[{"model": "test-model", "digest": "a" * 64}])

            def show(self, model):
                return {"capabilities": ["vision", "completion"]}

            def ps(self):
                return Response(models=[])

            def chat(self, **kwargs):
                calls.append(kwargs)
                return Response(model="test-model", done_reason="stop",
                                message={"content": '{"payer_name":"Example"}'})

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            fixtures = root / "fixtures"
            fixtures.mkdir()
            with pymupdf.open() as doc:
                page = doc.new_page()
                page.insert_text((30, 40), "Form 1099-R SYNTHETIC NOT FOR FILING")
                doc.save(fixtures / "example.pdf")
            (fixtures / "manifest.json").write_text(json.dumps([{
                "fixture_id": "test_fixture", "doc_type": "1099-R", "variant": "clean",
                "pdf_path": "example.pdf", "page_count": 1,
                "expected": {"payer_name": "Example"}, "field_types": {"payer_name": "text"}}]))
            args = argparse.Namespace(fixtures=fixtures, output=root / "out", types=["1099-R"],
                                      variants=["clean"], models=["test-model"], transport="app",
                                      host="http://example.invalid:11434", timeout=3,
                                      claude_wrapper=None)
            original_factory = ollama_local.client
            ollama_local._check_model_cached.cache_clear()
            with patch("ollama.Client", FakeClient), contextlib.redirect_stdout(io.StringIO()):
                run(args)
            self.assertIs(ollama_local.client, original_factory)
            self.assertTrue(hosts)
            self.assertTrue(all(h == args.host for h in hosts))
            self.assertEqual(len(calls), 1)
            schema = calls[0]["format"]
            self.assertIn("distribution_codes", schema["properties"])
            self.assertEqual(len(schema["properties"]), 30)
            self.assertEqual(calls[0]["options"], {"temperature": 0})
            result = json.loads((root / "out" / "results.jsonl").read_text())
            self.assertEqual(result["status"], "ok")
            self.assertTrue(result["score"]["exact_document"])
            self.assertEqual(result["pages"][0]["format"], schema)
            ollama_local._check_model_cached.cache_clear()


if __name__ == "__main__":
    unittest.main()
