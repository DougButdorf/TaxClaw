"""Backend, config and model-tier tests (mocked HTTP; no network, no model).

Run: PYTHONPATH=. venv/bin/python -P -m unittest discover -s tests -v
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest

import httpx

_TMP_HOME = tempfile.mkdtemp(prefix="taxclaw-test-home-")
os.environ["HOME"] = _TMP_HOME

from src.ai import ensure_backend_ready  # noqa: E402
from src.backends import AnthropicBackend, LocalBackend, OpenAICompatBackend, get_backend  # noqa: E402
from src.config import Config, is_cloud_backend, normalize_backend  # noqa: E402
from src.models import _bucket_for, load_catalog, pick_by_patterns, tier2_cloud  # noqa: E402

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
_KEY_ENVS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY",
    "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "TAXCLAW_TEST_KEY",
)


class CleanEnv(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.pop(k) for k in _KEY_ENVS if k in os.environ}

    def tearDown(self):
        for k in _KEY_ENVS:
            os.environ.pop(k, None)
        os.environ.update(self._saved)


class ConfigTest(CleanEnv):
    def test_cloud_alias(self):
        self.assertEqual(normalize_backend("cloud"), "anthropic")
        self.assertEqual(normalize_backend("bogus"), "local")
        self.assertTrue(is_cloud_backend("cloud"))
        self.assertFalse(is_cloud_backend("local"))
        self.assertIsInstance(get_backend(Config(model_backend="cloud")), AnthropicBackend)
        self.assertIsInstance(get_backend(Config()), LocalBackend)

    def test_privacy_required_for_every_cloud_backend(self):
        for b in ("anthropic", "openai_compat", "cloudflare_clairic", "cloud"):
            with self.assertRaises(RuntimeError) as cm:
                ensure_backend_ready(Config(model_backend=b, privacy_acknowledged=False))
            self.assertIn("privacy", str(cm.exception).lower())

    def test_privacy_required_when_backend_called_directly(self):
        # extract/classify call get_backend(cfg) directly, bypassing src.ai; the
        # backend itself must refuse before any key/model checks or network use.
        for b in ("anthropic", "openai_compat", "cloudflare_clairic", "cloud"):
            backend = get_backend(Config(model_backend=b, privacy_acknowledged=False))
            with self.assertRaises(RuntimeError) as cm:
                backend.ensure_ready()
            self.assertIn("privacy", str(cm.exception).lower(), b)

    def test_openai_compat_presets(self):
        c = Config(openai_compat_provider="gemini")
        self.assertEqual(c.openai_compat_resolved_base_url(), "https://generativelanguage.googleapis.com/v1beta/openai")
        self.assertEqual(c.openai_compat_key_envs(), ["GEMINI_API_KEY", "GOOGLE_API_KEY"])
        os.environ["GOOGLE_API_KEY"] = "x"
        self.assertEqual(c.openai_compat_api_key(), "x")


class OpenAICompatTest(CleanEnv):
    def _cfg(self, **kw):
        os.environ["TAXCLAW_TEST_KEY"] = "sk-test-not-real"
        base = dict(
            model_backend="openai_compat",
            privacy_acknowledged=True,
            openai_compat_provider="custom",
            openai_compat_base_url="https://example.invalid/v1",
            openai_compat_api_key_env="TAXCLAW_TEST_KEY",
            openai_compat_model="vision-model-1",
        )
        base.update(kw)
        return Config(**base)

    def test_json_schema_request_and_parse(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(json.loads(request.content))
            self.assertEqual(request.headers["authorization"], "Bearer sk-test-not-real")
            return httpx.Response(200, json={"choices": [{"message": {"content": '```json\n{"wages": "1.00"}\n```'}}]})

        be = OpenAICompatBackend(self._cfg(), transport=httpx.MockTransport(handler))
        schema = {"type": "object", "properties": {"wages": {"type": ["string", "null"]}}}
        out = be.chat_json(prompt="Return JSON", image_bytes=PNG_1PX, schema=schema)
        self.assertEqual(out, {"wages": "1.00"})
        body = seen[0]
        self.assertEqual(body["response_format"]["type"], "json_schema")
        self.assertEqual(body["response_format"]["json_schema"]["schema"], schema)
        img = body["messages"][0]["content"][1]["image_url"]["url"]
        self.assertTrue(img.startswith("data:image/png;base64,"))

    def test_falls_back_to_json_object_then_plain(self):
        formats = []

        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            rf = (body.get("response_format") or {}).get("type")
            formats.append(rf)
            if rf in ("json_schema", "json_object"):
                return httpx.Response(400, json={"error": {"message": f"{rf} not supported"}})
            return httpx.Response(200, json={"choices": [{"message": {"content": 'Sure: {"a": 1} done'}}]})

        be = OpenAICompatBackend(self._cfg(), transport=httpx.MockTransport(handler))
        self.assertEqual(be.chat_json(prompt="p", image_bytes=PNG_1PX, schema={"type": "object"}), {"a": 1})
        self.assertEqual(formats, ["json_schema", "json_object", None])

    def test_missing_key_message_names_env_not_value(self):
        cfg = self._cfg()
        os.environ.pop("TAXCLAW_TEST_KEY")
        with self.assertRaises(RuntimeError) as cm:
            OpenAICompatBackend(cfg).ensure_ready()
        self.assertIn("TAXCLAW_TEST_KEY", str(cm.exception))


class McpSafetyTest(CleanEnv):
    """Tool-level checks without a transport (the stdio path is covered by tests/mcp_stdio_client.py)."""

    def setUp(self):
        super().setUp()
        from src.config import CONFIG_PATH

        self.config_path = CONFIG_PATH
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.pdf = os.path.join(tempfile.mkdtemp(), "doc.pdf")
        import pymupdf

        d = pymupdf.open()
        d.new_page().insert_text((50, 72), "Form W-2 Wage and Tax Statement")
        d.save(self.pdf)

    def tearDown(self):
        self.config_path.unlink(missing_ok=True)
        super().tearDown()

    def test_cloud_backend_without_privacy_ack_is_a_tool_error(self):
        from mcp.server.mcpserver.exceptions import ToolError

        from src.mcp_server import ingest_document

        self.config_path.write_text("model_backend: openai_compat\nprivacy_acknowledged: false\n")
        with self.assertRaises(ToolError) as cm:
            ingest_document(path=self.pdf)
        self.assertIn("privacy", str(cm.exception).lower())

    def test_rejects_disallowed_files(self):
        from mcp.server.mcpserver.exceptions import ToolError

        from src.mcp_server import ingest_document

        txt = os.path.join(tempfile.mkdtemp(), "notes.txt")
        with open(txt, "w") as f:
            f.write("hello")
        fake_pdf = os.path.join(tempfile.mkdtemp(), "fake.pdf")
        with open(fake_pdf, "w") as f:
            f.write("not a pdf")
        for bad, why in ((txt, "unsupported file type"), (fake_pdf, "does not match"), (os.path.dirname(txt), "not a regular file")):
            with self.assertRaises(ToolError) as cm:
                ingest_document(path=bad)
            self.assertIn(why, str(cm.exception))

    def test_export_requires_exactly_one_scope(self):
        from mcp.server.mcpserver.exceptions import ToolError

        from src.mcp_server import export_documents

        with self.assertRaises(ToolError):
            export_documents(format="json")
        out = export_documents(format="json", all=True)
        self.assertIsInstance(json.loads(out["content"])["documents"], list)
        self.assertEqual(out["scope"], "all")


class ModelTierTest(CleanEnv):
    def test_ram_buckets(self):
        buckets = load_catalog()["tier1_local"]["ram_buckets"]
        self.assertEqual(_bucket_for(8, buckets)["default"], "gemma3:4b")
        self.assertIsNone(_bucket_for(8, buckets)["accuracy"])
        b16 = _bucket_for(16, buckets)
        self.assertEqual((b16["default"], b16["accuracy"]), ("gemma3:4b", "gemma3:12b"))
        self.assertEqual(_bucket_for(64, buckets)["default"], "gemma3:12b")

    def test_pick_by_patterns_prefers_newest_undated(self):
        ids = ["gpt-4o-mini", "gpt-4o-mini-2024-07-18", "gpt-5-mini", "gpt-5-mini-2025-08-07", "gpt-5", "gpt-4.1"]
        self.assertEqual(pick_by_patterns(ids, [r"^gpt-[\d.]+-mini", r"^gpt-4o-mini"]), "gpt-5-mini")
        self.assertEqual(pick_by_patterns(ids, [r"^gpt-[\d.]+$"]), "gpt-5")
        self.assertIsNone(pick_by_patterns(ids, [r"^nothing"]))

    def test_tier2_presence_only_and_live_listing(self):
        os.environ["OPENROUTER_API_KEY"] = "or-test-not-real"

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.host, "openrouter.ai")
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "google/gemini-9.0-flash", "architecture": {"input_modalities": ["text", "image"]}},
                        {"id": "google/gemini-9.0-flash-lite", "architecture": {"input_modalities": ["text", "image"]}},
                        {"id": "some/text-only", "architecture": {"input_modalities": ["text"]}},
                    ]
                },
            )

        t2 = tier2_cloud(Config(), live=True, transport=httpx.MockTransport(handler))
        by = {p["provider"]: p for p in t2["providers"]}
        self.assertTrue(by["openrouter"]["configured"])
        self.assertEqual(by["openrouter"]["vision_models"], ["google/gemini-9.0-flash", "google/gemini-9.0-flash-lite"])
        self.assertEqual(by["openrouter"]["recommended"]["balance"], "google/gemini-9.0-flash")
        self.assertIn("unbenchmarked", by["openrouter"]["recommended"]["basis"])
        self.assertFalse(by["openai"]["configured"])
        self.assertEqual(by["anthropic"]["recommended"]["balance"], "claude-haiku-5-5")
        self.assertNotIn("or-test-not-real", json.dumps(t2))


if __name__ == "__main__":
    unittest.main()
