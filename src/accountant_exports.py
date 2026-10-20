"""Form 8949-ready CSV and TXF v042 exports of capital-gain transactions.

Sources (see README "Exports for accountants and tax software"):

- IRS Form 8949 (2025) and its instructions (Jan 20, 2026):
  https://www.irs.gov/pub/irs-pdf/f8949.pdf, https://www.irs.gov/pub/irs-pdf/i8949.pdf.
  Check boxes A/B/C/G/H/I (Part I, short-term) and D/E/F/J/K/L (Part II,
  long-term); G-L are new for 2025 and cover Form 1099-DA. Column (h) is
  (d) - (e) + (g). Codes are listed in alphabetical order with the net
  amount in (g). Holding period: more than 1 year is long-term, counting from
  the day after acquisition and including the day of disposal.
- TXF v042 (Intuit, last changed 11/30/2011), as published by Tax Data Exchange:
  https://taxdataexchange.org/docs/txf/v042/txf-spec.html. Header V042/A/D/^;
  capital-gain detail records use Format 4 (P, D acquired, D sold, $ cost,
  $ sales net) or Format 5 (Format 4 + $ wash-sale amount). Refnums 321/711/712
  (short-term, 8949 copy A/B/C) and 323/713/714 (long-term copy A/B/C) map to
  today's boxes A/B/C and D/E/F. TXF v042 has no refnums for boxes G-L, so
  1099-DA rows are never written to TXF.

Nothing here prepares a return or gives tax advice: values are AI-extracted,
gain/loss is arithmetic on those values, and anything that can't be derived
from the form itself (missing basis, unknown holding period, unknown basis
reporting) is left blank and flagged for review instead of guessed.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Iterable, Sequence

from .db import db
from .exporter import TAXCLAW_VERSION, _csv_generated_human, _csv_notice_block

CAPITAL_DOC_TYPES = ("1099-B", "1099-DA", "consolidated-1099")

NOTICE_TEXT = (
    "AI-extracted data. May contain errors. Verify every figure against the original documents before use. "
    "Not tax advice. TaxClaw does not prepare or file returns. Outbranch Network LLC makes no warranty of accuracy."
)

CENT = Decimal("0.01")

# Form 8949 (2025) check boxes: (form family, term, basis reported to IRS) -> letter.
SHORT_TERM_BOXES = frozenset("ABCGHI")
LONG_TERM_BOXES = frozenset("DEFJKL")
DIGITAL_ASSET_BOXES = frozenset("GHIJKL")
_BOX = {
    ("1099-B", "short", True): "A",
    ("1099-B", "short", False): "B",
    ("1099-B", "long", True): "D",
    ("1099-B", "long", False): "E",
    ("1099-DA", "short", True): "G",
    ("1099-DA", "short", False): "H",
    ("1099-DA", "long", True): "J",
    ("1099-DA", "long", False): "K",
}

# TXF v042 refnums for capital-gain detail (8949 copy A/B/C == today's A/B/C, D/E/F).
TXF_REFNUM = {"A": 321, "B": 711, "C": 712, "D": 323, "E": 713, "F": 714}

FORM_8949_COLUMNS = [
    "category",
    "part",
    "term",
    "a_description",
    "b_date_acquired",
    "c_date_sold",
    "d_proceeds",
    "e_cost_basis",
    "f_adjustment_codes",
    "g_adjustment_amount",
    "h_gain_or_loss",
    "source_document_id",
    "source_form",
    "payer",
    "confidence",
    "needs_review",
    "review_reasons",
]


# ---------------------------------------------------------------------------
# Normalized transactions
# ---------------------------------------------------------------------------


@dataclass
class SourceTransaction:
    """One sale as read from a 1099-B, consolidated 1099 or 1099-DA (raw strings, no derivation)."""

    source_document_id: str
    source_form: str  # "1099-B" | "consolidated-1099" | "1099-DA"
    payer: str | None = None
    description: str | None = None
    date_acquired: Any = None
    date_sold: Any = None
    proceeds: Any = None
    cost_basis: Any = None
    wash_sale_disallowed: Any = None
    accrued_market_discount: Any = None
    term: Any = None  # the form's short/long flag, as printed
    basis_reported_to_irs: Any = None
    noncovered: Any = None
    form_8949_box: Any = None  # a box letter printed on the statement, if any
    loss_not_allowed: Any = None
    reported_gain_loss: Any = None  # gain/(loss) printed on the statement, used only as a cross-check
    confidence: float | None = None
    document_needs_review: bool = False
    ref: str = ""  # human locator for warnings, e.g. "lot 2 (page 3)"

    @property
    def family(self) -> str:
        return "1099-DA" if self.source_form == "1099-DA" else "1099-B"


@dataclass
class Form8949Row:
    category: str
    part: str
    term: str
    description: str
    date_acquired: str
    date_sold: str
    proceeds: Decimal | None
    cost_basis: Decimal | None
    adjustment_codes: str
    adjustment_amount: Decimal | None
    gain_or_loss: Decimal | None
    source_document_id: str
    source_form: str
    payer: str
    confidence: float | None
    review_reasons: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)  # contradictory values (subset of review_reasons)
    ref: str = ""

    @property
    def needs_review(self) -> bool:
        return bool(self.review_reasons)

    def as_csv_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "part": self.part,
            "term": self.term,
            "a_description": self.description,
            "b_date_acquired": self.date_acquired,
            "c_date_sold": self.date_sold,
            "d_proceeds": _fmt(self.proceeds),
            "e_cost_basis": _fmt(self.cost_basis),
            "f_adjustment_codes": self.adjustment_codes,
            "g_adjustment_amount": _fmt(self.adjustment_amount),
            "h_gain_or_loss": _fmt(self.gain_or_loss),
            "source_document_id": self.source_document_id,
            "source_form": self.source_form,
            "payer": self.payer,
            "confidence": "" if self.confidence is None else f"{self.confidence:.2f}",
            "needs_review": "true" if self.needs_review else "false",
            "review_reasons": "; ".join(self.review_reasons),
        }


# ---------------------------------------------------------------------------
# Value parsing (never guesses: unparseable -> None + review reason)
# ---------------------------------------------------------------------------

_BLANK = frozenset({"", "-", "--", "—", "n/a", "na", "none", "null", "missing", "not reported", "unknown", "not provided"})


def parse_amount(v: Any) -> tuple[Decimal | None, bool]:
    """Parse a money string ("1,234.56", "$(250.00)", "-12") to Decimal cents.

    Returns (value, ok). Blank-like values -> (None, True); unparseable -> (None, False).
    Rounds half-up to cents.
    """

    if v is None or isinstance(v, bool):
        return None, v is None
    if isinstance(v, (int, Decimal)):
        return Decimal(v).quantize(CENT, rounding=ROUND_HALF_UP), True
    if isinstance(v, float):
        return Decimal(repr(v)).quantize(CENT, rounding=ROUND_HALF_UP), True
    s = str(v).strip()
    if s.lower() in _BLANK:
        return None, True
    neg = False
    s = s.replace("$", "").replace(",", "").replace(" ", "")
    if s.startswith("(") and s.endswith(")"):
        neg, s = True, s[1:-1]
    if s.endswith("-") and not s.startswith("-"):  # "250.00-" (some broker layouts)
        neg, s = True, s[:-1]
    if s.startswith("-"):
        neg, s = (not neg), s[1:]
    try:
        d = Decimal(s)
    except InvalidOperation:
        return None, False
    if not d.is_finite():
        return None, False
    d = d.quantize(CENT, rounding=ROUND_HALF_UP)
    return (-d if neg else d), True


_DATE_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y", "%m-%d-%y", "%b %d, %Y", "%B %d, %Y", "%d-%b-%Y", "%Y/%m/%d")


def parse_date(v: Any) -> tuple[date | str | None, bool]:
    """Returns (date | "VARIOUS" | "INHERITED" | None, ok)."""

    if v is None:
        return None, True
    s = " ".join(str(v).strip().split())
    if s.lower() in _BLANK:
        return None, True
    if s.upper() in ("VARIOUS", "INHERITED"):
        return s.upper(), True
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date(), True
        except ValueError:
            continue
    return None, False


def parse_bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "yes", "y", "1", "x", "checked"):
            return True
        if s in ("false", "no", "n", "0", "unchecked"):
            return False
    return None


def term_from_flag(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip().lower()
    if not s:
        return None
    if "short" in s or s in ("st", "s"):
        return "short"
    if "long" in s or s in ("lt", "l"):
        return "long"
    return None


def box_letter(v: Any) -> str | None:
    if v is None:
        return None
    s = re.sub(r"(?i)\b(box|form|8949|check(ed)?)\b", "", str(v)).strip(" .:()[]-").upper()
    return s if len(s) == 1 and s in SHORT_TERM_BOXES | LONG_TERM_BOXES else None


def one_year_after(d: date) -> date:
    try:
        return d.replace(year=d.year + 1)
    except ValueError:  # Feb 29 -> Feb 28 (holding period starts Mar 1)
        return d.replace(year=d.year + 1, day=28)


def term_from_dates(acquired: date, sold: date) -> str:
    """IRS: long-term if held more than 1 year (count from the day after acquisition, include the sale day)."""

    return "long" if sold > one_year_after(acquired) else "short"


def _fmt(d: Decimal | None) -> str:
    return "" if d is None else f"{d:.2f}"


def _fmt_date(v: date | str | None, raw: Any) -> str:
    if isinstance(v, date):
        return v.strftime("%m/%d/%Y")
    if isinstance(v, str):
        return v
    return "" if raw is None else str(raw).strip()


# ---------------------------------------------------------------------------
# Transaction -> Form 8949 row
# ---------------------------------------------------------------------------


def to_8949_row(t: SourceTransaction) -> Form8949Row:
    reasons: list[str] = []
    da = t.family == "1099-DA"

    proceeds, ok = parse_amount(t.proceeds)
    if not ok:
        reasons.append(f"proceeds not a number: {t.proceeds!r}")
    if proceeds is None and ok:
        reasons.append("proceeds missing")
    basis, ok = parse_amount(t.cost_basis)
    if not ok:
        reasons.append(f"basis not a number: {t.cost_basis!r}")
    elif basis is None:
        reasons.append("basis missing — common for 1099-DA; enter your own basis" if da else "basis missing; enter your own basis")
    wash, ok = parse_amount(t.wash_sale_disallowed)
    if not ok:
        reasons.append(f"wash sale amount not a number: {t.wash_sale_disallowed!r}")
    discount, ok = parse_amount(t.accrued_market_discount)
    if not ok:
        reasons.append(f"accrued market discount not a number: {t.accrued_market_discount!r}")

    acquired, ok_a = parse_date(t.date_acquired)
    sold, ok_s = parse_date(t.date_sold)
    if not ok_a:
        reasons.append(f"date acquired not recognized: {t.date_acquired!r}")
    if not ok_s:
        reasons.append(f"date sold not recognized: {t.date_sold!r}")
    elif sold is None:
        reasons.append("date sold missing")

    # Values that contradict each other: flagged here and kept out of TXF.
    conflicts: list[str] = []

    # A Form 8949 box letter printed on the statement (ignored if it can't apply to this form).
    letter = box_letter(t.form_8949_box)
    if letter and (letter in DIGITAL_ASSET_BOXES) != da:
        reasons.append(f"ignored box {letter} printed for this sale: it does not apply to a {t.family}")
        letter = None
    letter_term = None if letter is None else ("short" if letter in SHORT_TERM_BOXES else "long")

    # Holding period: the form's short/long flag, else the printed box letter, else the dates.
    flag_term = term_from_flag(t.term)
    date_term = None
    if acquired == "INHERITED":
        date_term = "long"
    elif isinstance(acquired, date) and isinstance(sold, date):
        if sold < acquired:
            conflicts.append("date sold is before date acquired")
        else:
            date_term = term_from_dates(acquired, sold)
    term = flag_term or letter_term or date_term
    if flag_term and letter_term and flag_term != letter_term:
        conflicts.append(f"form says {flag_term}-term but box {letter} is {letter_term}-term")
        term, letter = None, None
    elif term is None:
        reasons.append("holding period unknown (no short/long flag on the form and dates incomplete)")
    elif date_term and term != date_term:
        conflicts.append(f"form says {term}-term but the dates give {date_term}-term")

    # Check box: derived from form family + term + the basis-reported checkbox (IRS rule);
    # a printed letter is a cross-check, or the answer when basis reporting isn't visible.
    category = ""
    reported = parse_bool(t.basis_reported_to_irs)
    noncovered = parse_bool(t.noncovered)
    boxes = "1099-DA box 2 / box 9" if da else "1099-B box 12 / box 5"
    if reported is True and noncovered is True:
        reasons.append(f"both 'basis reported to IRS' and 'noncovered' are marked; confirm {boxes}")
    if reported is None and noncovered is not None:
        reported = not noncovered
    if term:
        derived = _BOX[(t.family, term, reported)] if reported is not None else None
        if derived and letter and derived != letter:
            conflicts.append(f"statement says box {letter} but the form's checkboxes give box {derived}")
        elif derived or letter:
            category = derived or letter  # type: ignore[assignment]
        else:
            reasons.append(f"can't tell if basis was reported to the IRS ({boxes})")
    reasons.extend(conflicts)

    # Adjustments (codes in alphabetical order, net amount in (g)).
    codes: list[str] = []
    adj = Decimal("0.00")
    adj_known = True
    if discount is not None and discount != 0:
        codes.append("D")
        if proceeds is not None and basis is not None:
            gain = max(proceeds - basis, Decimal("0.00"))
            adj -= min(gain, abs(discount))
            reasons.append(
                "code D amount uses the IRS accrued-market-discount worksheet; it is 0 if you elected to include "
                "market discount in income currently"
            )
        else:
            adj_known = False
            reasons.append("code D amount needs proceeds and basis")
    if wash is not None and wash != 0:
        codes.append("W")
        adj += abs(wash)
    if parse_bool(t.loss_not_allowed):
        reasons.append("form says loss not allowed (code L may apply); not computed")
    codes.sort()
    g = (adj if adj_known else None) if codes else None

    h = None
    if proceeds is not None and basis is not None and (adj_known or not codes):
        h = (proceeds - basis + (adj if codes else Decimal("0.00"))).quantize(CENT, rounding=ROUND_HALF_UP)

    printed, ok = parse_amount(t.reported_gain_loss)
    if h is not None and ok and printed is not None and printed != h:
        msg = f"computed gain/loss {_fmt(h)} differs from the statement's {_fmt(printed)}; check basis and adjustments"
        conflicts.append(msg)
        reasons.append(msg)

    description = " ".join(str(t.description or "").split())
    if not description:
        reasons.append("description missing")
    if t.document_needs_review:
        reasons.append("source document is flagged for review")

    return Form8949Row(
        category=category,
        part={"short": "I", "long": "II"}.get(term or "", ""),
        term=term or "",
        description=description,
        date_acquired=_fmt_date(acquired, t.date_acquired),
        date_sold=_fmt_date(sold, t.date_sold),
        proceeds=proceeds,
        cost_basis=basis,
        adjustment_codes="".join(codes),
        adjustment_amount=g,
        gain_or_loss=h,
        source_document_id=t.source_document_id,
        source_form=t.source_form,
        payer=t.payer or "",
        confidence=t.confidence,
        review_reasons=reasons,
        conflicts=conflicts,
        ref=t.ref,
    )


def rows_for(transactions: Iterable[SourceTransaction]) -> list[Form8949Row]:
    return [to_8949_row(t) for t in transactions]


# ---------------------------------------------------------------------------
# Renderers (pure)
# ---------------------------------------------------------------------------

_CATEGORY_ORDER = {c: i for i, c in enumerate("ABCGHIDEFJKL")}


def _sorted(rows: Sequence[Form8949Row]) -> list[Form8949Row]:
    return sorted(rows, key=lambda r: (_CATEGORY_ORDER.get(r.category, 99), r.source_document_id))


def render_8949_csv(rows: Sequence[Form8949Row], *, generated: str | None = None) -> str:
    buf = io.StringIO()
    buf.write(_csv_notice_block(generated or _csv_generated_human()))
    buf.write(
        "# Form 8949 layout (2025): one row per sale; category = the box to check (A/B/D/E for 1099-B, G/H/J/K for 1099-DA).\n"
        "# Rows with needs_review=true are incomplete (e.g. missing basis): column (h) is blank rather than guessed.\n"
    )
    w = csv.DictWriter(buf, fieldnames=FORM_8949_COLUMNS, lineterminator="\n")
    w.writeheader()
    for r in _sorted(rows):
        w.writerow(r.as_csv_dict())
    return buf.getvalue()


@dataclass
class TxfExport:
    content: str
    records: int
    warnings: list[str]
    notice: str = NOTICE_TEXT


_TXF_SAFE = re.compile(r"[^\x20-\x7e]")


def _txf_text(s: str) -> str:
    # ASCII only, one line; the spec is ASCII and line-oriented.
    s = s.replace("—", "-").replace("–", "-")
    return _TXF_SAFE.sub("", " ".join(s.split()))


def _txf_amount(d: Decimal) -> str:
    return f"{d:.2f}"


def render_txf(rows: Sequence[Form8949Row], *, export_date: date | None = None, app: str | None = None) -> TxfExport:
    """TXF v042 detail records (Format 4, or Format 5 when there is a wash-sale amount).

    Rows that TXF can't represent or that are missing a required value are
    skipped and listed in ``warnings``; no partial or guessed records are written.
    """

    lines = ["V042", f"A{_txf_text(app or f'TaxClaw {TAXCLAW_VERSION}')}", f"D{(export_date or date.today()).strftime('%m/%d/%Y')}", "^"]
    warnings: list[str] = []
    n = 0
    for r in _sorted(rows):
        who = f"{r.source_form} {r.source_document_id}" + (f" {r.ref}" if r.ref else "") + (f" ({r.description})" if r.description else "")
        problem = None
        if r.category in DIGITAL_ASSET_BOXES:
            problem = f"box {r.category} (Form 1099-DA): TXF v042 has no reference number for boxes G-L; use the Form 8949 CSV"
        elif r.conflicts:
            problem = "extracted values contradict each other: " + "; ".join(r.conflicts)
        elif not r.category:
            problem = "no Form 8949 box (holding period or basis reporting unknown)"
        elif r.proceeds is None:
            problem = "proceeds missing"
        elif r.cost_basis is None:
            problem = "basis missing"
        elif not r.date_sold or r.date_sold in ("VARIOUS", "INHERITED") or not re.fullmatch(r"\d\d/\d\d/\d{4}", r.date_sold):
            problem = "date sold missing or not a date"
        elif r.date_acquired == "INHERITED":
            problem = "date acquired INHERITED has no TXF equivalent"
        elif r.date_acquired != "VARIOUS" and not re.fullmatch(r"\d\d/\d\d/\d{4}", r.date_acquired):
            problem = "date acquired missing or not a date"
        elif set(r.adjustment_codes) - {"W"}:
            problem = f"adjustment code(s) {r.adjustment_codes} can't be expressed in TXF (only wash sales)"
        elif "W" in r.adjustment_codes and r.adjustment_amount is None:
            problem = "wash sale amount missing"
        if problem:
            warnings.append(f"skipped {who}: {problem}")
            continue
        if r.needs_review:
            warnings.append(f"included {who} but it needs review: {'; '.join(r.review_reasons)}")
        lines += [
            "TD",
            f"N{TXF_REFNUM[r.category]}",
            "C1",
            "L1",
            f"P{_txf_text(r.description)}",
            "DVarious" if r.date_acquired == "VARIOUS" else f"D{r.date_acquired}",
            f"D{r.date_sold}",
            f"${_txf_amount(r.cost_basis)}",
            f"${_txf_amount(r.proceeds)}",
        ]
        if "W" in r.adjustment_codes:
            lines.append(f"${_txf_amount(r.adjustment_amount)}")  # Format 5: disallowed wash sale amount
        lines.append("^")
        n += 1
    # The spec prefers CR+LF line endings.
    return TxfExport(content="\r\n".join(lines) + "\r\n", records=n, warnings=warnings)


# ---------------------------------------------------------------------------
# Loading from the TaxClaw database
# ---------------------------------------------------------------------------


def _fields_by_path(con: Any, doc_id: str) -> dict[str, str | None]:
    rows = con.execute("SELECT field_path, field_value FROM extracted_fields WHERE document_id=?", (doc_id,)).fetchall()
    return {r[0]: r[1] for r in rows}


def _latest_extraction(con: Any, doc_id: str) -> Any:
    r = con.execute(
        "SELECT raw_json FROM form_extractions WHERE document_id=? ORDER BY created_at DESC LIMIT 1", (doc_id,)
    ).fetchone()
    if not r or not r[0]:
        return None
    try:
        return json.loads(r[0])
    except ValueError:
        return None


_TXN_PATH = re.compile(r"^transactions\[(\d+)\]\.([A-Za-z0-9_]+)$")


def _da_from_fields(fields: dict[str, str | None]) -> list[dict[str, Any]]:
    """1099-DA transactions as edited in the UI (extracted_fields ``transactions[i].field``)."""

    by_idx: dict[int, dict[str, Any]] = {}
    for path, value in fields.items():
        m = _TXN_PATH.match(path)
        if m:
            by_idx.setdefault(int(m.group(1)), {})[m.group(2)] = value
    return [by_idx[i] for i in sorted(by_idx)]


def _payer(doc: dict[str, Any], fields: dict[str, str | None]) -> str | None:
    for v in (doc.get("payer_name"), fields.get("header.payer_name"), fields.get("payer_name")):
        if isinstance(v, str) and v.strip():
            return " ".join(v.split())
    return None


def _da_description(t: dict[str, Any]) -> str | None:
    # Instructions: digital asset name or symbol plus the exact units sold.
    name = t.get("asset_name") or t.get("asset_code")
    units = t.get("units")
    parts = [str(p).strip() for p in (units, name) if p not in (None, "")]
    return " ".join(parts) or None


def load_transactions(con: Any, doc_ids: Sequence[str] | None = None) -> tuple[list[SourceTransaction], list[str]]:
    """Normalized capital-gain transactions for the given documents (None = every 1099-B/DA/consolidated).

    Sources, per document type:
    - 1099-DA: ``extracted_fields`` ``transactions[i].*`` (reflects UI edits), else ``transactions_1099da``,
      else the raw extraction JSON;
    - 1099-B / consolidated-1099: ``transactions_1099b`` lots; a plain 1099-B without lots falls back to
      its single flat extraction (proceeds/basis/term; no dates on that schema).
    Raises ValueError for an unknown document id.
    """

    warnings: list[str] = []
    if doc_ids is None:
        docs = con.execute(
            f"SELECT * FROM documents WHERE doc_type IN ({','.join('?' * len(CAPITAL_DOC_TYPES))}) ORDER BY created_at ASC",
            CAPITAL_DOC_TYPES,
        ).fetchall()
    else:
        docs = []
        for i in doc_ids:
            d = con.execute("SELECT * FROM documents WHERE id=?", (i,)).fetchone()
            if d is None:
                raise ValueError(f"document not found: {i}")
            docs.append(d)

    out: list[SourceTransaction] = []
    for d in docs:
        doc = {k: d[k] for k in d.keys()}
        doc_id, doc_type = doc["id"], doc.get("doc_type")
        if doc_type not in CAPITAL_DOC_TYPES:
            warnings.append(f"document {doc_id} is a {doc_type}, not a 1099-B/1099-DA/consolidated 1099; nothing to export")
            continue
        fields = _fields_by_path(con, doc_id)
        common = dict(
            source_document_id=doc_id,
            source_form=doc_type,
            payer=_payer(doc, fields),
            document_needs_review=bool(doc.get("needs_review")),
        )
        doc_conf = doc.get("overall_confidence")
        before = len(out)

        if doc_type == "1099-DA":
            txns = _da_from_fields(fields)
            if not txns:
                rows = con.execute("SELECT * FROM transactions_1099da WHERE document_id=? ORDER BY rowid", (doc_id,)).fetchall()
                txns = [{k: r[k] for k in r.keys()} for r in rows]
            if not txns:
                ext = _latest_extraction(con, doc_id)
                txns = [t for t in (ext.get("transactions") or []) if isinstance(t, dict)] if isinstance(ext, dict) else []
            for i, t in enumerate(txns):
                conf = t.get("confidence")
                out.append(SourceTransaction(
                    **common,
                    description=_da_description(t),
                    date_acquired=t.get("date_acquired"),
                    date_sold=t.get("date_sold"),
                    proceeds=t.get("proceeds"),
                    cost_basis=t.get("cost_basis"),
                    wash_sale_disallowed=t.get("wash_sale_disallowed"),
                    accrued_market_discount=t.get("accrued_market_discount"),
                    term=t.get("gain_loss_term"),
                    basis_reported_to_irs=t.get("basis_reported_to_irs"),
                    noncovered=t.get("noncovered"),
                    form_8949_box=t.get("form_8949_code"),
                    loss_not_allowed=t.get("loss_not_allowed"),
                    confidence=_float(conf) if _float(conf) is not None else _float(doc_conf),
                    ref=f"transaction {i + 1}",
                ))
        else:
            lots = con.execute("SELECT * FROM transactions_1099b WHERE document_id=? ORDER BY lot_index", (doc_id,)).fetchall()
            for r in lots:
                t = {k: r[k] for k in r.keys()}
                desc = t.get("description")
                if not desc and t.get("quantity"):
                    desc = t.get("quantity")
                out.append(SourceTransaction(
                    **common,
                    description=desc,
                    date_acquired=t.get("date_acquired"),
                    date_sold=t.get("date_sold"),
                    proceeds=t.get("proceeds"),
                    cost_basis=t.get("cost_basis"),
                    wash_sale_disallowed=t.get("wash_sale_loss_disallowed"),
                    accrued_market_discount=t.get("accrued_market_discount"),
                    reported_gain_loss=t.get("gain_loss"),
                    term=t.get("term"),
                    basis_reported_to_irs=t.get("basis_reported_to_irs"),
                    form_8949_box=t.get("form_8949_box"),
                    confidence=_float(doc_conf),
                    ref=f"lot {int(t.get('lot_index') or 0) + 1}" + (f" (page {t['page']})" if t.get("page") else ""),
                ))
            if not lots and doc_type == "1099-B" and fields.get("proceeds"):
                out.append(SourceTransaction(
                    **common,
                    description=fields.get("description"),
                    proceeds=fields.get("proceeds"),
                    cost_basis=fields.get("cost_basis"),
                    wash_sale_disallowed=fields.get("wash_sale_loss_disallowed"),
                    reported_gain_loss=fields.get("gain_loss"),
                    term=fields.get("term"),
                    confidence=_float(doc_conf),
                    ref="single-sale form fields",
                ))
        if len(out) == before:
            warnings.append(f"{doc_type} {doc_id}: no sale transactions found in the extracted data")
    return out, warnings


def _float(v: Any) -> float | None:
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


@dataclass
class Export8949:
    content: str
    rows: int
    needs_review: int
    warnings: list[str]
    notice: str = NOTICE_TEXT


def build_8949(doc_ids: Sequence[str] | None = None, *, generated: str | None = None) -> Export8949:
    with db() as con:
        txns, warnings = load_transactions(con, doc_ids)
    rows = rows_for(txns)
    return Export8949(
        content=render_8949_csv(rows, generated=generated),
        rows=len(rows),
        needs_review=sum(r.needs_review for r in rows),
        warnings=warnings,
    )


def export_8949_csv(doc_ids: Sequence[str] | None = None) -> str:
    """Form 8949-ready CSV for the given document ids (None = all capital-gain documents)."""

    return build_8949(doc_ids).content


def export_txf(doc_ids: Sequence[str] | None = None, *, export_date: date | None = None) -> TxfExport:
    """TXF v042 for the given document ids (None = all). See ``TxfExport.warnings`` for skipped rows."""

    with db() as con:
        txns, warnings = load_transactions(con, doc_ids)
    result = render_txf(rows_for(txns), export_date=export_date)
    result.warnings = warnings + result.warnings
    return result
