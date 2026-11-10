"""1.1.0 fixes: retry/--force/delete, max_pages, PDF validation, classifier tie-break,
redact_identifiers, data-dir permissions, model reply kept out of notes, web upload off the event loop.

No network, no model: classification/extraction are mocked, config and data live in a temp dir.

Run: PYTHONPATH=. venv/bin/python -P -m unittest tests.test_ingest_recovery -v
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import stat
import unittest
from pathlib import Path
from unittest import mock

import pymupdf

from src import cli, config, pipeline
from src.backends import ExtractionResult
from src.db import db
from tests.test_doctor import Isolated

ROOT = Path(__file__).resolve().parents[1]

W2 = {
    "employer_name": "Synthetic LLC",
    "employer_ein": "12-3456789",
    "employee_name": "Pat Example",
    "employee_ssn": "123-45-6789",
    "account_number": "ACCT-0099887766",
    "wages": "1000.00",
    "reinvested_dividends": "12.34",
}


class Base(Isolated):
    def setUp(self):
        super().setUp()
        self.calls = 0

    def cfg(self):
        return config.load_config()

    def pdf(self, name: str, text: str = "Form W-2 synthetic", pages: int = 1) -> str:
        p = self.tmp / name
        d = pymupdf.open()
        for i in range(pages):
            d.new_page().insert_text((50, 72), f"{text} page {i + 1}", fontsize=10)
        d.save(p)
        return str(p)

    def _extract_ok(self, path, doc_type, cfg):
        self.calls += 1
        return ExtractionResult(data=dict(W2), method="mock")

    def run_ingest(self, path: str, extract=None, **kw):
        with mock.patch.object(pipeline, "ensure_backend_ready"), \
             mock.patch.object(pipeline, "classify_document", return_value={"doc_type": "W-2", "confidence": 0.95}), \
             mock.patch.object(pipeline, "extract_document_with_meta", side_effect=extract or self._extract_ok), \
             mock.patch.object(pipeline, "extract_and_store_1099b_lots", return_value=(None, None)):
            return pipeline.ingest_path(path, self.cfg(), **kw)

    def row(self, doc_id: str) -> dict:
        with db() as con:
            r = con.execute("SELECT status, needs_review, notes FROM documents WHERE id=?", (doc_id,)).fetchone()
            n = con.execute("SELECT COUNT(*) FROM form_extractions WHERE document_id=?", (doc_id,)).fetchone()[0]
            f = con.execute("SELECT COUNT(*) FROM extracted_fields WHERE document_id=?", (doc_id,)).fetchone()[0]
        return {"status": r[0], "needs_review": r[1], "notes": r[2], "extractions": n, "fields": f} if r else {}

    def doc_count(self) -> int:
        with db() as con:
            return con.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def stored_files(self) -> list[str]:
        d = self.data_dir / "files"
        return sorted(p.name for p in d.iterdir()) if d.exists() else []


# ---------------------------------------------------------------------------
# P0-1: an interrupted or failed ingest is retried, --force, delete
# ---------------------------------------------------------------------------


class RetryTest(Base):
    def test_killed_mid_extraction_is_retried_on_the_same_document(self):
        path = self.pdf("killed.pdf")

        def killed(*a):
            raise KeyboardInterrupt  # stands in for the process dying mid-extraction

        with self.assertRaises(KeyboardInterrupt):
            self.run_ingest(path, extract=killed)
        with db() as con:
            doc_id = con.execute("SELECT id FROM documents").fetchone()[0]
        self.assertEqual(self.row(doc_id)["status"], "processing")

        out = self.run_ingest(path)
        self.assertEqual((out["document_id"], out["duplicate"], out["retried"]), (doc_id, False, True))
        self.assertEqual(self.calls, 1)
        r = self.row(doc_id)
        self.assertEqual((r["status"], r["extractions"]), ("processed", 1))
        self.assertEqual(self.doc_count(), 1)

    def test_failed_extraction_is_retried_and_notes_omit_the_model_reply(self):
        path = self.pdf("failed.pdf")

        def bad_json(*a):
            raise ValueError("model response was not valid JSON (Expecting value); response began: 'SSN 123-45-6789 ...'")

        with self.assertRaises(pipeline.IngestError) as cm:
            self.run_ingest(path, extract=bad_json)
        self.assertEqual((cm.exception.stage, cm.exception.exit_code), ("extract", 1))
        doc_id = cm.exception.document_id
        r = self.row(doc_id)
        self.assertEqual((r["status"], r["extractions"]), ("needs_review", 0))
        self.assertNotIn("123-45-6789", r["notes"])
        self.assertNotIn("response began", r["notes"])
        self.assertIn("not valid JSON", r["notes"])

        out = self.run_ingest(path)
        self.assertEqual((out["document_id"], out["duplicate"], out["retried"]), (doc_id, False, True))
        self.assertEqual(self.row(doc_id)["extractions"], 1)

    def test_error_status_is_retried(self):
        path = self.pdf("error.pdf")
        doc_id = self.run_ingest(path)["document_id"]
        with db() as con:
            con.execute("UPDATE documents SET status='error' WHERE id=?", (doc_id,))
        out = self.run_ingest(path)
        self.assertTrue(out["retried"])
        self.assertEqual(self.row(doc_id)["status"], "processed")

    def test_finished_document_is_a_duplicate_unless_forced(self):
        path = self.pdf("done.pdf")
        first = self.run_ingest(path, filer="pat")
        self.assertEqual((first["duplicate"], first["retried"]), (False, False))
        again = self.run_ingest(path)
        self.assertEqual((again["document_id"], again["duplicate"], again["retried"]), (first["document_id"], True, False))
        self.assertEqual(self.calls, 1)

        forced = self.run_ingest(path, force=True)
        self.assertEqual((forced["document_id"], forced["duplicate"], forced["retried"]), (first["document_id"], False, True))
        self.assertEqual(self.calls, 2)
        r = self.row(first["document_id"])
        self.assertEqual((r["extractions"], r["status"]), (1, "processed"))  # previous results replaced, not stacked
        self.assertEqual(forced["filer"], "pat")  # metadata kept when not given again

    def test_cli_force_flag(self):
        path = self.pdf("cli.pdf")
        self.run_ingest(path)
        with mock.patch.object(pipeline, "ensure_backend_ready"), \
             mock.patch.object(pipeline, "classify_document", return_value={"doc_type": "W-2", "confidence": 0.95}), \
             mock.patch.object(pipeline, "extract_document_with_meta", side_effect=self._extract_ok), \
             mock.patch.object(pipeline, "extract_and_store_1099b_lots", return_value=(None, None)):
            rc, out, _ = self.run_cli("ingest", path, "--json")
            self.assertEqual((rc, json.loads(out)["duplicate"]), (0, True))
            rc, out, _ = self.run_cli("ingest", path, "--json", "--force")
        data = json.loads(out)
        self.assertEqual((rc, data["duplicate"], data["retried"]), (0, False, True))

    def test_mcp_ingest_has_force(self):
        from src import mcp_server

        path = self.pdf("mcp.pdf")
        self.run_ingest(path)
        with mock.patch.object(pipeline, "ensure_backend_ready"), \
             mock.patch.object(pipeline, "classify_document", return_value={"doc_type": "W-2", "confidence": 0.95}), \
             mock.patch.object(pipeline, "extract_document_with_meta", side_effect=self._extract_ok), \
             mock.patch.object(pipeline, "extract_and_store_1099b_lots", return_value=(None, None)):
            out = mcp_server.ingest_document(path, force=True)
        self.assertTrue(out["retried"])


class DeleteTest(Base):
    def test_cli_delete_removes_row_children_and_stored_copy_but_not_the_original(self):
        path = self.pdf("del.pdf")
        doc_id = self.run_ingest(path)["document_id"]
        self.assertEqual(len(self.stored_files()), 1)
        rc, out, _ = self.run_cli("delete", doc_id, "--json")
        self.assertEqual((rc, json.loads(out)["deleted"]), (0, True))
        self.assertEqual(self.doc_count(), 0)
        with db() as con:
            for table in ("extracted_fields", "form_extractions", "form_sections"):
                self.assertEqual(con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0], 0, table)
        self.assertEqual(self.stored_files(), [])
        self.assertTrue(os.path.exists(path))
        # and the file can be ingested fresh afterwards
        self.assertFalse(self.run_ingest(path)["duplicate"])

    def test_cli_delete_unknown_id_exits_2(self):
        rc, _, err = self.run_cli("delete", "no-such-id")
        self.assertEqual(rc, 2)
        self.assertIn("document not found", err)

    def test_mcp_delete_document(self):
        from mcp.server.mcpserver.exceptions import ToolError

        from src import mcp_server

        doc_id = self.run_ingest(self.pdf("mcpdel.pdf"))["document_id"]
        self.assertEqual(mcp_server.delete_document(doc_id), {"deleted": True, "document_id": doc_id})
        with self.assertRaises(ToolError):
            mcp_server.delete_document(doc_id)


# ---------------------------------------------------------------------------
# P0-2 / P1-2: max_pages, unreadable and password-protected PDFs
# ---------------------------------------------------------------------------


class ValidateTest(Base):
    def test_too_many_pages_is_an_invalid_file_with_the_estimate(self):
        path = self.pdf("long.pdf", pages=41)
        with self.assertRaises(pipeline.IngestError) as cm:
            self.run_ingest(path)
        e = cm.exception
        self.assertEqual((e.stage, e.exit_code), ("validate", 2))
        self.assertIn("41 pages", str(e))
        self.assertIn("max_pages", str(e))
        self.assertIn("15-100 s per page", str(e))
        self.assertIn("41 page(s)", str(e))
        self.assertEqual((self.doc_count(), self.stored_files()), (0, []))
        rc, out, _ = self.run_cli("ingest", path, "--json")
        self.assertEqual((rc, json.loads(out)["stage"]), (2, "validate"))

    def test_max_pages_is_configurable_and_zero_means_no_limit(self):
        path = self.pdf("long2.pdf", pages=41)
        self.write_config({"max_pages": 0})
        self.assertFalse(self.run_ingest(path)["duplicate"])
        self.write_config({"max_pages": 3})
        with self.assertRaises(pipeline.IngestError):
            self.run_ingest(self.pdf("four.pdf", pages=4))

    def test_corrupt_pdf_is_refused_before_anything_is_copied(self):
        p = self.tmp / "corrupt.pdf"
        p.write_bytes(b"%PDF-1.4\n" + os.urandom(3000))
        with self.assertRaises(pipeline.IngestError) as cm:
            self.run_ingest(str(p))
        self.assertEqual((cm.exception.stage, cm.exception.exit_code), ("validate", 2))
        self.assertIn("not a readable PDF", str(cm.exception))
        self.assertEqual((self.doc_count(), self.stored_files()), (0, []))

    def test_password_protected_pdf_is_refused(self):
        p = self.tmp / "locked.pdf"
        d = pymupdf.open()
        d.new_page().insert_text((50, 72), "Form W-2", fontsize=10)
        d.save(p, encryption=pymupdf.PDF_ENCRYPT_AES_256, owner_pw="owner-pw", user_pw="user-pw")
        with self.assertRaises(pipeline.IngestError) as cm:
            self.run_ingest(str(p))
        self.assertEqual(cm.exception.exit_code, 2)
        self.assertIn("password-protected PDF: remove the password first", str(cm.exception))
        self.assertEqual(self.stored_files(), [])

    def test_mcp_ingest_description_states_time_per_page_times_pages(self):
        import asyncio

        from src import mcp_server

        tool = next(t for t in asyncio.run(mcp_server.mcp.list_tools()) if t.name == "ingest_document")
        self.assertIn("per page times pages", tool.description)
        self.assertIn("15-100 s per page", tool.description)
        self.assertIn("max_pages", tool.description)
        skill = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("15-100 s per page", skill)
        self.assertNotIn("30-120", (ROOT / "src" / "mcp_server.py").read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# P1-1: text classification (synthetic text in the IRS 1099 PDF layout; no IRS files in the repo)
# ---------------------------------------------------------------------------

# Page 1 of every IRS 1099 PDF is an "Attention" page that names Form 1099-NEC several times;
# the form's own name and OMB number follow on the next page.
ATTENTION = (
    "Attention: Copy A of this form is provided for informational purposes only. ... "
    "To order official IRS information returns, which include a scannable Copy A for filing ... "
    "Form 1099-NEC filers: see Form 1099-NEC instructions. Due dates for Form 1099-NEC differ.\n"
)


def irs_like(form: str, omb: str, title: str) -> str:
    copy_a = f"{form}\n{title}\nOMB No. {omb}\nCopy A For Internal Revenue Service Center\nForm {form} (Rev. 1-2025)\n"
    return ATTENTION + copy_a


class ClassifyTextTest(unittest.TestCase):
    def test_irs_pattern_1099_r_g_k_are_not_nec(self):
        from src.classify import classify_text

        cases = {
            "1099-R": irs_like("1099-R", "1545-0119", "Distributions From Pensions, Annuities, Retirement or Profit-Sharing Plans"),
            "1099-G": irs_like("1099-G", "1545-0120", "Certain Government Payments"),
            "1099-K": irs_like("1099-K", "1545-2205", "Payment Card and Third Party Network Transactions"),
            "1099-DA": irs_like("1099-DA", "1545-2330", "Digital Asset Proceeds From Broker Transactions"),
            "1099-MISC": irs_like("1099-MISC", "1545-0115", "Miscellaneous Information"),
            "1099-NEC": irs_like("1099-NEC", "1545-0116", "Nonemployee Compensation"),
        }
        for want, text in cases.items():
            got = classify_text(text)
            self.assertIsNotNone(got, want)
            self.assertEqual(got["doc_type"], want, want)

    def test_form_1040_mention_only_counts_alone(self):
        from src.classify import classify_text

        instr = "Instructions for Recipient. Report this amount on Form 1040 or 1040-SR. Form 1099-R box 1."
        self.assertEqual(classify_text(instr)["doc_type"], "1099-R")
        self.assertEqual(classify_text("Form 1040 U.S. Individual Income Tax Return")["doc_type"], "1040")

    def test_tie_goes_to_vision_not_list_order(self):
        from src import classify

        self.assertIsNone(classify.classify_text("Form 1099-NEC and Form 1099-R"))
        tmp = Path(self.id().replace(".", "_") + ".pdf")
        path = Path(os.environ.get("TMPDIR", "/tmp")) / tmp
        d = pymupdf.open()
        d.new_page().insert_text((50, 72), "Form 1099-NEC and Form 1099-R", fontsize=10)
        d.save(path)
        backend = mock.Mock()
        backend.classify_image.return_value = {"doc_type": "1099-R", "confidence": 0.85, "method": "vision"}
        try:
            with mock.patch.object(classify, "get_backend", return_value=backend):
                out = classify.classify_document(str(path), config.Config())
        finally:
            path.unlink(missing_ok=True)
        self.assertEqual((out["doc_type"], out["method"]), ("1099-R", "vision"))
        backend.classify_image.assert_called_once()


# ---------------------------------------------------------------------------
# P1-3: identifiers masked in what the MCP tools return
# ---------------------------------------------------------------------------


class RedactTest(Base):
    def test_mask_and_key_rules(self):
        from src.redact import is_identifier_key, mask_value

        self.assertEqual(mask_value("123-45-6789"), "***-**-6789")
        self.assertEqual(mask_value("ACCT-0099887766"), "****-******7766")
        self.assertEqual(mask_value(None), None)
        for k in ("employee_ssn", "payer_tin", "header.recipient_tin", "employer_ein", "partnership_ein", "account_number", "AccountNumber"):
            self.assertTrue(is_identifier_key(k), k)
        for k in ("reinvested_dividends", "accounting_method", "wages", "state_id", "distribution_code", "payer_name"):
            self.assertFalse(is_identifier_key(k), k)

    def test_get_document_masks_by_default(self):
        from src import mcp_server

        doc_id = self.run_ingest(self.pdf("r.pdf"))["document_id"]
        got = mcp_server.get_document(doc_id)
        fields = {f["field_path"]: f["field_value"] for f in got["fields"]}
        self.assertEqual(fields["employee_ssn"], "***-**-6789")
        self.assertEqual(fields["employer_ein"], "**-***6789")
        self.assertEqual(fields["account_number"], "****-******7766")
        self.assertEqual(fields["reinvested_dividends"], "12.34")
        self.assertEqual(got["extraction"]["employee_ssn"], "***-**-6789")
        self.assertTrue(got["identifiers_redacted"])
        self.assertNotIn("123-45-6789", json.dumps(got))

        full = mcp_server.get_document(doc_id, redact_identifiers=False)
        self.assertIn("123-45-6789", json.dumps(full))
        self.assertFalse(full["identifiers_redacted"])

    def test_exports_mask_by_default_and_cli_is_unchanged(self):
        from src import mcp_server

        doc_id = self.run_ingest(self.pdf("e.pdf"))["document_id"]
        for fmt in ("json", "wide_csv", "long_csv"):
            for scope in ({"all": True}, {"document_id": doc_id}):
                out = mcp_server.export_documents(format=fmt, **scope)
                self.assertNotIn("123-45-6789", out["content"], (fmt, scope))
                self.assertNotIn("0099887766", out["content"], (fmt, scope))
                self.assertIn("6789", out["content"], (fmt, scope))
                self.assertIn("1000.00", out["content"], (fmt, scope))
                self.assertTrue(out["content"].startswith("{" if fmt == "json" else "# TaxClaw Data Export"), fmt)
                full = mcp_server.export_documents(format=fmt, redact_identifiers=False, **scope)
                self.assertIn("123-45-6789", full["content"], (fmt, scope))
        wide = mcp_server.export_documents(format="wide_csv", document_id=doc_id)["content"]
        rows = list(csv.DictReader(io.StringIO("".join(l for l in wide.splitlines(True) if not l.startswith("#")))))
        self.assertEqual(rows[0]["employee_ssn"], "***-**-6789")
        rc, out, _ = self.run_cli("export", "--id", doc_id, "--format", "json")
        self.assertEqual(rc, 0)
        self.assertIn("123-45-6789", out)

    def test_list_documents_accepts_the_flag(self):
        from src import mcp_server

        self.run_ingest(self.pdf("l.pdf"))
        self.assertEqual(mcp_server.list_documents()["count"], 1)
        self.assertEqual(mcp_server.list_documents(redact_identifiers=False)["count"], 1)


# ---------------------------------------------------------------------------
# P2-3 permissions, P1-4 hosted text, P1-5 web UI
# ---------------------------------------------------------------------------


class PermissionsTest(Base):
    def test_data_dir_files_and_db_are_owner_only(self):
        old = os.umask(0o022)
        try:
            self.run_ingest(self.pdf("p.pdf"))
        finally:
            os.umask(old)
        mode = lambda p: stat.S_IMODE(p.stat().st_mode)  # noqa: E731
        self.assertEqual(mode(self.data_dir), 0o700)
        self.assertEqual(mode(self.data_dir / "files"), 0o700)
        self.assertEqual(mode(self.data_dir / "tax.db"), 0o600)


class NoComingSoonTest(unittest.TestCase):
    def test_no_coming_soon_outside_changelog_history(self):
        hits = []
        for p in ROOT.rglob("*"):
            if p.suffix not in (".py", ".md", ".yaml", ".sh", ".html") or "venv" in p.parts or p.name == "CHANGELOG.md":
                continue
            if "coming" " soon" in p.read_text(encoding="utf-8", errors="ignore").lower():
                hits.append(str(p.relative_to(ROOT)))
        self.assertEqual(hits, [])


class WebTest(Base):
    def test_no_reload_in_serve_paths(self):
        self.assertNotIn("--reload", (ROOT / "start.sh").read_text(encoding="utf-8"))
        self.assertNotIn("reload=True", (ROOT / "src" / "cli.py").read_text(encoding="utf-8"))

    def test_upload_runs_off_the_event_loop_and_retries_a_stuck_record(self):
        from fastapi.testclient import TestClient

        from src import main

        path = self.pdf("web.pdf")

        def killed(*a):
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.run_ingest(path, extract=killed)
        with db() as con:
            doc_id = con.execute("SELECT id FROM documents").fetchone()[0]

        seen = []
        real = main.run_in_threadpool

        async def spy(fn, *a, **k):
            seen.append(fn.__name__)
            return await real(fn, *a, **k)

        client = TestClient(main.app, base_url="http://127.0.0.1:8421")
        with mock.patch.object(main, "cfg", self.cfg()), \
             mock.patch.object(main, "run_in_threadpool", spy), \
             mock.patch.object(main, "ensure_backend_ready"), \
             mock.patch.object(main, "classify_document", return_value={"doc_type": "W-2", "confidence": 0.95}), \
             mock.patch.object(main, "extract_document_with_meta", side_effect=self._extract_ok), \
             mock.patch.object(main, "extract_and_store_1099b_lots", return_value=(None, None)):
            page = client.get("/upload").text
            tok = re.search(r'name="csrf_token" value="([^"]+)"', page).group(1)
            with open(path, "rb") as fh:
                r = client.post("/upload", data={"csrf_token": tok}, files={"file": ("web.pdf", fh, "application/pdf")}, follow_redirects=False)
        self.assertEqual(r.status_code, 303)
        self.assertEqual(r.headers["location"], f"/doc/{doc_id}")
        self.assertEqual(seen, ["_ingest_upload"])
        self.assertEqual(self.row(doc_id)["status"], "processed")
        self.assertEqual(self.doc_count(), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
