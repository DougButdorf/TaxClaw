"""Separate WP-F changed-form corpus; the original fixture generator is immutable.

The answer key never enters PDF text, metadata, or image payloads. Human labels
and invented values are rendered locally with bundled PDF fonts. Scan parameters
and dependency versions are recorded because byte stability is version-local.
Run with ``python -m benchmarks.taxclaw_accuracy.followup_fixtures OUTPUT_DIR``.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pymupdf as fitz
from PIL import Image, ImageFilter, __version__ as pillow_version

from src.extract import schema_for
from .fixtures import Field, RECIPIENT, SSN, TIN, _set_path, f, identity

CORPUS_ID = "wp_f_changed_forms_v1"
SCAN_PARAMETERS = {
    "dpi": 100, "colorspace": "grayscale", "rotation_degrees": 0.35,
    "rotation_resampling": "bicubic", "rotation_expand": False,
    "rotation_fill": 255, "gaussian_blur_radius_pixels": 0.25,
    "jpeg_quality": 78, "jpeg_optimize": False, "jpeg_progressive": False,
    "randomness": "none (no random operations)",
    "pdf_text_layer": False,
}
ADDRESS = "42 Fictional Quay, Example City, NY 00000"


def _specs() -> list[tuple[str, str, list[list[Field]]]]:
    r = identity(account=True) + [
        f("gross_distribution", "1 Gross distribution", "18500.00"),
        f("taxable_amount", "2a Taxable amount", "17500.00"),
        f("taxable_amount_not_determined", "2b Taxable amount not determined", False, "boolean"),
        f("total_distribution", "2b Total distribution", False, "boolean"),
        f("capital_gain", "3 Capital gain (included in box 2a)", None),
        f("federal_withheld", "4 Federal income tax withheld", "1850.00"),
        f("employee_contributions", "5 Employee / designated Roth contributions or insurance premiums", "1000.00"),
        f("net_unrealized_appreciation", "6 Net unrealized appreciation in employer securities", "123.47"),
        f("distribution_codes", "7 Distribution code(s)", "7Q", "identifier"),
        f("ira_sep_simple", "7 IRA/SEP/SIMPLE", True, "boolean"),
        f("other_amount", "8 Other amount", "0.00"),
        f("other_percent", "8 Other percentage", "12.375%", "percent"),
        f("percent_of_total_distribution", "9a Your percentage of total distribution", "33.3333%", "percent"),
        f("total_employee_contributions", "9b Total employee contributions", "1456.78"),
        f("amount_allocable_to_irr", "10 Amount allocable to IRR within 5 years", "0.00"),
        f("first_year_designated_roth", "11 First year of designated Roth contribution", "2017", "text"),
        # A missing checkbox is different from an explicitly drawn empty box.
        f("fatca_filing_requirement", "12 FATCA filing requirement", None, "boolean"),
        f("date_of_payment", "13 Date of payment", "2025-10-09", "date"),
        f("state_withheld", "14 State tax withheld", "0.00"),
        f("state_payer_number", "15 State / Payer's state number", "NY QO-001908", "identifier"),
        f("state_distribution", "16 State distribution", "17500.00"),
        f("local_withheld", "17 Local tax withheld", None),
        f("locality_name", "18 Name of locality", "QO Example District", "text"),
        f("local_distribution", "19 Local distribution", "0.00"),
    ]
    g = identity(account=True) + [
        f("unemployment_compensation", "1 Unemployment compensation", "8642.19"),
        f("state_local_tax_refunds", "2 State or local income tax refunds, credits, or offsets", "1098.76"),
        f("box2_tax_year", "3 Box 2 amount is for tax year", "2024", "text"),
        f("federal_withheld", "4 Federal income tax withheld", "0.00"),
        f("rtaa_payments", "5 RTAA payments", None),
        f("taxable_grants", "6 Taxable grants", "2190.08"),
        f("agriculture_payments", "7 Agriculture payments", None),
        f("trade_or_business_income", "8 Box 2 is trade or business income", False, "boolean"),
        f("market_gain", "9 Market gain", "0.00"),
        f("state", "10a State", "NY", "text"),
        f("state_id", "10b State identification number", "000QO1908", "identifier"),
        f("state_withheld", "11 State income tax withheld", "432.10"),
    ]
    k = identity(account=True) + [
        f("gross_amount", "1a Gross amount of payment card / third party network transactions", "78123.45"),
        f("card_not_present", "1b Card Not Present transactions", "65001.09"),
        f("merchant_category_code", "2 Merchant category code", "0190", "identifier"),
        f("number_of_transactions", "3 Number of payment transactions", "1908", "number"),
        f("federal_withheld", "4 Federal income tax withheld", "0.00"),
    ]
    monthly = ["0.00", "1111.11", "2222.22", "3333.33", "4444.44", "5555.55",
               "6666.66", "7777.77", "8888.88", "9999.99", "10101.01", "18022.49"]
    for letter, month, value in zip("abcdefghijkl", (
            "january", "february", "march", "april", "may", "june", "july",
            "august", "september", "october", "november", "december"), monthly):
        k.append(f(month, f"5{letter} {month.title()}", value))
    k += [f("state", "6 State", "NY", "text"),
          f("state_id", "7 State identification number", "QO-0001908", "identifier"),
          f("state_withheld", "8 State income tax withheld", None)]
    # Filer/payee labels, not payer/recipient labels, exercise the actual K prompt.
    k = [Field(x.path, x.label.replace("PAYER'S", "FILER'S").replace("RECIPIENT'S", "PAYEE'S"), x.value, x.kind) for x in k]
    k1_first = [
        f("tax_year", "For calendar year", "2025", "text"),
        f("partnership_name", "B Partnership's name", "Example Lantern Partners LP", "text"),
        f("partnership_ein", "A Partnership's employer identification number", TIN, "identifier"),
        f("partner_name", "F Partner's name", RECIPIENT, "text"),
        f("partner_ssn", "E Partner's SSN or TIN", SSN, "identifier"),
        f("partner_type", "I1 What type of entity is this partner?", "Individual", "text"),
        f("profit_sharing_pct", "J Partner's share of profit - ending", "25.00%", "percent"),
        f("loss_sharing_pct", "J Partner's share of loss - ending", "25.00%", "percent"),
        f("capital_sharing_pct", "J Partner's share of capital - ending", "25.00%", "percent"),
        f("ordinary_income", "1 Ordinary business income (loss)", "-1250.50"),
        f("net_rental_income", "2 Net rental real estate income (loss)", "2480.00"),
        f("guaranteed_payments", "4c Total guaranteed payments", "5000.00"),
        f("interest_income", "5 Interest income", "85.15"),
        f("dividends", "6a Ordinary dividends", "42.75"),
        f("royalties", "7 Royalties", None),
        f("net_short_term_gain", "8 Net short-term capital gain (loss)", "0.00"),
        f("net_long_term_gain", "9a Net long-term capital gain (loss)", "325.25"),
        f("other_income", "11 Other income (loss) - coded", None, "object"),
        f("section_179", "12 Section 179 deduction", "250.00"),
        f("other_deductions.13W", "13 Code W - Other deductions", "87.65"),
        f("other_information.20A", "20 Code A - Investment income", "127.90"),
    ]
    k1_second = [
        f("other_deductions.13A", "13 Code A - Cash charitable contributions (60%)", "125.00"),
        f("charitable_contributions", "13 Codes A-G - Charitable contributions total", "125.00"),
        f("other_deductions.13H", "13 Code H - Investment interest expense", "0.00"),
        f("self_employment_earnings", "14 Code A - Net earnings from self-employment", "3749.50"),
        f("other_credits.15A", "15 Code A - Low-income housing credit", "0.00"),
        f("foreign_transactions.16A", "16 Code A - Name of country (legacy statement)", "Canada", "text"),
        f("amt_items.17A", "17 Code A - Post-1986 depreciation adjustment", "-32.10"),
        f("tax_exempt_and_nondeductible.18A", "18 Code A - Tax-exempt interest income", "0.00"),
        f("tax_exempt_and_nondeductible.18C", "18 Code C - Nondeductible expenses", "32.45"),
        f("distributions.19A", "19 Code A - Cash and marketable securities", "1500.00"),
        f("other_information.20Z", "20 Code Z - Section 199A information", "STMT", "text"),
        f("other_information.20Q", "20 Code Q - Section 1260(b) information", "0.00"),
        f("foreign_taxes_paid", "21 Foreign taxes paid or accrued", None),
        f("beginning_capital", "L Partner's capital account - beginning", "25000.00"),
        f("capital_contributed", "L Capital contributed during year", "2000.00"),
        f("capital_withdrawn", "L Withdrawals and distributions", "1500.00"),
        f("ending_capital", "L Partner's capital account - ending", "27850.00"),
    ]
    return [("1099-R", "Distributions From Pensions, Annuities, Retirement Plans", [r]),
            ("1099-G", "Certain Government Payments", [g]),
            ("1099-K", "Payment Card and Third Party Network Transactions", [k]),
            ("K-1", "Partner's Share of Income, Deductions, Credits, etc.", [k1_first, k1_second])]


def _page(doc: fitz.Document, typ: str, title: str, fields: list[Field], number: int, total: int) -> None:
    page = doc.new_page(width=612, height=792)
    page.insert_text((28, 30), "Form " + typ, fontsize=18, fontname="hebo")
    page.insert_text((28, 49), title, fontsize=10, fontname="hebo")
    page.insert_text((28, 65), "2025 | Copy B - For Recipient | Invented data; not an official IRS form", fontsize=8)
    page.draw_rect(fitz.Rect(28, 75, 584, 103), color=(0.4, 0.4, 0.4), fill=(0.94, 0.94, 0.94))
    page.insert_text((91, 94), "SYNTHETIC NOT FOR FILING", fontsize=17, fontname="hebo", color=(0.4, 0.4, 0.4))
    address_label = "Partnership mailing address" if typ == "K-1" else "Filer mailing address" if typ == "1099-K" else "Payer mailing address"
    page.insert_text((28, 120), address_label + ": " + ADDRESS, fontsize=9)
    if typ == "K-1" and number == 2:
        page.insert_text((28, 136), "Continuation for Morgan Sample / Example Lantern Partners LP", fontsize=9)
    visible = [x for x in fields if not (x.kind == "boolean" and x.value is None)]
    for index, field in enumerate(visible):
        x, y = 28 + (index % 2) * 278, 147 + (index // 2) * 38
        page.draw_rect(fitz.Rect(x, y, x + 278, y + 38), color=(0.4, 0.4, 0.4), width=0.5)
        spare = page.insert_textbox(fitz.Rect(x + 5, y + 3, x + 273, y + 21), field.label,
                                    fontsize=8, lineheight=1.05)
        if spare < 0:
            raise ValueError(f"Label overflow: {typ} {field.path}")
        if field.kind == "boolean":
            checkbox = fitz.Rect(x + 6, y + 24, x + 15, y + 33)
            page.draw_rect(checkbox, color=(0, 0, 0), width=0.8)
            if field.value:
                page.draw_line(checkbox.tl, checkbox.br, color=(0, 0, 0), width=1.1)
                page.draw_line(checkbox.bl, checkbox.tr, color=(0, 0, 0), width=1.1)
        elif field.value is not None:
            value = "* STMT" if field.value == "STMT" else str(field.value)
            if fitz.get_text_length(value, fontsize=10, fontname="hebo") > 267:
                raise ValueError(f"Value overflow: {typ} {field.path}")
            page.insert_text((x + 6, y + 32), value, fontsize=10, fontname="hebo")
    page.insert_text((28, 762), f"SYNTHETIC NOT FOR FILING | {typ} | Page {number} of {total}", fontsize=8)
    for block in page.get_text("blocks"):
        if not page.rect.contains(fitz.Rect(block[:4])):
            raise ValueError(f"Text outside page bounds: {typ}")


def _metadata(doc: fitz.Document, typ: str) -> None:
    doc.set_metadata({"title": f"Synthetic Form {typ}", "author": "Synthetic Benchmark",
                      "creationDate": "D:20260101000000Z", "modDate": "D:20260101000000Z"})


def _scan(clean: fitz.Document, typ: str) -> bytes:
    with fitz.open() as scanned:
        for source in clean:
            pix = source.get_pixmap(dpi=SCAN_PARAMETERS["dpi"], colorspace=fitz.csGRAY, alpha=False)
            image = Image.frombytes("L", (pix.width, pix.height), pix.samples)
            image = image.rotate(SCAN_PARAMETERS["rotation_degrees"], resample=Image.Resampling.BICUBIC,
                                 expand=False, fillcolor=255)
            image = image.filter(ImageFilter.GaussianBlur(SCAN_PARAMETERS["gaussian_blur_radius_pixels"]))
            jpeg = io.BytesIO()
            image.save(jpeg, format="JPEG", quality=SCAN_PARAMETERS["jpeg_quality"],
                       optimize=False, progressive=False)
            page = scanned.new_page(width=source.rect.width, height=source.rect.height)
            page.insert_image(page.rect, stream=jpeg.getvalue())
        _metadata(scanned, typ)
        return scanned.tobytes(garbage=4, deflate=True, no_new_id=True)


def build_fixtures(output_dir: Path) -> list[dict[str, Any]]:
    """Write eight PDFs / ten pages and manifest.json using the original list contract.

    Clean/scan pairs share one answer key. Top-level keys are validated against
    the live prompt-derived schema; every graded leaf has an explicit type.
    A null checkbox is omitted entirely, a false checkbox is visibly unchecked.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for typ, title, pages in _specs():
        expected: dict[str, Any] = {}
        field_types: dict[str, str] = {}
        with fitz.open() as clean:
            for number, fields in enumerate(pages, start=1):
                _page(clean, typ, title, fields, number, len(pages))
                for field in fields:
                    if field.path in field_types:
                        raise ValueError(f"Duplicate fixture path: {field.path}")
                    _set_path(expected, field.path, field.value)
                    field_types[field.path] = field.kind
            schema = schema_for(typ)
            if schema is None or set(expected) != set(schema["properties"]):
                raise ValueError(f"Fixture keys do not match current schema: {typ}")
            _metadata(clean, typ)
            variants = {"clean": clean.tobytes(garbage=4, deflate=True, no_new_id=True),
                        "degraded_scan": _scan(clean, typ)}
        for variant, pdf in variants.items():
            fixture_id = "wp_f_changed_" + typ.lower().replace("-", "_") + "_" + variant
            pdf_path = fixture_id + ".pdf"
            (output_dir / pdf_path).write_bytes(pdf)
            records.append({"corpus_id": CORPUS_ID, "fixture_id": fixture_id, "doc_type": typ,
                            "pdf_path": pdf_path, "page_count": len(pages), "variant": variant,
                            "synthetic": True, "expected": expected, "field_types": field_types,
                            "generation": {"pymupdf_version": fitz.VersionBind, "pillow_version": pillow_version,
                                           "scan_parameters": SCAN_PARAMETERS if variant == "degraded_scan" else None}})
    (output_dir / "manifest.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return records


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python -m benchmarks.taxclaw_accuracy.followup_fixtures OUTPUT_DIR")
    build_fixtures(Path(sys.argv[1]))
