"""Clairic adapter tests against the documented request/response schema (mocked HTTP; no network).

Run: PYTHONPATH=. venv/bin/python -P -m unittest discover -s tests -v
"""

from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

import httpx
import pymupdf

# Isolate config/data before importing TaxClaw modules.
_TMP_HOME = tempfile.mkdtemp(prefix="taxclaw-test-home-")
os.environ["HOME"] = _TMP_HOME

from src import clairic  # noqa: E402
from src.backends import ClairicBackend, get_backend  # noqa: E402
from src.config import Config  # noqa: E402

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _answer(value, *, confidence=0.99, p_null=1e-6, typ="number"):
    return {"type": typ, "value": value, "guess": value, "confidence": confidence, "p_null": p_null}


def w2_response(**overrides):
    """A response shaped like the documented schema-output.json, wrapped like Workers AI REST."""

    answers = {
        "employer_name": _answer("Synthetic Widgets LLC", typ="text") | {"span": [10, 31]},
        "employer_ein": _answer("12-3456789", typ="text"),
        "employee_ssn": _answer("XXX-XX-1234", typ="text"),
        "wages": _answer(54321.0),
        "federal_withheld": _answer(6789.1, confidence=0.62),  # low confidence -> review
        "state_wages": _answer(54321.0),
        "state_withheld": _answer(None, confidence=0.9, p_null=0.55),  # ambiguous null -> review
        "local_wages": _answer(None, confidence=0.99, p_null=0.999),  # confidently blank
        "box_codes": {"type": "list", "value": ["D=2000.00", "DD: 5,000.00"], "spans": [[1, 2], [3, 4]], "confidence": 0.97},
    }
    answers.update(overrides)
    return {
        "result": {
            "model": "clairic",
            "answers": answers,
            "truncated": False,
            "usage": {"state_tokens": 61, "image_tokens": 900, "schema_tokens": 472, "input_tokens": 1433, "output_tokens": 0, "passes": 1},
        },
        "success": True,
        "errors": [],
        "messages": [],
    }


class Recorder:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        body = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        return httpx.Response(200, json=body)


def clairic_cfg() -> Config:
    return Config(
        model_backend="cloudflare_clairic",
        privacy_acknowledged=True,
        cloudflare_account_id="acct123",
        cloudflare_api_token_env="TAXCLAW_TEST_CF_TOKEN",
    )


class ClairicFieldMappingTest(unittest.TestCase):
    def test_w2_fields_typed(self):
        fields, plan = clairic.build_fields("W-2")
        self.assertEqual(fields["wages"]["type"], "number")
        self.assertEqual(fields["wages"]["decimals"], 2)
        self.assertEqual(fields["wages"]["unit"], "USD")
        self.assertEqual(fields["employer_ein"]["type"], "text")
        self.assertEqual(fields["employee_ssn"]["type"], "text")
        self.assertEqual(fields["employer_name"]["type"], "text")
        self.assertEqual(fields["box_codes"], fields["box_codes"] | {"type": "list", "items": "text"})
        self.assertIn("box 1", fields["wages"]["instructions"])  # prompt comment reused as instructions

    def test_other_forms(self):
        f, _ = clairic.build_fields("1099-R")
        self.assertEqual(f["date_of_payment"]["type"], "date")
        self.assertTrue(f["ira_sep_simple"]["integer"])  # checkbox -> 0/1
        self.assertEqual(f["distribution_codes"]["type"], "text")
        f, _ = clairic.build_fields("K-1")
        self.assertEqual(f["net_short_term_gain"]["decimals"], 2)
        self.assertEqual(f["other_deductions"]["type"], "list")
        self.assertEqual(f["profit_sharing_pct"]["type"], "text")
        f, _ = clairic.build_fields("1099-K")
        self.assertEqual(f["march"]["decimals"], 2)
        self.assertTrue(f["number_of_transactions"]["integer"])

    def test_every_schema_form_maps_and_names_are_valid(self):
        import re

        from src.extract import PROMPTS

        name_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]{0,63}$")  # schema-input.json propertyNames
        for doc_type in PROMPTS:
            if not clairic.supports_doc_type(doc_type):
                continue
            fields, _ = clairic.build_fields(doc_type)
            self.assertTrue(fields, doc_type)
            for name, spec in fields.items():
                self.assertRegex(name, name_re)
                self.assertIn(spec["type"], {"text", "number", "date", "list"})

    def test_1099da_header_only(self):
        fields, _ = clairic.build_fields("1099-DA")
        self.assertIn("header.payer_name", fields)
        self.assertFalse(any(k.startswith("transactions") for k in fields))

    def test_unsupported(self):
        self.assertFalse(clairic.supports_doc_type("generic"))
        self.assertFalse(clairic.supports_doc_type("1040"))
        self.assertFalse(clairic.supports_doc_type("unknown"))


