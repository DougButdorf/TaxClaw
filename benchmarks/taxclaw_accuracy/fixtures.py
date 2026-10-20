"""Deterministic, invented IRS-style extraction fixtures (never usable for filing).

The PDFs contain human form labels, not extraction schema names or answer keys.
Only the separately written manifest has canonical expected values. Dotted paths
in ``field_types`` address leaves, including indexed transaction-array members.
No network, real forms, real people, credentials, or platform fonts are used.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pymupdf as fitz


@dataclass(frozen=True)
class Field:
    path: str
    label: str
    value: Any
    kind: str = "money"


def f(path: str, label: str, value: Any, kind: str = "money") -> Field:
    return Field(path, label, value, kind)


PAYER = "Juniper Example Works LLC"
RECIPIENT = "Morgan Sample"
TIN = "00-XXX0000"
SSN = "XXX-XX-0000"


def identity(*, recipient: bool = True, account: bool = False, year: bool = True) -> list[Field]:
    fields = [f("payer_name", "PAYER'S name", PAYER, "text"),
              f("payer_tin", "PAYER'S TIN", TIN, "identifier"),
              f("recipient_tin", "RECIPIENT'S TIN", SSN, "identifier")]
    if recipient:
        fields.append(f("recipient_name", "RECIPIENT'S name", RECIPIENT, "text"))
    if account:
        fields.append(f("account_number", "Account number", "SYN-0042", "identifier"))
    if year:
        fields.append(f("tax_year", "Calendar year", "2025", "text"))
    return fields


def _specs() -> list[tuple[str, str, list[list[Field]], dict[str, Any]]]:
    """Each list of fields is exactly one visually rendered page."""
    specs = []

    def add(typ: str, title: str, fields: list[Field], **extra: Any) -> None:
        specs.append((typ, title, [fields], extra))

    add("W-2", "Wage and Tax Statement", [
        f("employer_name", "c Employer's name", PAYER, "text"),
        f("employer_ein", "b Employer identification number (EIN)", TIN, "identifier"),
        f("employee_ssn", "a Employee's social security number", SSN, "identifier"),
        f("wages", "1 Wages, tips, other compensation", "82456.78"),
        f("federal_withheld", "2 Federal income tax withheld", "11234.56"),
        f("box_codes.D", "12a Code D - Elective retirement deferrals", "6500.00"),
        f("box_codes.DD", "12b Code DD - Employer health coverage", "9840.25"),
        f("state_wages", "16 State wages, tips, etc.", "82456.78"),
        f("state_withheld", "17 State income tax", "4120.15"),
        f("local_wages", "18 Local wages, tips, etc.", None),
    ])
    add("1099-NEC", "Nonemployee Compensation", identity(recipient=False, year=False) + [
        f("nonemployee_comp", "1 Nonemployee compensation", "18425.70"),
        f("federal_withheld", "4 Federal income tax withheld", "0.00"),
        f("state_income", "7 State income", None),
    ])
    add("1099-INT", "Interest Income", identity(recipient=False, year=False) + [
        f("interest_income", "1 Interest income", "1245.67"),
        f("early_withdrawal_penalty", "2 Early withdrawal penalty", "45.25"),
        f("us_bond_interest", "3 Interest on U.S. Savings Bonds and Treasury obligations", "312.80"),
        f("federal_withheld", "4 Federal income tax withheld", "0.00"),
        f("tax_exempt_interest", "8 Tax-exempt interest", None),
    ])
    add("1099-DIV", "Dividends and Distributions", identity() + [
        f("ordinary_dividends", "1a Total ordinary dividends", "2350.12"),
        f("qualified_dividends", "1b Qualified dividends", "1875.09"),
        f("total_capital_gain", "2a Total capital gain distributions", "432.10"),
        f("unrecap_1250_gain", "2b Unrecaptured section 1250 gain", "12.50"),
        f("section_1202_gain", "2c Section 1202 gain", None),
        f("collectibles_gain", "2d Collectibles (28%) gain", "0.00"),
        f("nondividend_distributions", "3 Nondividend distributions", "105.00"),
        f("federal_withheld", "4 Federal income tax withheld", "0.00"),
        f("section_199a_dividends", "5 Section 199A dividends", "87.25"),
        f("investment_expenses", "6 Investment expenses", None),
        f("foreign_tax_paid", "7 Foreign tax paid", "23.45"),
        f("foreign_country", "8 Foreign country or U.S. possession", "Canada", "text"),
        f("cash_liquidation", "9 Cash liquidation distributions", "0.00"),
        f("noncash_liquidation", "10 Noncash liquidation distributions", None),
        f("exempt_interest_dividends", "12 Exempt-interest dividends", "54.00"),
        f("specified_pab_dividends", "13 Specified private activity bond interest dividends", "4.00"),
    ])
    add("consolidated-1099", "Consolidated Tax Statement", identity(account=True) + [
        f("div_ordinary_dividends", "1099-DIV 1a Total ordinary dividends", "980.20"),
        f("div_qualified_dividends", "1099-DIV 1b Qualified dividends", "750.10"),
        f("div_total_capital_gain", "1099-DIV 2a Total capital gain distributions", "120.00"),
        f("div_federal_withheld", "1099-DIV 4 Federal income tax withheld", "0.00"),
        f("div_exempt_interest", "1099-DIV 12 Exempt-interest dividends", None),
        f("int_interest_income", "1099-INT 1 Interest income", "84.32"),
        f("int_early_withdrawal_penalty", "1099-INT 2 Early withdrawal penalty", None),
        f("int_us_bond_interest", "1099-INT 3 U.S. Savings Bonds / Treasury interest", "14.56"),
        f("int_federal_withheld", "1099-INT 4 Federal income tax withheld", "0.00"),
        f("int_tax_exempt_interest", "1099-INT 8 Tax-exempt interest", "25.75"),
        f("oid_original_issue_discount", "1099-OID 1 Original issue discount", "18.90"),
        f("oid_federal_withheld", "1099-OID 4 Federal income tax withheld", "0.00"),
        f("misc_gross_proceeds", "1099-MISC 10 Gross proceeds paid to an attorney", None),
        f("misc_federal_withheld", "1099-MISC 4 Federal income tax withheld", None),
    ])
    add("1099-B", "Proceeds From Broker and Barter Exchange Transactions", identity(account=True) + [
        f("description", "1a Description of property", "10 SH EXAMPLE ORCHARD FUND", "text"),
        f("cusip", "CUSIP number", "000000000", "identifier"),
        f("proceeds", "1d Proceeds", "1250.00"),
        f("cost_basis", "1e Cost or other basis", "1500.00"),
        f("wash_sale_loss_disallowed", "1g Wash sale loss disallowed", "0.00"),
        f("term", "2 Type of gain or loss", "Short-term", "text"),
        f("federal_withheld", "4 Federal income tax withheld", "0.00"),
        f("gain_loss", "Realized gain or (loss) - supplementary information", "-250.00"),
    ])
    add("1099-MISC", "Miscellaneous Information", identity() + [
        f("rents", "1 Rents", "12000.00"),
        f("royalties", "2 Royalties", "340.55"),
        f("other_income", "3 Other income", "125.00"),
        f("federal_withheld", "4 Federal income tax withheld", "0.00"),
        f("fishing_boat_proceeds", "5 Fishing boat proceeds", None),
        f("medical_payments", "6 Medical and health care payments", None),
        f("substitute_payments", "8 Substitute payments in lieu of dividends or interest", "16.25"),
        f("crop_insurance", "9 Crop insurance proceeds", None),
        f("gross_proceeds_attorney", "10 Gross proceeds paid to an attorney", None),
        f("section_409a_deferrals", "12 Section 409A deferrals", None),
        f("nonqualified_deferred", "15 Nonqualified deferred compensation", None),
        f("state_income", "18 State income", "12465.55"),
    ])
    add("1099-OID", "Original Issue Discount", identity() + [
        f("original_issue_discount", "1 Original issue discount for 2025", "425.67"),
        f("other_periodic_interest", "2 Other periodic interest", "123.40"),
        f("description", "7 Description", "EXAMPLE ZERO COUPON NOTE 2030", "text"),
        f("oid_us_treasury", "8 Original issue discount on U.S. Treasury obligations", "55.15"),
        f("federal_withheld", "4 Federal income tax withheld", "0.00"),
        f("market_discount", "5 Market discount", "18.20"),
        f("acquisition_premium", "6 Acquisition premium", None),
    ])
    k1_first = [
        f("tax_year", "For calendar year", "2025", "text"),
        f("partnership_name", "A/B Partnership's name", "Example Lantern Partners LP", "text"),
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
        f("section_179", "12 Section 179 deduction", "250.00"),
    ]
    k1_second = [
        f("charitable_contributions", "13 Code A - Cash charitable contributions (60%)", "125.00"),
        f("other_deductions.W", "13 Code W - Other deductions", "87.65"),
        f("self_employment_earnings", "14 Code A - Net earnings from self-employment", "3749.50"),
        f("other_credits.A", "15 Code A - Low-income housing credit", "0.00"),
        f("foreign_transactions.A", "16 Code A - Name of country", "Canada", "text"),
        f("amt_items.A", "17 Code A - Post-1986 depreciation adjustment", "-32.10"),
        f("other_information.A", "20 Code A - Investment income", "127.90"),
        f("beginning_capital", "L Partner's capital account - beginning", "25000.00"),
        f("capital_contributed", "L Capital contributed during year", "2000.00"),
        f("capital_withdrawn", "L Withdrawals and distributions", "1500.00"),
        f("ending_capital", "L Partner's capital account - ending", "27850.00"),
    ]
    specs.append(("K-1", "Partner's Share of Income, Deductions, Credits, etc.", [k1_first, k1_second], {}))
    da_pages = []
    for i in range(2):
        prefix = f"transactions.{i}."
        head = [Field("header." + x.path, x.label, 2025 if x.path == "tax_year" else x.value,
                      "number" if x.path == "tax_year" else x.kind) for x in identity(account=True)]
        txn = [
            f("asset_code", "1a Digital asset code", "SYNBTC" if i == 0 else "SYNETH", "identifier"),
            f("asset_name", "1b Name of digital asset", "Example Bitcoin" if i == 0 else "Example Ether", "text"),
            f("units", "1c Number of units", "0.12500000" if i == 0 else "1.25000000", "text"),
            f("date_acquired", "1d Date acquired", "2024-02-03" if i == 0 else "2025-01-15", "date"),
            f("date_sold", "1e Date sold or disposed", "2025-07-08" if i == 0 else "2025-09-20", "date"),
            f("proceeds", "1f Proceeds", "7500.00" if i == 0 else "3100.25"),
            f("cost_basis", "1g Cost or other basis", "4000.00" if i == 0 else "3500.00"),
            f("accrued_market_discount", "1h Accrued market discount", None),
            f("wash_sale_disallowed", "1i Wash sale loss disallowed", "0.00"),
            f("basis_reported_to_irs", "2 Basis reported to IRS", True, "boolean"),
            f("proceeds_type", "3 Type of proceeds", "Gross proceeds", "text"),
            f("qof_proceeds", "3 Qualified opportunity fund proceeds", False, "boolean"),
            f("federal_withheld", "4 Federal income tax withheld", "0.00"),
            f("loss_not_allowed", "5 Loss not allowed", False, "boolean"),
            f("gain_loss_term", "6 Term", "Long-term" if i == 0 else "Short-term", "text"),
            f("cash_only", "7 Cash-only transaction", True, "boolean"),
            f("customer_info_used", "8 Customer-provided acquisition information used", False, "boolean"),
            f("noncovered", "9 Noncovered security", False, "boolean"),
            f("aggregate_flag", "10 Aggregation method", None, "text"),
            f("transaction_count", "10 Number of transactions", 1, "number"),
            f("nft_first_sale_proceeds", "11 NFT first-sale proceeds", None),
            f("units_transferred_in", "12 Units transferred in", None, "text"),
            f("transfer_in_date", "12 Transfer-in date", None, "date"),
            f("form_8949_code", "13 Form 8949 applicable checkbox", "D" if i == 0 else "A", "identifier"),
            f("state_name", "14 State name", "NY", "text"),
            f("state_id", "15 State identification number", "SYN-NY-00", "identifier"),
            f("state_withheld", "16 State tax withheld", "0.00"),
        ]
        da_pages.append(head + [Field(prefix + x.path, x.label, x.value, x.kind) for x in txn])
    specs.append(("1099-DA", "Digital Asset Proceeds From Broker Transactions", da_pages,
                  {"computed_expected": {"is_multi_transaction": True}}))
    add("1099-R", "Distributions From Pensions, Annuities, Retirement Plans", identity() + [
        f("gross_distribution", "1 Gross distribution", "18500.00"),
        f("taxable_amount", "2a Taxable amount", "17500.00"),
        f("taxable_amount_not_determined", "2b Taxable amount not determined", False, "boolean"),
        f("total_distribution", "2b Total distribution", False, "boolean"),
        f("capital_gain", "3 Capital gain (included in box 2a)", None),
        f("federal_withheld", "4 Federal income tax withheld", "1850.00"),
        f("employee_contributions", "5 Employee contributions / insurance premiums", "1000.00"),
        f("distribution_code", "7 Distribution code(s)", "7", "identifier"),
        f("ira_sep_simple", "7 IRA/SEP/SIMPLE", True, "boolean"),
        f("state_withheld", "14 State tax withheld", "0.00"),
        f("state_distribution", "16 State distribution", "17500.00"),
    ], prompt_gap="No dedicated 1099-R prompt; extraction currently uses generic labels.")
    add("1040", "U.S. Individual Income Tax Return", [
        f("tax_year", "For the year", "2025", "text"),
        f("taxpayer_name", "Your first name and middle initial / Last name", RECIPIENT, "text"),
        f("taxpayer_ssn", "Your social security number", SSN, "identifier"),
        f("filing_status", "Filing status", "Single", "text"),
        f("wages", "1a Total amount from Form(s) W-2, box 1", "82456.78"),
        f("tax_exempt_interest", "2a Tax-exempt interest", None),
        f("taxable_interest", "2b Taxable interest", "1245.67"),
        f("qualified_dividends", "3a Qualified dividends", "1875.09"),
        f("ordinary_dividends", "3b Ordinary dividends", "2350.12"),
        f("total_income", "9 Total income", "86052.57"),
        f("adjustments", "10 Adjustments to income", "0.00"),
        f("adjusted_gross_income", "11a Adjusted gross income", "86052.57"),
        f("standard_or_itemized_deduction", "12e Standard deduction or itemized deductions", "15750.00"),
        f("taxable_income", "15 Taxable income", "70302.57"),
        f("total_tax", "24 Total tax", "10380.00"),
        f("federal_withheld", "25a Federal income tax withheld from W-2", "11234.56"),
        f("total_payments", "33 Total payments", "11234.56"),
        f("refund", "35a Amount to be refunded to you", "854.56"),
        f("amount_owed", "37 Amount you owe", "0.00"),
    ], prompt_gap="No dedicated 1040 prompt; extraction currently uses generic labels.")
    return specs


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    keys = path.split(".")
    node: Any = target
    for index, key in enumerate(keys[:-1]):
        next_is_index = keys[index + 1].isdigit()
        if isinstance(node, list):
            while len(node) <= int(key):
                node.append({})
            node = node[int(key)]
        else:
            node = node.setdefault(key, [] if next_is_index else {})
    if isinstance(node, list):
        raise ValueError("Fixture leaves must be named fields")
    node[keys[-1]] = value


def _page(doc: fitz.Document, typ: str, title: str, fields: list[Field], number: int, total: int) -> None:
    page = doc.new_page(width=612, height=792)
    page.insert_text((28, 31), "Form " + typ, fontsize=19, fontname="hebo")
    page.insert_text((28, 51), title, fontsize=10, fontname="hebo")
    page.insert_text((28, 68), "2025   Copy B - For Recipient   |   Invented data; not an official IRS form", fontsize=8)
    page.draw_rect(fitz.Rect(26, 78, 586, 105), fill=(0.93, 0.93, 0.93), color=(0.4, 0.4, 0.4))
    page.insert_text((91, 96), "SYNTHETIC NOT FOR FILING", fontsize=17, fontname="hebo", color=(0.45, 0.45, 0.45))
    row_height = 37 if len(fields) > 30 else 49
    for index, field in enumerate(fields):
        column = index % 2
        row = index // 2
        x = 28 + column * 278
        y = 116 + row * row_height
        rect = fitz.Rect(x, y, x + 278, y + row_height)
        page.draw_rect(rect, color=(0.35, 0.35, 0.35), width=0.55)
        label_rect = fitz.Rect(x + 5, y + 3, x + 273, y + 21)
        spare = page.insert_textbox(label_rect, field.label, fontsize=7.3, lineheight=1.05)
        if spare < 0:
            raise ValueError(f"Label overflow: {typ} {field.path}")
        if field.value is not None:
            value = ("[X] Yes   [ ] No" if field.value else "[ ] Yes   [X] No") if field.kind == "boolean" else str(field.value)
            if fitz.get_text_length(value, fontsize=10, fontname="hebo") > 267:
                raise ValueError(f"Value overflow: {typ} {field.path}")
            page.insert_text((x + 6, y + 31), value, fontsize=10, fontname="hebo")
    page.insert_text((28, 762), f"SYNTHETIC NOT FOR FILING  |  {typ}  |  Page {number} of {total}", fontsize=8)
    if typ == "K-1" and number == 2:
        page.insert_text((28, 738), "Continuation statement for Morgan Sample - Example Lantern Partners LP", fontsize=8)
    for block in page.get_text("blocks"):
        if not page.rect.contains(fitz.Rect(block[:4])):
            raise ValueError(f"Text outside page bounds: {typ}")


def build_fixtures(output_dir: Path) -> list[dict[str, Any]]:
    """Write 12 PDFs and manifest.json; paths are relative to output_dir.

    Stable text, fixed metadata and no generated document ID produce byte-for-byte
    stable PDFs when rerun under the same PyMuPDF version. Expected values never
    enter PDF metadata. Money uses decimal strings; visible blanks are None.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for typ, title, pages, extras in _specs():
        fixture_id = typ.lower().replace("-", "_") + "_clean"
        expected: dict[str, Any] = {}
        field_types: dict[str, str] = {}
        with fitz.open() as doc:
            for number, fields in enumerate(pages, start=1):
                _page(doc, typ, title, fields, number, len(pages))
                for field in fields:
                    _set_path(expected, field.path, field.value)
                    field_types[field.path] = field.kind
            for key, value in extras.get("computed_expected", {}).items():
                expected[key] = value
                field_types[key] = "boolean"
            doc.set_metadata({"title": f"Synthetic Form {typ}", "author": "Synthetic Benchmark",
                              "creationDate": "D:20260101000000Z", "modDate": "D:20260101000000Z"})
            pdf_path = fixture_id + ".pdf"
            (output_dir / pdf_path).write_bytes(doc.tobytes(garbage=4, deflate=True, no_new_id=True))
        record = {"fixture_id": fixture_id, "doc_type": typ, "pdf_path": pdf_path,
                  "page_count": len(pages), "variant": "clean", "synthetic": True,
                  "expected": expected, "field_types": field_types}
        if "prompt_gap" in extras:
            record["prompt_gap"] = extras["prompt_gap"]
        records.append(record)
    (output_dir / "manifest.json").write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return records
