"""tax_year output contract (mocked backends; no network, no model).

Every top-level ``tax_year`` is a 4-digit string or null; the 1099-DA
``header.tax_year`` is an int or null. Enforced after extraction on every
backend path, so a model returning the wrong JSON type cannot reach storage.

Run: PYTHONPATH=. venv/bin/python -P -m unittest discover -s tests -v
"""

from __future__ import annotations

import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pymupdf

_TMP_HOME = tempfile.mkdtemp(prefix="taxclaw-test-home-")
os.environ["HOME"] = _TMP_HOME

from src import extract  # noqa: E402
from src.backends import (  # noqa: E402
    AnthropicBackend,
    ClairicBackend,
    ExtractionResult,
    LocalBackend,
    OpenAICompatBackend,
)
from src.config import Config  # noqa: E402
from src.extract import (  # noqa: E402
    PROMPTS,
    apply_tax_year_contract,
    extract_document_with_meta,
    parse_tax_year,
    schema_for,
)

STRING_FORMS = ("1099-DIV", "consolidated-1099", "1099-B", "1099-MISC", "1099-OID", "K-1", "1099-R", "1099-G", "1099-K")


def _one_page_pdf(text: str = "synthetic") -> str:
    path = Path(tempfile.mkdtemp()) / "doc.pdf"
    d = pymupdf.open()
    d.new_page().insert_text((50, 72), text)
    d.save(path)
    return str(path)


class ParseTaxYearTest(unittest.TestCase):
    def test_plausible(self):
        for raw in (2025, 2025.0, "2025", " 2025 ", "2025.0", "2025.00", 1990, 2100):
            self.assertEqual(parse_tax_year(raw), int(float(str(raw).strip())), raw)

    def test_implausible(self):
        for raw in (True, False, 2025.5, "TY2025", "2025-12-31", "25", "20255", "", "abc", 1989, 2101, 0, -2025, [], {}, float("nan")):
            self.assertIsNone(parse_tax_year(raw), repr(raw))


class SchemaTest(unittest.TestCase):
    def test_top_level_tax_year_is_string_in_every_schema(self):
        for t in STRING_FORMS:
            props = schema_for(t)["properties"]
            self.assertEqual(props["tax_year"]["type"], ["string", "null"], t)

    def test_compact_prompts_declare_string(self):
        for t in ("1099-DIV", "consolidated-1099", "1099-B", "1099-MISC", "1099-OID"):
            self.assertIn('"tax_year":string|null', PROMPTS[t], t)
            self.assertNotIn('"tax_year":null', PROMPTS[t], t)

    def test_da_header_tax_year_is_integer(self):
        header = schema_for("1099-DA")["properties"]["header"]
        self.assertEqual(header["properties"]["tax_year"]["type"], ["integer", "null"])
        self.assertIn("tax_year", header["required"])

    def test_forms_without_tax_year_have_none(self):
        for t in ("W-2", "1099-NEC", "1099-INT"):
            self.assertNotIn("tax_year", schema_for(t)["properties"], t)