class ClairicBatchingTest(unittest.TestCase):
    def test_max_four_images_per_call(self):
        pages = [(PNG_1PX, f"page {i}") for i in range(9)]
        batches = clairic.batch_pages(pages)
        self.assertEqual([len(b) for b in batches], [4, 4, 1])

    def test_request_shape(self):
        fields, _ = clairic.build_fields("W-2")
        body = clairic.build_request(fields, [(PNG_1PX, "Form W-2 text layer"), (PNG_1PX, "")])
        self.assertEqual(body["model"], "clairic")
        self.assertIn("Form W-2 text layer", body["state"])
        self.assertEqual(len(body["images"]), 2)
        self.assertEqual(body["images"][0]["content_type"], "image/png")
        self.assertEqual(base64.b64decode(body["images"][0]["base64"]), PNG_1PX)


class ClairicAdapterTest(unittest.TestCase):
    def setUp(self):
        os.environ["TAXCLAW_TEST_CF_TOKEN"] = "test-token-not-real"

    def tearDown(self):
        os.environ.pop("TAXCLAW_TEST_CF_TOKEN", None)

    def _backend(self, rec: Recorder) -> ClairicBackend:
        return ClairicBackend(clairic_cfg(), transport=httpx.MockTransport(rec))

    def test_extract_w2_with_confidence_and_review(self):
        rec = Recorder([w2_response()])
        be = self._backend(rec)
        res = be.extract_structured(doc_type="W-2", pages=[(PNG_1PX, "Form W-2 Wage and Tax Statement")])

        req = rec.requests[0]
        self.assertEqual(str(req.url), "https://api.cloudflare.com/client/v4/accounts/acct123/ai/run/@cf/cloudflare/clairic")
        self.assertEqual(req.headers["authorization"], "Bearer test-token-not-real")
        sent = json.loads(req.content)
        self.assertEqual(sent["model"], "clairic")
        self.assertEqual(sent["fields"]["wages"]["type"], "number")

        d = res.data
        self.assertEqual(d["wages"], "54321.00")
        self.assertEqual(d["federal_withheld"], "6789.10")
        self.assertEqual(d["employer_name"], "Synthetic Widgets LLC")
        self.assertIsNone(d["local_wages"])
        self.assertEqual(d["box_codes"], {"D": "2000.00", "DD": "5,000.00"})
        self.assertAlmostEqual(res.field_confidence["wages"], 0.99)
        self.assertAlmostEqual(res.field_confidence["federal_withheld"], 0.62)
        self.assertEqual(sorted(res.review_fields), ["federal_withheld", "state_withheld"])
        self.assertEqual(res.method, "clairic")

    def test_unwrapped_binding_shape_also_accepted(self):
        rec = Recorder([w2_response()["result"]])
        res = self._backend(rec).extract_structured(doc_type="W-2", pages=[(PNG_1PX, "")])
        self.assertEqual(res.data["wages"], "54321.00")

    def test_batches_merge_first_non_null(self):
        first = w2_response(wages=_answer(None, p_null=0.99))
        second = w2_response(wages=_answer(1000.0, confidence=0.95))
        rec = Recorder([first, second])
        pages = [(PNG_1PX, f"p{i}") for i in range(6)]
        res = self._backend(rec).extract_structured(doc_type="W-2", pages=pages)
        self.assertEqual(len(rec.requests), 2)
        self.assertEqual(len(json.loads(rec.requests[0].content)["images"]), 4)
        self.assertEqual(len(json.loads(rec.requests[1].content)["images"]), 2)
        self.assertEqual(res.data["wages"], "1000.00")
        self.assertAlmostEqual(res.field_confidence["wages"], 0.95)

    def test_http_error_never_leaks_token(self):
        def handler(request):
            return httpx.Response(403, json={"success": False, "errors": [{"code": 10000, "message": "Authentication error"}]})

        be = ClairicBackend(clairic_cfg(), transport=httpx.MockTransport(handler))
        with self.assertRaises(RuntimeError) as cm:
            be.extract_structured(doc_type="W-2", pages=[(PNG_1PX, "")])
        self.assertIn("Authentication error", str(cm.exception))
        self.assertNotIn("test-token-not-real", str(cm.exception))

    def test_ensure_ready_presence_only(self):
        os.environ.pop("TAXCLAW_TEST_CF_TOKEN", None)
        with self.assertRaises(RuntimeError) as cm:
            get_backend(clairic_cfg()).ensure_ready()
        self.assertIn("TAXCLAW_TEST_CF_TOKEN", str(cm.exception))

    def test_classify(self):
        resp = {"model": "clairic", "answers": {"form_type": _answer("Form 1099-INT", typ="text", confidence=0.97)}, "truncated": False, "usage": {"input_tokens": 1, "output_tokens": 0}}
        out = self._backend(Recorder([resp])).classify_image(PNG_1PX)
        self.assertEqual(out["doc_type"], "1099-INT")
        self.assertAlmostEqual(out["confidence"], 0.97)

    def test_normalize_form_type(self):
        n = clairic.normalize_form_type
        self.assertEqual(n("W-2"), "W-2")
        self.assertEqual(n("Schedule K-1 (Form 1065)"), "K-1")
        self.assertEqual(n("1099-K"), "1099-K")
        self.assertEqual(n("1099-DIV"), "1099-DIV")
        self.assertEqual(n("Consolidated 1099"), "consolidated-1099")
        self.assertIsNone(n("invoice"))


