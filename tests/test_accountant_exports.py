"""Form 8949 CSV and TXF v042 export tests (synthetic transactions; no model, no network).

Run: PYTHONPATH=. venv/bin/python -P -m unittest tests.test_accountant_exports -v
Regenerate the TXF golden file (then review it by hand against the spec):
    TAXCLAW_UPDATE_GOLDEN=1 PYTHONPATH=. venv/bin/python -P -m unittest tests.test_accountant_exports
"""

from __future__ import annotations

import csv
import io
import os
import tempfile
import unittest
from datetime import date
from decimal import Decimal
from pathlib import Path

from src.accountant_exports import (
    SourceTransaction,
    parse_amount,
    parse_date,
    render_8949_csv,
    render_txf,
    rows_for,
    term_from_dates,
    to_8949_row,
)

GOLDEN_TXF = Path(__file__).parent / "golden" / "form8949_sample.txf.txt"


def B(**kw) -> SourceTransaction:
    base = dict(source_document_id="doc-b", source_form="consolidated-1099", payer="Example Brokerage LLC")
    base.update(kw)
    return SourceTransaction(**base)


def DA(**kw) -> SourceTransaction:
    base = dict(source_document_id="doc-da", source_form="1099-DA", payer="Example Digital Exchange")
    base.update(kw)
    return SourceTransaction(**base)


def synthetic() -> list[SourceTransaction]:
    return [
        B(description="10 SH ACME CORP", date_acquired="01/15/2025", date_sold="06/20/2025",
          proceeds="1,500.00", cost_basis="1,000.00", term="Short-term", basis_reported_to_irs=True, ref="lot 1"),
        B(description="25 SH GLOBEX INC", date_acquired="02/01/2023", date_sold="03/10/2025",
          proceeds="2,000.00", cost_basis="2,750.50", basis_reported_to_irs=True, ref="lot 2"),
        B(description="40 SH INITECH", date_acquired="08/01/2025", date_sold="09/15/2025",
          proceeds="800.00", cost_basis="1,000.00", wash_sale_disallowed="150.00", term="short",
          basis_reported_to_irs=True, ref="lot 3"),
        B(description="5 SH HOOLI", date_acquired="03/03/2015", date_sold="04/04/2025",
          proceeds="900.00", cost_basis="400.00", basis_reported_to_irs=False, ref="lot 4"),
        B(description="12 SH UMBRELLA CO", date_acquired="05/05/2025", date_sold="07/07/2025",
          proceeds="640.00", cost_basis=None, term="short", basis_reported_to_irs=False, ref="lot 5"),
        DA(description="0.5 ETH", date_acquired="01/10/2025", date_sold="03/12/2025",
           proceeds="1200.00", cost_basis="1000.00", term="short", basis_reported_to_irs=True, ref="transaction 1"),
        DA(description="0.01 BTC", date_acquired="01/01/2023", date_sold="02/02/2025",
           proceeds="950.00", cost_basis=None, basis_reported_to_irs=False, ref="transaction 2"),
    ]


class ParsingTests(unittest.TestCase):
    def test_amounts_and_rounding(self):
        self.assertEqual(parse_amount("1,234.565"), (Decimal("1234.57"), True))  # half-up to cents
        self.assertEqual(parse_amount("1,234.564"), (Decimal("1234.56"), True))
        self.assertEqual(parse_amount("$(250.00)"), (Decimal("-250.00"), True))
        self.assertEqual(parse_amount("250.00-"), (Decimal("-250.00"), True))
        self.assertEqual(parse_amount("-12"), (Decimal("-12.00"), True))
        self.assertEqual(parse_amount("$1,000"), (Decimal("1000.00"), True))
        self.assertEqual(parse_amount(None), (None, True))
        self.assertEqual(parse_amount("Not reported"), (None, True))
        self.assertEqual(parse_amount("abc"), (None, False))
        self.assertEqual(parse_amount(0.1), (Decimal("0.10"), True))

    def test_decimal_math_has_no_float_drift(self):
        r = to_8949_row(B(description="X", date_acquired="01/02/2025", date_sold="01/03/2025",
                          proceeds="0.30", cost_basis="0.10", wash_sale_disallowed="0.20", term="short",
                          basis_reported_to_irs=True))
        self.assertEqual(r.gain_or_loss, Decimal("0.40"))
        r = to_8949_row(B(description="X", date_acquired="01/02/2025", date_sold="01/03/2025",
                          proceeds="100.10", cost_basis="100.205", term="short", basis_reported_to_irs=True))
        self.assertEqual(r.cost_basis, Decimal("100.21"))
        self.assertEqual(r.gain_or_loss, Decimal("-0.11"))
        self.assertEqual(r.as_csv_dict()["h_gain_or_loss"], "-0.11")

    def test_dates(self):
        self.assertEqual(parse_date("3/5/2025"), (date(2025, 3, 5), True))
        self.assertEqual(parse_date("2025-03-05"), (date(2025, 3, 5), True))
        self.assertEqual(parse_date("Various"), ("VARIOUS", True))
        self.assertEqual(parse_date("sometime"), (None, False))

    def test_holding_period_boundary(self):
        # More than 1 year is long-term; exactly one year is still short-term.
        self.assertEqual(term_from_dates(date(2024, 3, 15), date(2025, 3, 15)), "short")
        self.assertEqual(term_from_dates(date(2024, 3, 15), date(2025, 3, 16)), "long")
        # Acquired Feb 29: the holding period starts Mar 1, so Feb 28 next year is still short.
        self.assertEqual(term_from_dates(date(2024, 2, 29), date(2025, 2, 28)), "short")
        self.assertEqual(term_from_dates(date(2024, 2, 29), date(2025, 3, 1)), "long")