class ApplyContractTest(unittest.TestCase):
    def test_number_becomes_string_for_misc_b_consolidated(self):
        for t in ("1099-MISC", "1099-B", "consolidated-1099"):
            data = {"payer_name": "Acme", "tax_year": 2025}
            out, review = apply_tax_year_contract(data, t)
            self.assertEqual(out["tax_year"], "2025", t)
            self.assertIsInstance(out["tax_year"], str)
            self.assertEqual(review, [], t)
            self.assertEqual(data["tax_year"], 2025, "input must not be mutated")

    def test_string_variants_normalize(self):
        for raw in (2025.0, "2025.0", " 2025 ", "2025"):
            out, review = apply_tax_year_contract({"tax_year": raw}, "1099-MISC")
            self.assertEqual((out["tax_year"], review), ("2025", []), repr(raw))

    def test_da_header_string_becomes_int(self):
        for raw in ("2025", " 2025 ", "2025.0", 2025.0, 2025):
            out, review = apply_tax_year_contract({"header": {"tax_year": raw, "payer_name": "X"}, "transactions": []}, "1099-DA")
            self.assertEqual(out["header"]["tax_year"], 2025, repr(raw))
            self.assertIs(type(out["header"]["tax_year"]), int)
            self.assertEqual(out["header"]["payer_name"], "X")
            self.assertEqual(review, [])

    def test_null_stays_null(self):
        out, review = apply_tax_year_contract({"tax_year": None}, "1099-B")
        self.assertEqual((out, review), ({"tax_year": None}, []))
        out, review = apply_tax_year_contract({"header": {"tax_year": None}}, "1099-DA")
        self.assertEqual((out, review), ({"header": {"tax_year": None}}, []))
        out, review = apply_tax_year_contract({"wages": "1.00"}, "W-2")  # key absent: not added
        self.assertEqual((out, review), ({"wages": "1.00"}, []))

    def test_weird_value_is_kept_and_flagged(self):
        out, review = apply_tax_year_contract({"tax_year": "Tax Year 2025"}, "1099-MISC")
        self.assertEqual((out["tax_year"], review), ("Tax Year 2025", ["tax_year"]))
        out, review = apply_tax_year_contract({"tax_year": 1850}, "1099-B")
        self.assertEqual((out["tax_year"], review), (1850, ["tax_year"]))
        out, review = apply_tax_year_contract({"header": {"tax_year": "unknown"}}, "1099-DA")
        self.assertEqual((out["header"]["tax_year"], review), ("unknown", ["header.tax_year"]))

    def test_da_top_level_tax_year_is_not_touched_and_bad_shapes_are_safe(self):
        out, _ = apply_tax_year_contract({"tax_year": 2025, "header": {}}, "1099-DA")
        self.assertEqual(out["tax_year"], 2025)
        for bad in (None, [], "text", {"header": None}, {"header": "x"}):
            apply_tax_year_contract(copy.deepcopy(bad), "1099-DA")


class _Backends(unittest.TestCase):
    def setUp(self):
        os.environ["TAXCLAW_TEST_CF_TOKEN"] = "test-token-not-real"

    def tearDown(self):
        os.environ.pop("TAXCLAW_TEST_CF_TOKEN", None)

    def cfgs(self):
        return {
            "local": (Config(model_backend="local"), LocalBackend),
            "anthropic": (Config(model_backend="anthropic", privacy_acknowledged=True), AnthropicBackend),
            "openai_compat": (Config(model_backend="openai_compat", privacy_acknowledged=True), OpenAICompatBackend),
        }