class ClairicPipelineTest(unittest.TestCase):
    """End to end through extract_document_with_meta + store (Clairic mocked)."""

    def setUp(self):
        os.environ["TAXCLAW_TEST_CF_TOKEN"] = "test-token-not-real"

    def tearDown(self):
        os.environ.pop("TAXCLAW_TEST_CF_TOKEN", None)

    def test_w2_pipeline_stores_field_confidence(self):
        from unittest import mock

        from src import backends
        from src.db import db, init_db
        from src.extract import extract_document_with_meta
        from src.store import store_extracted_fields

        init_db()
        tmp = Path(tempfile.mkdtemp())
        pdf = tmp / "w2.pdf"
        d = pymupdf.open()
        d.new_page().insert_text((50, 72), "Form W-2 Wage and Tax Statement (synthetic)")
        d.save(pdf)

        rec = Recorder([w2_response()])
        real_init = backends.ClairicBackend.__init__

        def patched_init(self, cfg, *, transport=None):
            real_init(self, cfg, transport=httpx.MockTransport(rec))

        with mock.patch.object(backends.ClairicBackend, "__init__", patched_init):
            res = extract_document_with_meta(str(pdf), "W-2", clairic_cfg())

        sent = json.loads(rec.requests[0].content)
        self.assertIn("Wage and Tax Statement", sent["state"])  # PDF text layer goes in `state`
        doc_id = "test-doc-clairic"
        with db() as con:
            con.execute(
                "INSERT INTO documents (id, file_path, file_hash, original_filename, mime_type, doc_type, status) VALUES (?,?,?,?,?,?,?)",
                (doc_id, str(pdf), "hash-clairic-test", "w2.pdf", "application/pdf", "W-2", "processed"),
            )
        store_extracted_fields(doc_id=doc_id, section_id=None, data=res.data, confidences=res.field_confidence)
        with db() as con:
            rows = dict(
                (r[0], r[1])
                for r in con.execute("SELECT field_path, confidence FROM extracted_fields WHERE document_id=?", (doc_id,))
            )
        self.assertAlmostEqual(rows["wages"], 0.99)
        self.assertAlmostEqual(rows["federal_withheld"], 0.62)
        self.assertAlmostEqual(rows["box_codes.D"], 0.97)  # child of a coded list inherits the list confidence


if __name__ == "__main__":
    unittest.main()