class Form8949RowTests(unittest.TestCase):
    def setUp(self):
        self.rows = rows_for(synthetic())

    def test_short_term_gain_covered_is_box_a(self):
        r = self.rows[0]
        self.assertEqual((r.category, r.part, r.term), ("A", "I", "short"))
        self.assertEqual((r.proceeds, r.cost_basis, r.gain_or_loss), (Decimal("1500.00"), Decimal("1000.00"), Decimal("500.00")))
        self.assertEqual((r.adjustment_codes, r.adjustment_amount), ("", None))
        self.assertFalse(r.needs_review, r.review_reasons)

    def test_long_term_from_dates_is_box_d(self):
        r = self.rows[1]
        self.assertEqual((r.category, r.part, r.term), ("D", "II", "long"))
        self.assertEqual(r.gain_or_loss, Decimal("-750.50"))

    def test_wash_sale_code_w(self):
        r = self.rows[2]
        self.assertEqual((r.category, r.adjustment_codes, r.adjustment_amount), ("A", "W", Decimal("150.00")))
        self.assertEqual(r.gain_or_loss, Decimal("-50.00"))  # (d) - (e) + (g)

    def test_noncovered_long_term_is_box_e(self):
        r = self.rows[3]
        self.assertEqual((r.category, r.gain_or_loss), ("E", Decimal("500.00")))

    def test_missing_basis_is_blank_and_flagged(self):
        r = self.rows[4]
        self.assertEqual(r.category, "B")
        self.assertIsNone(r.cost_basis)
        self.assertIsNone(r.gain_or_loss)
        self.assertTrue(r.needs_review)
        self.assertIn("basis missing", r.review_reasons[0])

    def test_1099da_boxes(self):
        g, k = self.rows[5], self.rows[6]
        self.assertEqual((g.category, g.gain_or_loss), ("G", Decimal("200.00")))
        self.assertEqual((k.category, k.term, k.gain_or_loss), ("K", "long", None))
        self.assertIn("basis missing — common for 1099-DA", "; ".join(k.review_reasons))

    def test_unknown_basis_reporting_leaves_category_blank(self):
        r = to_8949_row(B(description="X", date_acquired="01/02/2025", date_sold="02/03/2025",
                          proceeds="10", cost_basis="5", term="short"))
        self.assertEqual(r.category, "")
        self.assertTrue(any("basis was reported" in x for x in r.review_reasons), r.review_reasons)
        self.assertEqual(r.gain_or_loss, Decimal("5.00"))  # arithmetic still fine

    def test_noncovered_flag_maps_to_not_reported(self):
        r = to_8949_row(DA(description="1 SOL", date_acquired="01/02/2025", date_sold="02/03/2025",
                           proceeds="10", cost_basis="5", noncovered=True))
        self.assertEqual(r.category, "H")

    def test_unknown_holding_period(self):
        r = to_8949_row(B(description="X", date_sold="02/03/2025", proceeds="10", cost_basis="5",
                          basis_reported_to_irs=True))
        self.assertEqual((r.category, r.term), ("", ""))
        self.assertTrue(any("holding period unknown" in x for x in r.review_reasons), r.review_reasons)

    def test_form_flag_beats_dates_but_conflict_is_flagged(self):
        r = to_8949_row(B(description="X", date_acquired="01/02/2020", date_sold="02/03/2025", proceeds="10",
                          cost_basis="5", term="SHORT TERM", basis_reported_to_irs=True))
        self.assertEqual(r.category, "A")
        self.assertTrue(any("dates give long-term" in x for x in r.review_reasons), r.review_reasons)

    def test_printed_box_letter(self):
        r = to_8949_row(B(description="X", date_sold="02/03/2025", proceeds="10", cost_basis="5", form_8949_box="Box E"))
        self.assertEqual((r.category, r.term), ("E", "long"))
        r = to_8949_row(B(description="X", date_sold="02/03/2025", proceeds="10", cost_basis="5", form_8949_box="G"))
        self.assertEqual(r.category, "")  # a 1099-B can't be box G
        self.assertTrue(r.needs_review)

    def test_printed_box_disagreeing_with_checkboxes_is_a_conflict(self):
        r = to_8949_row(B(description="X", date_acquired="02/01/2023", date_sold="03/10/2025", proceeds="10",
                          cost_basis="5", term="long", basis_reported_to_irs=True, form_8949_box="E"))
        self.assertEqual(r.category, "")
        self.assertTrue(r.conflicts and "box E" in r.conflicts[0], r.conflicts)
        res = render_txf([r], export_date=date(2026, 1, 15))
        self.assertEqual(res.records, 0)
        self.assertIn("contradict", res.warnings[0])

    def test_reported_and_noncovered_both_marked(self):
        r = to_8949_row(DA(description="0.01 BTC", date_acquired="01/01/2023", date_sold="02/02/2025",
                           proceeds="950", cost_basis=None, basis_reported_to_irs=True, noncovered=True))
        self.assertEqual(r.category, "J")  # the basis-reported checkbox decides (IRS rule) ...
        self.assertTrue(any("noncovered" in x for x in r.review_reasons), r.review_reasons)  # ... but it's flagged

    def test_market_discount_code_d_worksheet(self):
        r = to_8949_row(B(description="BOND", date_acquired="01/02/2020", date_sold="02/03/2025", proceeds="1000",
                          cost_basis="900", accrued_market_discount="30", basis_reported_to_irs=True))
        self.assertEqual((r.adjustment_codes, r.adjustment_amount, r.gain_or_loss), ("D", Decimal("-30.00"), Decimal("70.00")))
        # Discount larger than the gain: only the gain becomes ordinary income.
        r = to_8949_row(B(description="BOND", date_acquired="01/02/2020", date_sold="02/03/2025", proceeds="1000",
                          cost_basis="990", accrued_market_discount="30", basis_reported_to_irs=True))
        self.assertEqual((r.adjustment_amount, r.gain_or_loss), (Decimal("-10.00"), Decimal("0.00")))
        # Codes in alphabetical order, net amount in (g).
        r = to_8949_row(B(description="BOND", date_acquired="01/02/2020", date_sold="02/03/2025", proceeds="1000",
                          cost_basis="900", accrued_market_discount="30", wash_sale_disallowed="5",
                          basis_reported_to_irs=True))
        self.assertEqual((r.adjustment_codes, r.adjustment_amount), ("DW", Decimal("-25.00")))

    def test_statement_gain_loss_cross_check(self):
        # The model missed the wash sale: (h) is still computed from the form values, but flagged.
        r = to_8949_row(B(description="40 SH INITECH", date_acquired="08/01/2025", date_sold="09/15/2025",
                          proceeds="800.00", cost_basis="1,000.00", reported_gain_loss="-50.00", term="short",
                          basis_reported_to_irs=True))
        self.assertEqual(r.gain_or_loss, Decimal("-200.00"))
        self.assertTrue(any("differs from the statement's -50.00" in x for x in r.review_reasons), r.review_reasons)
        r = to_8949_row(B(description="10 SH ACME", date_acquired="01/15/2025", date_sold="06/20/2025",
                          proceeds="1500", cost_basis="1000", reported_gain_loss="500.00", term="short",
                          basis_reported_to_irs=True))
        self.assertFalse(r.needs_review, r.review_reasons)

    def test_csv_columns_and_notice(self):
        text = render_8949_csv(self.rows, generated="2026-01-15 09:00:00")
        self.assertTrue(text.startswith("# TaxClaw Data Export | Generated: 2026-01-15 09:00:00"))
        self.assertIn("Not tax advice", text)
        body = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
        rows = list(csv.DictReader(io.StringIO(body)))
        self.assertEqual(len(rows), 7)
        self.assertEqual([r["category"] for r in rows], ["A", "A", "B", "G", "D", "E", "K"])
        for col in ("a_description", "b_date_acquired", "c_date_sold", "d_proceeds", "e_cost_basis",
                    "f_adjustment_codes", "g_adjustment_amount", "h_gain_or_loss", "source_document_id",
                    "payer", "confidence", "needs_review"):
            self.assertIn(col, rows[0])
        wash = next(r for r in rows if r["f_adjustment_codes"] == "W")
        self.assertEqual((wash["g_adjustment_amount"], wash["h_gain_or_loss"]), ("150.00", "-50.00"))
        self.assertEqual([r["needs_review"] for r in rows].count("true"), 2)