class PipelineEntryTest(_Backends):
    """extract_document_with_meta is the one place every caller (CLI, MCP, web, benchmark) goes through."""

    def test_prompt_backends_normalize_string_forms(self):
        pdf = _one_page_pdf()
        for name, (cfg, cls) in self.cfgs().items():
            for doc_type in ("1099-MISC", "1099-B", "consolidated-1099"):
                with mock.patch.object(cls, "chat_json", return_value={"payer_name": "Acme", "tax_year": 2025}):
                    res = extract_document_with_meta(pdf, doc_type, cfg)
                self.assertEqual(res.data["tax_year"], "2025", (name, doc_type))
                self.assertEqual(res.review_fields, [], (name, doc_type))

    def test_prompt_backends_normalize_da_header_and_keep_transactions(self):
        pdf = _one_page_pdf()
        reply = {"header": {"payer_name": "X", "tax_year": "2025"}, "transactions": [{"asset_code": "BTC"}], "is_multi_transaction": False}
        for name, (cfg, cls) in self.cfgs().items():
            with mock.patch.object(cls, "chat_json", return_value=copy.deepcopy(reply)):
                res = extract_document_with_meta(pdf, "1099-DA", cfg)
            self.assertEqual(res.data["header"]["tax_year"], 2025, name)
            self.assertIs(type(res.data["header"]["tax_year"]), int, name)
            self.assertEqual(res.data["transactions"], [{"asset_code": "BTC"}], name)

    def test_null_and_weird_through_pipeline(self):
        pdf = _one_page_pdf()
        cfg, cls = self.cfgs()["local"]
        with mock.patch.object(cls, "chat_json", return_value={"tax_year": None, "payer_name": "Acme"}):
            res = extract_document_with_meta(pdf, "1099-MISC", cfg)
        self.assertIsNone(res.data["tax_year"])
        self.assertEqual(res.review_fields, [])
        # Placeholder strings are nulled before the contract runs.
        with mock.patch.object(cls, "chat_json", return_value={"tax_year": "null"}):
            res = extract_document_with_meta(pdf, "1099-MISC", cfg)
        self.assertIsNone(res.data["tax_year"])
        with mock.patch.object(cls, "chat_json", return_value={"tax_year": "last year"}):
            res = extract_document_with_meta(pdf, "1099-MISC", cfg)
        self.assertEqual(res.data["tax_year"], "last year")
        self.assertEqual(res.review_fields, ["tax_year"])

    def test_multi_page_merge_then_normalize(self):
        path = Path(tempfile.mkdtemp()) / "two.pdf"
        d = pymupdf.open()
        d.new_page()
        d.new_page()
        d.save(path)
        replies = iter([{"payer_name": "Acme", "tax_year": None}, {"tax_year": 2025}])
        cfg, cls = self.cfgs()["local"]
        with mock.patch.object(cls, "chat_json", side_effect=lambda **_: next(replies)):
            res = extract_document_with_meta(str(path), "1099-B", cfg)
        self.assertEqual(res.data["tax_year"], "2025")

    def test_clairic_structured_path_and_da_header_merge(self):
        cfg = Config(
            model_backend="cloudflare_clairic",
            privacy_acknowledged=True,
            cloudflare_account_id="acct123",
            cloudflare_api_token_env="TAXCLAW_TEST_CF_TOKEN",
        )
        pdf = _one_page_pdf()
        with mock.patch.object(
            ClairicBackend, "extract_structured",
            return_value=ExtractionResult(data={"payer_name": "Acme", "tax_year": 2025}, method="clairic"),
        ):
            res = extract_document_with_meta(pdf, "1099-MISC", cfg)
        self.assertEqual(res.data["tax_year"], "2025")
        self.assertEqual(res.method, "clairic")

        structured = ExtractionResult(data={"header": {"payer_name": "Acme", "tax_year": "2025.0"}}, method="clairic")
        with mock.patch.object(ClairicBackend, "extract_structured", return_value=structured), \
                mock.patch.object(ClairicBackend, "chat_json", return_value={"header": {}, "transactions": [{"asset_code": "BTC"}]}):
            res = extract_document_with_meta(pdf, "1099-DA", cfg)
        self.assertEqual(res.data["header"]["tax_year"], 2025)
        self.assertEqual(len(res.data["transactions"]), 1)

        bad = ExtractionResult(data={"tax_year": "soon"}, review_fields=["payer_name"], method="clairic")
        with mock.patch.object(ClairicBackend, "extract_structured", return_value=bad):
            res = extract_document_with_meta(pdf, "1099-MISC", cfg)
        self.assertEqual(res.review_fields, ["payer_name", "tax_year"])

    def test_extract_document_wrapper_is_normalized(self):
        cfg, cls = self.cfgs()["local"]
        with mock.patch.object(cls, "chat_json", return_value={"tax_year": 2025}):
            self.assertEqual(extract.extract_document(_one_page_pdf(), "1099-OID", cfg)["tax_year"], "2025")


class BenchmarkGraderTest(unittest.TestCase):
    """Run the strict benchmark grader on synthetic model output; no model calls."""

    @classmethod
    def setUpClass(cls):
        from benchmarks.taxclaw_accuracy.fixtures import build_fixtures

        cls.fixtures = {r["fixture_id"]: r for r in build_fixtures(Path(tempfile.mkdtemp()))}

    def test_expected_year_types_match_contract(self):
        self.assertEqual(self.fixtures["1099_misc_clean"]["expected"]["tax_year"], "2025")
        self.assertEqual(self.fixtures["1099_da_clean"]["expected"]["header"]["tax_year"], 2025)

    def test_normalized_output_scores_exact(self):
        from benchmarks.taxclaw_accuracy.grader import score

        for fid, doc_type in (("1099_misc_clean", "1099-MISC"), ("1099_b_clean", "1099-B"),
                              ("consolidated_1099_clean", "consolidated-1099"), ("1099_da_clean", "1099-DA")):
            rec = self.fixtures[fid]
            self.assertEqual(rec["doc_type"], doc_type)
            raw = copy.deepcopy(rec["expected"])  # a perfect read except for the year's JSON type
            if doc_type == "1099-DA":
                raw["header"]["tax_year"] = "2025"
            else:
                raw["tax_year"] = 2025
            before = score(rec["expected"], raw, rec["field_types"])
            if doc_type != "1099-DA":  # the grader's "number" kind tolerates a numeric string; "text" does not
                self.assertFalse(before["exact_document"], f"{fid}: wrong year type must fail the strict grader")
            fixed, review = apply_tax_year_contract(raw, doc_type)
            after = score(rec["expected"], fixed, rec["field_types"])
            self.assertTrue(after["exact_document"], (fid, [f for f in after["fields"] if not f["correct"]]))
            self.assertEqual(review, [])


if __name__ == "__main__":
    unittest.main()
