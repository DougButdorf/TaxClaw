"""First-run doctor, use-cloud / use-local, processed_by and MCP setup_status tests.

No real installs, no network, no model: Ollama, RAM and disk are mocked, config and data live in a temp dir.

Run: PYTHONPATH=. venv/bin/python -P -m unittest tests.test_doctor -v
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pymupdf
import yaml

from src import cli, config, doctor, models
from src.backends import ExtractionResult
from src.config import Config

_KEY_ENVS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENROUTER_API_KEY",
    "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN", "OLLAMA_HOST", "OLLAMA_MODELS",
    "OPENCLAW_CONFIG_PATH", "OPENCLAW_STATE_DIR",
)

VISION = [{"name": "gemma3:4b", "vision": True}]
TEXT_ONLY = [{"name": "llama3.2:latest", "vision": False}]


class Isolated(unittest.TestCase):
    """Temp HOME, temp config.yaml, no provider keys, Ollama host unset."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="taxclaw-doctor-test-"))
        self.cfg_path = self.tmp / "config" / "config.yaml"
        self.data_dir = self.tmp / "data"
        env = {k: v for k, v in os.environ.items() if k not in _KEY_ENVS}
        env["HOME"] = str(self.tmp)
        patches = [
            mock.patch.dict(os.environ, env, clear=True),
            mock.patch.object(config, "CONFIG_PATH", self.cfg_path),
            # Safety net: nothing in this file may reach a real Ollama (tests that need one mock the doctor probes).
            mock.patch("ollama.Client", side_effect=ConnectionError("blocked in tests")),
            mock.patch.object(doctor, "find_ollama_binary", return_value=None),
            mock.patch.object(doctor, "probe_ollama", return_value=None),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.write_config({})

    def write_config(self, extra: dict) -> None:
        self.cfg_path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg_path.write_text(yaml.safe_dump({"data_dir": str(self.data_dir), **extra}))

    def read_config(self) -> dict:
        return yaml.safe_load(self.cfg_path.read_text())

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = cli.main(list(argv))
        return rc, out.getvalue(), err.getvalue()

    def make_pdf(self, name: str, text: str) -> str:
        p = self.tmp / name
        if p.exists():
            return str(p)
        d = pymupdf.open()
        d.new_page().insert_text((50, 72), text, fontsize=10)
        d.save(p)
        return str(p)

    def ingest(self, cfg: Config, name: str):
        from src import pipeline

        path = self.make_pdf(name, f"Form W-2 synthetic {name}")
        with mock.patch.object(pipeline, "ensure_backend_ready"), \
             mock.patch.object(pipeline, "classify_document", return_value={"doc_type": "W-2", "confidence": 0.9}), \
             mock.patch.object(pipeline, "extract_document_with_meta", return_value=ExtractionResult(data={"employer_name": "Synthetic LLC", "wages": "1.00"})), \
             mock.patch.object(pipeline, "extract_and_store_1099b_lots", return_value=(None, None)):
            return pipeline.ingest_path(path, cfg)

    def report(self, *, binary="/usr/local/bin/ollama", models_=VISION, ram=16.0, free=500.0, cfg=None):
        with mock.patch.object(doctor, "find_ollama_binary", return_value=binary), \
             mock.patch.object(doctor, "probe_ollama", return_value=models_), \
             mock.patch.object(doctor, "ram_gb", return_value=ram), \
             mock.patch.object(doctor, "free_disk_gb", return_value=free):
            return doctor.build_report(cfg or config.load_config(create_dirs=False))


class LocalStatesTest(Isolated):
    def test_a_ollama_binary_missing(self):
        r = self.report(binary=None, models_=None)
        loc = r["local"]
        self.assertEqual(loc["state"], "ollama_missing")
        self.assertFalse(loc["ready"])
        self.assertFalse(r["ready"])
        step = loc["next_step"]
        self.assertIn("https://ollama.com/download", step)
        self.assertIn("brew install ollama", step)
        self.assertIn("curl -fsSL https://ollama.com/install.sh | sh", step)
        self.assertIn("new terminal", step)
        self.assertIn("restart your agent", step)
        self.assertEqual(loc["install"]["url"], "https://ollama.com/download")
        self.assertEqual(r["next_step"], step)

    def test_b_server_unreachable_respects_ollama_host(self):
        r = self.report(binary="/usr/local/bin/ollama", models_=None)
        loc = r["local"]
        self.assertEqual(loc["state"], "server_unreachable")
        self.assertIn("Open the Ollama app", loc["next_step"])
        self.assertIn("ollama serve", loc["next_step"])
        self.assertIn("http://127.0.0.1:11434", loc["next_step"])
        self.assertNotIn("https://ollama.com/download", loc["next_step"])

        os.environ["OLLAMA_HOST"] = "127.0.0.1:9"
        loc = self.report(binary="/usr/local/bin/ollama", models_=None)["local"]
        self.assertEqual(loc["state"], "server_unreachable")
        self.assertIn("http://127.0.0.1:9", loc["next_step"])
        self.assertIn("OLLAMA_HOST=127.0.0.1:9", loc["next_step"])

    def test_b_remote_host_never_asks_for_an_install(self):
        os.environ["OLLAMA_HOST"] = "http://gpu-box.lan:11434"
        loc = self.report(binary=None, models_=None)["local"]
        self.assertEqual(loc["state"], "server_unreachable")
        self.assertIn("gpu-box.lan", loc["next_step"])
        self.assertNotIn("brew install", loc["next_step"])
        self.assertEqual(loc["warnings"], [])  # RAM/disk of this machine say nothing about the remote one

    def test_c_no_vision_model_recommends_by_ram_and_never_pulls(self):
        with mock.patch("subprocess.run") as run, mock.patch("subprocess.Popen") as popen:
            r = self.report(models_=TEXT_ONLY, ram=16.0)
        run.assert_not_called()
        popen.assert_not_called()
        loc = r["local"]
        self.assertEqual(loc["state"], "no_vision_model")
        self.assertFalse(loc["ready"])
        rec = loc["recommended"]
        self.assertEqual(rec["model"], "gemma3:4b")
        self.assertEqual(rec["approx_download"], "approx. 3.4 GB")
        self.assertEqual(rec["pull_command"], "ollama pull gemma3:4b")
        self.assertEqual(loc["commands"], ["ollama pull gemma3:4b"])
        self.assertIn("approx. 3.4 GB", loc["next_step"])
        self.assertIn("never downloads models", loc["next_step"])
        self.assertIn("llama3.2:latest", loc["next_step"])  # installed but text-only

    def test_c_recommendation_follows_ram_bucket(self):
        rec = self.report(models_=[], ram=64.0)["local"]["recommended"]
        self.assertEqual(rec["model"], "gemma3:12b")
        self.assertEqual(rec["approx_download"], "approx. 8.2 GB")

    def test_d_ready_shows_the_model(self):
        r = self.report(models_=VISION)
        loc = r["local"]
        self.assertEqual((loc["state"], loc["ready"], loc["model"]), ("ready", True, "gemma3:4b"))
        self.assertTrue(r["ready"])
        self.assertIn("gemma3:4b", loc["next_step"])
        self.assertIn("gemma3:4b", doctor.format_report(r))
        self.assertEqual(loc["warnings"], [])

    def test_vision_model_installed_but_not_selected(self):
        self.write_config({"local_model": "llama3.2"})
        r = self.report(models_=VISION + TEXT_ONLY)
        loc = r["local"]
        self.assertEqual(loc["state"], "model_not_selected")
        self.assertFalse(r["ready"])
        self.assertEqual(loc["commands"], ["taxclaw use-local --model gemma3:4b"])

    def test_low_ram_and_low_disk_warnings(self):
        loc = self.report(models_=[], ram=4.0, free=3.0)["local"]
        text = " ".join(loc["warnings"])
        self.assertIn("4 GB of RAM", text)
        self.assertIn("needs about 6 GB", text)
        self.assertIn("Only 3 GB of disk is free", text)
        self.assertEqual(len(loc["warnings"]), 2)
        self.assertEqual(self.report(models_=[], ram=16.0, free=500.0)["local"]["warnings"], [])

    def test_disk_warning_not_shown_for_an_installed_model(self):
        loc = self.report(models_=VISION, ram=16.0, free=1.0)["local"]
        self.assertEqual(loc["warnings"], [])

    def test_report_is_json_and_has_no_secrets(self):
        os.environ["ANTHROPIC_API_KEY"] = "sk-ant-SECRET-VALUE-123"
        r = self.report()
        blob = json.dumps(r)
        self.assertNotIn("SECRET-VALUE", blob)
        self.assertEqual(r["doctor_version"], 1)
        self.assertTrue(r["read_only"])
        self.assertTrue(any("Never choose cloud" in rule for rule in r["agent_rules"]))

    def test_doctor_writes_nothing(self):
        before = sorted(p.name for p in self.tmp.rglob("*"))
        self.report()
        self.assertEqual(before, sorted(p.name for p in self.tmp.rglob("*")))
        self.assertFalse(self.data_dir.exists())


class CloudAndHostedTest(Isolated):
    def test_usable_providers_ordered_by_measured_data(self):
        os.environ.update({"OPENAI_API_KEY": "x1", "GEMINI_API_KEY": "x2", "ANTHROPIC_API_KEY": "x3", "OPENROUTER_API_KEY": "x4"})
        cloud = self.report()["cloud"]
        self.assertEqual([p["provider"] for p in cloud["usable"]], ["anthropic", "openai", "gemini", "openrouter"])
        first = cloud["usable"][0]
        self.assertEqual(first["model"], "claude-haiku-5-5")
        self.assertIn("562/562", first["evidence"])
        self.assertEqual(first["switch_command"], "taxclaw use-cloud anthropic --model claude-haiku-5-5 --accept-privacy")
        self.assertEqual(cloud["usable"][1]["evidence"], "not benchmarked")
        self.assertIn("--model <", cloud["usable"][1]["switch_command"])  # no invented model id
        self.assertIn("Full page images", cloud["what_is_sent"])
        self.assertIn("terms", cloud["what_is_sent"])
        self.assertIn("accept-privacy", cloud["switching"])

    def test_no_keys_means_no_usable_providers(self):
        cloud = self.report()["cloud"]
        self.assertEqual(cloud["usable"], [])
        self.assertEqual(len(cloud["not_configured"]), 5)
        text = doctor.format_report(self.report())
        self.assertIn("No cloud API keys found", text)

    def test_cloudflare_needs_both_variables(self):
        os.environ["CLOUDFLARE_ACCOUNT_ID"] = "acct"
        self.assertEqual(self.report()["cloud"]["usable"], [])
        os.environ["CLOUDFLARE_API_TOKEN"] = "tok"
        usable = self.report()["cloud"]["usable"]
        self.assertEqual(usable[0]["use_cloud_name"], "cloudflare_clairic")
        self.assertEqual(usable[0]["switch_command"], "taxclaw use-cloud cloudflare_clairic --accept-privacy")

    def test_hosted_is_one_line_with_no_pricing_while_disabled(self):
        r = self.report()
        h = r["hosted"]
        self.assertFalse(h["enabled"])
        self.assertEqual(h["status"], "coming_soon")
        self.assertNotIn("pricing", h)
        text = doctor.format_report(r)
        self.assertIn("coming soon", text)
        for word in ("$0.10", "x402", "10 free", "free pages"):
            self.assertNotIn(word, text)
            self.assertNotIn(word, json.dumps(r))

    def test_hosted_pricing_appears_only_when_the_flag_is_enabled(self):
        cat = json.loads(json.dumps(models.load_catalog()))
        cat["hosted"]["enabled"] = True
        with mock.patch.object(models, "load_catalog", return_value=cat):
            r = self.report()
        self.assertTrue(r["hosted"]["enabled"])
        self.assertIn("10 free pages, then $0.10 per page, paid by your agent via x402", r["hosted"]["message"])
        self.assertIn("not stored", r["hosted"]["message"])
        self.assertIn("explicit, recorded consent", r["hosted"]["consent"])

    def test_catalog_ships_hosted_disabled_with_pricing_ready(self):
        h = models.load_catalog()["hosted"]
        self.assertIs(h["enabled"], False)
        self.assertEqual(h["pricing"]["free_pages"], 10)
        self.assertEqual(h["pricing"]["price_per_page_usd"], 0.10)


class UseCloudTest(Isolated):
    def test_refuses_without_accept_privacy_and_writes_nothing(self):
        before = self.cfg_path.read_text()
        rc, out, err = self.run_cli("use-cloud", "anthropic")
        self.assertEqual(rc, 2)
        self.assertIn("PRIVACY NOTICE", out)
        self.assertIn("Full page images", out)
        self.assertIn("Anthropic", out)
        self.assertIn("--accept-privacy", err)
        self.assertEqual(self.cfg_path.read_text(), before)
        self.assertEqual(config.load_config().backend, "local")
        self.assertFalse(config.load_config().privacy_acknowledged)

    def test_refusal_json(self):
        rc, out, _ = self.run_cli("use-cloud", "openai", "--model", "m", "--json")
        data = json.loads(out)
        self.assertEqual(rc, 2)
        self.assertFalse(data["ok"])
        self.assertFalse(data["changed"])
        self.assertEqual(data["retry_command"], "taxclaw use-cloud openai --model m --accept-privacy")

    def test_writes_consent_timestamp_and_provider(self):
        rc, out, _ = self.run_cli("use-cloud", "anthropic", "--model", "claude-sonnet-5-5", "--accept-privacy")
        self.assertEqual(rc, 0, out)
        raw = self.read_config()
        self.assertEqual(raw["model_backend"], "anthropic")
        self.assertEqual(raw["cloud_model"], "claude-sonnet-5-5")
        self.assertIs(raw["privacy_acknowledged"], True)
        self.assertEqual(raw["cloud_provider"], "anthropic")
        self.assertRegex(raw["privacy_acknowledged_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00$")
        cfg = config.load_config()
        self.assertTrue(cfg.is_cloud and cfg.privacy_acknowledged)
        self.assertEqual(cfg.privacy_acknowledged_at, raw["privacy_acknowledged_at"])
        self.assertIn(raw["privacy_acknowledged_at"], out)

    def test_default_model_is_the_catalog_pick(self):
        self.assertEqual(self.run_cli("use-cloud", "anthropic", "--accept-privacy")[0], 0)
        self.assertEqual(self.read_config()["cloud_model"], "claude-haiku-5-5")

    def test_openai_compat_provider_needs_a_model_and_resets_custom_url(self):
        self.write_config({"openai_compat_base_url": "https://elsewhere.example/v1", "openai_compat_api_key_env": "OTHER_KEY"})
        rc, _, err = self.run_cli("use-cloud", "openrouter", "--accept-privacy")
        self.assertEqual(rc, 2)
        self.assertIn("--model is required", err)
        self.assertEqual(self.read_config().get("model_backend", "local"), "local")
        rc, _, _ = self.run_cli("use-cloud", "openrouter", "--model", "vendor/vision-1", "--accept-privacy")
        self.assertEqual(rc, 0)
        raw = self.read_config()
        self.assertEqual((raw["model_backend"], raw["openai_compat_provider"], raw["openai_compat_model"]), ("openai_compat", "openrouter", "vendor/vision-1"))
        self.assertEqual(raw["openai_compat_base_url"], "")  # documents go to the provider named in the consent
        self.assertEqual(raw["cloud_provider"], "openrouter")

    def test_cloudflare_clairic(self):
        rc, _, _ = self.run_cli("use-cloud", "cloudflare_clairic", "--accept-privacy")
        self.assertEqual(rc, 0)
        raw = self.read_config()
        self.assertEqual((raw["model_backend"], raw["cloud_provider"]), ("cloudflare_clairic", "cloudflare"))
        self.assertEqual(self.run_cli("use-cloud", "cloudflare", "--model", "other", "--accept-privacy")[0], 2)

    def test_unknown_backend(self):
        rc, _, err = self.run_cli("use-cloud", "bogus", "--accept-privacy")
        self.assertEqual(rc, 2)
        self.assertIn("unknown cloud backend", err)

    def test_use_local_needs_no_consent_and_withdraws_it(self):
        self.run_cli("use-cloud", "anthropic", "--accept-privacy")
        self.assertTrue(config.load_config().is_cloud)
        rc, out, _ = self.run_cli("use-local", "--model", "gemma3:12b")
        self.assertEqual(rc, 0)
        self.assertIn("Cloud consent cleared", out)
        raw = self.read_config()
        self.assertEqual((raw["model_backend"], raw["local_model"]), ("local", "gemma3:12b"))
        self.assertIs(raw["privacy_acknowledged"], False)
        self.assertEqual((raw["privacy_acknowledged_at"], raw["cloud_provider"]), ("", ""))
        cfg = config.load_config()
        self.assertFalse(cfg.is_cloud)

    def test_use_local_json(self):
        with mock.patch.object(doctor, "find_ollama_binary", return_value=None), \
             mock.patch.object(doctor, "probe_ollama", return_value=None):
            rc, out, _ = self.run_cli("use-local", "--json")
        data = json.loads(out)
        self.assertEqual(rc, 0)
        self.assertEqual((data["model_backend"], data["documents_left_machine"], data["local_ready"]), ("local", False, False))

    def test_doctor_cli_json_and_alias(self):
        for name in ("doctor", "setup"):
            with mock.patch.object(doctor, "find_ollama_binary", return_value=None), \
                 mock.patch.object(doctor, "probe_ollama", return_value=None):
                rc, out, _ = self.run_cli(name, "--json")
            self.assertEqual(rc, 0)
            self.assertEqual(json.loads(out)["local"]["state"], "ollama_missing")
        with mock.patch.object(doctor, "find_ollama_binary", return_value=None), \
             mock.patch.object(doctor, "probe_ollama", return_value=None):
            rc, out, _ = self.run_cli("doctor")
        self.assertIn("PATH 1", out)
        self.assertIn("PATH 2", out)
        self.assertIn("PATH 3", out)

    def test_cloud_config_without_consent_is_not_ready(self):
        self.write_config({"model_backend": "anthropic", "privacy_acknowledged": False})
        r = self.report()
        self.assertFalse(r["ready"])
        self.assertIn("privacy", r["next_step"].lower())
        self.assertIn("Only the user", r["next_step"])


class ProcessedByTest(Isolated):
    def test_local_result_says_documents_stayed(self):
        cfg = config.load_config()
        res = self.ingest(cfg, "a.pdf")
        self.assertEqual(
            res["processed_by"],
            {"backend": "local", "model": "gemma3:4b", "provider": "ollama", "documents_left_machine": False},
        )

    def test_cloud_result_says_documents_left(self):
        self.write_config({"model_backend": "anthropic", "cloud_model": "claude-haiku-5-5", "privacy_acknowledged": True})
        res = self.ingest(config.load_config(), "b.pdf")
        pb = res["processed_by"]
        self.assertEqual((pb["backend"], pb["model"], pb["provider"], pb["documents_left_machine"]), ("anthropic", "claude-haiku-5-5", "anthropic", True))

    def test_duplicate_keeps_the_original_record(self):
        res = self.ingest(config.load_config(), "c.pdf")
        self.write_config({"model_backend": "anthropic", "privacy_acknowledged": True})
        again = self.ingest(config.load_config(), "c.pdf")  # same bytes -> same hash
        self.assertTrue(again["duplicate"])
        self.assertEqual(again["processed_by"], res["processed_by"])
        self.assertFalse(again["processed_by"]["documents_left_machine"])

    def test_exports_carry_the_line_and_the_block(self):
        from src import exporter
        from src.accountant_exports import build_8949, export_txf

        self.ingest(config.load_config(), "d.pdf")
        data = json.loads(exporter.export_all_json())
        notice = data["_taxclaw_notice"]
        self.assertEqual(notice["processed_by"]["backend"], "local")
        self.assertFalse(notice["processed_by"]["documents_left_machine"])
        self.assertIn("Documents left this machine: no", notice["processed_by_notice"])
        self.assertEqual(data["documents"][0]["processed_by"]["model"], "gemma3:4b")
        for csv_text in (exporter.export_all_csv_wide(), exporter.export_all_csv_long()):
            self.assertIn("# Processed by: local / gemma3:4b (ollama). Documents left this machine: no.", csv_text)
        e = build_8949(None)
        self.assertIn("# Processed by:", e.content)
        self.assertIn("Documents left this machine", e.processed_by_line)
        self.assertIn("Documents left this machine", export_txf(None).processed_by_line)

    def test_mixed_exports_report_that_some_documents_left(self):
        from src import exporter

        self.ingest(config.load_config(), "e.pdf")
        self.write_config({"model_backend": "anthropic", "cloud_model": "claude-haiku-5-5", "privacy_acknowledged": True})
        self.ingest(config.load_config(), "f.pdf")
        pb = json.loads(exporter.export_all_json())["_taxclaw_notice"]["processed_by"]
        self.assertEqual((pb["backend"], pb["documents_left_machine"], pb["documents"]), ("mixed", True, 2))
        self.assertEqual(sorted(c["backend"] for c in pb["breakdown"]), ["anthropic", "local"])
        self.assertIn("Documents left this machine: yes", exporter.export_all_csv_wide())

    def test_documents_stored_before_this_existed_are_unknown_not_local(self):
        from src import exporter
        from src.db import db

        res = self.ingest(config.load_config(), "g.pdf")
        with db() as con:
            con.execute("UPDATE documents SET processed_by=NULL WHERE id=?", (res["document_id"],))
        pb = json.loads(exporter.export_all_json())["_taxclaw_notice"]["processed_by"]
        self.assertIsNone(pb["documents_left_machine"])
        self.assertEqual(pb["documents_without_record"], 1)
        self.assertIn("Documents left this machine: unknown", exporter.export_all_csv_wide())

    def test_cli_ingest_json_and_list_json_include_it(self):
        from src import pipeline

        path = self.make_pdf("h.pdf", "Form W-2 synthetic h")
        with mock.patch.object(pipeline, "ensure_backend_ready"), \
             mock.patch.object(pipeline, "classify_document", return_value={"doc_type": "W-2", "confidence": 0.9}), \
             mock.patch.object(pipeline, "extract_document_with_meta", return_value=ExtractionResult(data={"wages": "1.00"})), \
             mock.patch.object(pipeline, "extract_and_store_1099b_lots", return_value=(None, None)):
            rc, out, _ = self.run_cli("ingest", path, "--json")
        self.assertEqual(rc, 0)
        self.assertFalse(json.loads(out)["processed_by"]["documents_left_machine"])
        rc, out, _ = self.run_cli("list", "--json")
        self.assertEqual(json.loads(out)["documents"][0]["processed_by"]["backend"], "local")

    def test_cli_ingest_backend_error_carries_the_doctor_next_step(self):
        path = self.make_pdf("i.pdf", "Form W-2 synthetic i")
        with mock.patch.object(doctor, "find_ollama_binary", return_value=None), \
             mock.patch.object(doctor, "probe_ollama", return_value=None), \
             mock.patch("src.ai.ensure_backend_ready", side_effect=RuntimeError("Ollama is not reachable at http://127.0.0.1:11434.")), \
             mock.patch("src.pipeline.ensure_backend_ready", side_effect=RuntimeError("Ollama is not reachable at http://127.0.0.1:11434.")):
            rc, out, _ = self.run_cli("ingest", path, "--json")
        data = json.loads(out)
        self.assertEqual((rc, data["stage"]), (3, "backend"))
        self.assertIn("https://ollama.com/download", data["next_step"])


class McpTest(Isolated):
    def test_setup_status_tool_returns_the_doctor_report(self):
        from src import mcp_server

        names = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
        self.assertIn("setup_status", names)
        with mock.patch.object(doctor, "find_ollama_binary", return_value="/x/ollama"), \
             mock.patch.object(doctor, "probe_ollama", return_value=VISION), \
             mock.patch.object(doctor, "ram_gb", return_value=16.0), \
             mock.patch.object(doctor, "free_disk_gb", return_value=100.0):
            via_tool = mcp_server.setup_status()
            expected = doctor.build_report(config.load_config(create_dirs=False))
        self.assertEqual(via_tool, expected)
        self.assertEqual(via_tool["local"]["state"], "ready")
        json.dumps(via_tool)

    def test_no_tool_can_switch_to_cloud_or_record_consent(self):
        from src import mcp_server

        tools = asyncio.run(mcp_server.mcp.list_tools())
        self.assertEqual(
            {t.name for t in tools},
            {"ingest_document", "list_documents", "get_document", "export_documents", "list_models", "setup_status"},
        )
        for t in tools:
            props = set((t.input_schema or {}).get("properties", {}))
            self.assertFalse(props & {"accept_privacy", "privacy_acknowledged", "model_backend", "backend", "consent"}, t.name)
        with mock.patch.object(doctor, "find_ollama_binary", return_value=None), \
             mock.patch.object(doctor, "probe_ollama", return_value=None):
            before = self.cfg_path.read_text()
            mcp_server.setup_status()
            self.assertEqual(self.cfg_path.read_text(), before)

    def test_ingest_not_ready_error_includes_the_doctor_next_step(self):
        from mcp.server.mcpserver.exceptions import ToolError

        from src import mcp_server, pipeline

        p = self.tmp / "w2.pdf"
        d = pymupdf.open()
        d.new_page().insert_text((50, 72), "Form W-2", fontsize=10)
        d.save(p)
        err = "Ollama is not reachable at http://127.0.0.1:11434. Start it with `ollama serve`"
        with mock.patch.object(doctor, "find_ollama_binary", return_value=None), \
             mock.patch.object(doctor, "probe_ollama", return_value=None), \
             mock.patch.object(pipeline, "ensure_backend_ready", side_effect=RuntimeError(err)):
            with self.assertRaises(ToolError) as cm:
                mcp_server.ingest_document(str(p))
        msg = str(cm.exception)
        self.assertIn("backend not ready", msg)
        self.assertIn("Next step:", msg)
        self.assertIn("https://ollama.com/download", msg)
        self.assertIn("setup_status", msg)
        self.assertIn("Do not switch the user to cloud yourself", msg)

    def test_get_document_and_list_carry_processed_by(self):
        from src import mcp_server

        res = self.ingest(config.load_config(), "j.pdf")
        got = mcp_server.get_document(res["document_id"])
        self.assertFalse(got["document"]["processed_by"]["documents_left_machine"])
        listed = mcp_server.list_documents()
        self.assertEqual(listed["documents"][0]["processed_by"]["backend"], "local")
        ex = mcp_server.export_documents(all=True, format="json")
        self.assertFalse(ex["processed_by"]["documents_left_machine"])
        self.assertIn("Documents left this machine: no", ex["processed_by_notice"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