class TxfTests(unittest.TestCase):
    def test_golden_file(self):
        res = render_txf(rows_for(synthetic()), export_date=date(2026, 1, 15), app="TaxClaw test")
        if os.environ.get("TAXCLAW_UPDATE_GOLDEN"):
            GOLDEN_TXF.parent.mkdir(exist_ok=True)
            GOLDEN_TXF.write_bytes(res.content.encode("ascii"))
        self.assertEqual(res.content.encode("ascii"), GOLDEN_TXF.read_bytes())
        self.assertEqual(res.records, 4)
        skipped = [w for w in res.warnings if w.startswith("skipped")]
        self.assertEqual(len(skipped), 3, res.warnings)
        self.assertTrue(any("UMBRELLA" in w and "basis missing" in w for w in skipped))
        self.assertEqual(sum("TXF v042 has no reference number for boxes G-L" in w for w in skipped), 2)

    def test_structure(self):
        res = render_txf(rows_for(synthetic()), export_date=date(2026, 1, 15))
        lines = res.content.split("\r\n")
        self.assertEqual(lines[:4], ["V042", lines[1], "D01/15/2026", "^"])
        self.assertTrue(lines[1].startswith("ATaxClaw "))
        self.assertEqual(lines[-1], "")  # file ends with CR LF
        self.assertNotIn("\n", res.content.replace("\r\n", ""))
        recs = "\r\n".join(lines[4:]).strip().split("\r\n^")
        refs = [r.strip().split("\r\n")[1] for r in recs if r.strip()]
        self.assertEqual(refs, ["N321", "N321", "N323", "N713"])
        res.content.encode("ascii")  # ASCII only

    def test_codes_txf_cannot_express_are_skipped(self):
        r = to_8949_row(B(description="BOND", date_acquired="01/02/2020", date_sold="02/03/2025", proceeds="1000",
                          cost_basis="900", accrued_market_discount="30", basis_reported_to_irs=True))
        res = render_txf([r], export_date=date(2026, 1, 15))
        self.assertEqual(res.records, 0)
        self.assertIn("can't be expressed in TXF", res.warnings[0])

    def test_various_acquired(self):
        r = to_8949_row(B(description="100 SH VARIED", date_acquired="VARIOUS", date_sold="02/03/2025",
                          proceeds="1000", cost_basis="900", term="long", basis_reported_to_irs=True))
        res = render_txf([r], export_date=date(2026, 1, 15))
        self.assertEqual(res.records, 1)
        self.assertIn("\r\nDVarious\r\n", res.content)


class DatabaseExportTests(unittest.TestCase):
    """load_transactions over a temp DB: 1099-B lots, consolidated lots, 1099-DA fields, flat 1099-B fallback."""

    def setUp(self):
        self._home = os.environ.get("HOME")
        self._tmp = tempfile.mkdtemp(prefix="taxclaw-wpg-test-")
        os.environ["HOME"] = self._tmp

    def tearDown(self):
        if self._home is not None:
            os.environ["HOME"] = self._home

    def _doc(self, doc_type: str, name: str, *, needs_review: bool = False) -> str:
        import pymupdf

        from src.config import load_config
        from src.store import create_document_record, ingest_file, mark_processed

        cfg = load_config()
        p = Path(self._tmp) / f"{name}.pdf"
        d = pymupdf.open()
        d.new_page().insert_text((50, 72), f"synthetic {name}")
        d.save(p)
        dest, h, orig, mime = ingest_file(str(p), cfg)
        doc_id = create_document_record(cfg=cfg, file_path=dest, file_hash=h, original_filename=orig, mime_type=mime,
                                        filer="t", tax_year=2025, doc_type=doc_type, page_count=1,
                                        classification_confidence=0.9)
        mark_processed(doc_id=doc_id, overall_confidence=0.85, needs_review=needs_review)
        return doc_id

    def test_end_to_end_from_db(self):
        from src.accountant_exports import build_8949, export_txf
        from src.db import init_db
        from src.store import store_1099b_lots, store_1099da_transactions, store_extracted_fields, store_raw_extraction

        init_db()
        cons = self._doc("consolidated-1099", "cons")
        store_raw_extraction(doc_id=cons, form_type="consolidated-1099", data={"payer_name": "Example Brokerage"})
        store_extracted_fields(doc_id=cons, section_id=None, data={"payer_name": "Example Brokerage"})
        store_1099b_lots(doc_id=cons, lots=[
            {"description": "10 SH ACME", "date_acquired": "01/15/2025", "date_sold": "06/20/2025", "proceeds": "1500",
             "cost_basis": "1000", "term": "short", "basis_reported_to_irs": True, "page": 2},
            {"description": "3 SH NOBASIS", "date_acquired": "01/15/2024", "date_sold": "06/20/2025", "proceeds": "300",
             "cost_basis": None, "term": "long", "basis_reported_to_irs": False, "page": 2},
        ])

        da = self._doc("1099-DA", "da", needs_review=True)
        ext = {"header": {"payer_name": "Example Digital Exchange"}, "transactions": [
            {"asset_name": "Ether", "units": "0.5", "date_acquired": "01/10/2025", "date_sold": "03/12/2025",
             "proceeds": "1200.00", "cost_basis": "1000.00", "basis_reported_to_irs": True, "gain_loss_term": "short"},
        ], "is_multi_transaction": False}
        sid = store_raw_extraction(doc_id=da, form_type="1099-DA", data=ext)
        store_extracted_fields(doc_id=da, section_id=sid, data=ext)
        store_1099da_transactions(doc_id=da, extraction=ext)
        # A UI correction lives in extracted_fields and must win over the raw table.
        from src.db import db
        with db() as con:
            con.execute("UPDATE extracted_fields SET field_value='1250.00' WHERE document_id=? AND field_path='transactions[0].proceeds'", (da,))

        flat = self._doc("1099-B", "flat")
        fields = {"payer_name": "Solo Broker", "description": "7 SH SOLO", "proceeds": "70", "cost_basis": "50", "term": "Long-term"}
        store_extracted_fields(doc_id=flat, section_id=None, data=fields)

        w2 = self._doc("W-2", "w2")

        res = build_8949(None, generated="2026-01-15 09:00:00")
        self.assertEqual(res.rows, 4)
        body = "\n".join(line for line in res.content.splitlines() if not line.startswith("#"))
        rows = {r["a_description"]: r for r in csv.DictReader(io.StringIO(body))}
        self.assertEqual(rows["10 SH ACME"]["category"], "A")
        self.assertEqual(rows["10 SH ACME"]["payer"], "Example Brokerage")
        self.assertEqual(rows["3 SH NOBASIS"]["category"], "E")
        self.assertEqual(rows["3 SH NOBASIS"]["h_gain_or_loss"], "")
        self.assertEqual(rows["0.5 Ether"]["category"], "G")
        self.assertEqual(rows["0.5 Ether"]["d_proceeds"], "1250.00")
        self.assertIn("flagged for review", rows["0.5 Ether"]["review_reasons"])
        self.assertEqual(rows["7 SH SOLO"]["term"], "long")
        self.assertEqual(rows["7 SH SOLO"]["category"], "")  # flat 1099-B: no dates, no basis-reported flag
        self.assertEqual(rows["10 SH ACME"]["confidence"], "0.85")

        one = build_8949([cons, w2])
        self.assertEqual(one.rows, 2)
        self.assertTrue(any("W-2" in w for w in one.warnings), one.warnings)
        with self.assertRaises(ValueError):
            build_8949(["no-such-doc"])

        txf = export_txf(None, export_date=date(2026, 1, 15))
        self.assertEqual(txf.records, 1)  # ACME only: NOBASIS lacks basis, DA has no TXF ref, SOLO lacks a box
        self.assertIn("N321", txf.content)
        self.assertEqual(sum(w.startswith("skipped") for w in txf.warnings), 3, txf.warnings)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
