from __future__ import annotations

import json
from typing import Any

import fitz

from .ai import chat_json_from_image
from .config import Config


def _render_page_png(doc: fitz.Document, page_index: int) -> bytes:
    page = doc[page_index]
    mat = fitz.Matrix(2.0, 2.0)
    pix = page.get_pixmap(matrix=mat)
    return pix.tobytes("png")


PROMPTS: dict[str, str] = {
    "W-2": """You are extracting fields from US IRS Form W-2 (Wage and Tax Statement).
Return JSON only. Do not hallucinate. Use null for missing/blank.

Return object with keys:
{
  "employer_name": string|null,
  "employer_ein": string|null,
  "employee_ssn": string|null,
  "wages": string|null,
  "federal_withheld": string|null,
  "state_wages": string|null,
  "state_withheld": string|null,
  "local_wages": string|null,
  "box_codes": object|null
}

Formatting rules:
- Dollar amounts: string with digits, commas optional, no $ (e.g. "1234.56").
- EIN/TIN/SSN may be masked; preserve as seen.
""",
    "1099-NEC": """You are extracting fields from US IRS Form 1099-NEC.
Return JSON only. Do not hallucinate. Use null for missing/blank.

Keys:
{
  "payer_name": string|null,
  "payer_tin": string|null,
  "recipient_tin": string|null,
  "nonemployee_comp": string|null,
  "federal_withheld": string|null,
  "state_income": string|null
}
""",
    "1099-INT": """You are extracting fields from US IRS Form 1099-INT.
Return JSON only. Do not hallucinate. Use null for missing/blank.

Keys:
{
  "payer_name": string|null,
  "payer_tin": string|null,
  "recipient_tin": string|null,
  "interest_income": string|null,
  "early_withdrawal_penalty": string|null,
  "us_bond_interest": string|null,
  "federal_withheld": string|null,
  "tax_exempt_interest": string|null
}
""",
    "1099-DA": """You are extracting fields from US IRS Form 1099-DA.
Return JSON only. Do not hallucinate. Use null for missing/blank.

Return object:
{
  "header": {
    "payer_name": string|null,
    "payer_tin": string|null,
    "recipient_name": string|null,
    "recipient_tin": string|null,
    "account_number": string|null,
    "tax_year": number|null
  },
  "transactions": [
    {
      "asset_code": string|null,
      "asset_name": string|null,
      "units": string|null,
      "date_acquired": string|null,
      "date_sold": string|null,
      "proceeds": string|null,
      "cost_basis": string|null,
      "accrued_market_discount": string|null,
      "wash_sale_disallowed": string|null,
      "basis_reported_to_irs": boolean|null,
      "proceeds_type": string|null,
      "qof_proceeds": boolean|null,
      "federal_withheld": string|null,
      "loss_not_allowed": boolean|null,
      "gain_loss_term": string|null,
      "cash_only": boolean|null,
      "customer_info_used": boolean|null,
      "noncovered": boolean|null,
      "aggregate_flag": string|null,
      "transaction_count": number|null,
      "nft_first_sale_proceeds": string|null,
      "units_transferred_in": string|null,
      "transfer_in_date": string|null,
      "form_8949_code": string|null,
      "state_name": string|null,
      "state_id": string|null,
      "state_withheld": string|null
    }
  ],
  "is_multi_transaction": boolean
}

Rules:
- For dollar amounts: strings with no $.
- For units: preserve full precision as string.
- For checkbox/radio: use true/false or null if not visible.
- If this page contains exactly one transaction form, return transactions with 1 item.
""",
    "K-1": """You are extracting fields from US IRS Schedule K-1 (Partner's Share of Income, Deductions, Credits, etc.).
Return JSON only. Do not hallucinate. Use null for missing/blank.
This form may span multiple pages — extract every labeled field you can see on this page.

Return object with keys:
{
  "tax_year": string|null,
  "partnership_name": string|null,
  "partnership_ein": string|null,
  "partner_name": string|null,
  "partner_ssn": string|null,
  "partner_type": string|null,
  "profit_sharing_pct": string|null,
  "loss_sharing_pct": string|null,
  "capital_sharing_pct": string|null,
  "ordinary_income": string|null,
  "net_rental_income": string|null,
  "guaranteed_payments": string|null,
  "interest_income": string|null,
  "dividends": string|null,
  "royalties": string|null,
  "net_short_term_gain": string|null,
  "net_long_term_gain": string|null,
  "section_179": string|null,
  "charitable_contributions": string|null,
  "self_employment_earnings": string|null,
  "other_deductions": object|null,
  "other_credits": object|null,
  "beginning_capital": string|null,
  "ending_capital": string|null,
  "capital_contributed": string|null,
  "capital_withdrawn": string|null,
  "foreign_transactions": object|null,
  "amt_items": object|null,
  "other_information": object|null
}

Formatting rules:
- Dollar amounts: string with digits, commas optional, no $.
- Percentages: string as seen (e.g. "33.33%").
- For object fields: map box labels/codes to their values.
""",
    "generic": """Extract any visible labeled fields as key-value pairs.
Return JSON only as an object mapping labels to values.
Do not hallucinate values.
""",
}


def _merge_page_dicts(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """Merge update into base. Only overwrites if the existing value is None or missing."""
    result = dict(base)
    for k, v in update.items():
        if k not in result or result[k] is None:
            result[k] = v
    return result


def extract_document(file_path: str, doc_type: str, cfg: Config) -> dict[str, Any]:
    """LLM extraction.

    For 1099-DA: per-page extraction, transactions aggregated across all pages.
    For all other types (incl. multi-page K-1, W-2, etc.): iterate all pages and
    merge results — later pages fill in fields that were null/missing on earlier pages.
    """

    prompt = PROMPTS.get(doc_type, PROMPTS["generic"])

    doc = fitz.open(file_path)
    try:
        if doc_type == "1099-DA":
            txns: list[dict[str, Any]] = []
            header: dict[str, Any] | None = None
            # Extract each page as a separate form copy when page count >1.
            for i in range(doc.page_count):
                img = _render_page_png(doc, i)
                out = chat_json_from_image(cfg=cfg, prompt=prompt, image_bytes=img)
                if header is None and isinstance(out, dict):
                    header = out.get("header") or {}
                page_txns = (out.get("transactions") or []) if isinstance(out, dict) else []
                if isinstance(page_txns, list):
                    txns.extend(page_txns)

            return {
                "header": header or {},
                "transactions": txns,
                "is_multi_transaction": len(txns) > 1,
            }

        # All other form types: iterate all pages, merge fields
        # (handles multi-page K-1, W-2 copies, etc.)
        merged: dict[str, Any] = {}
        for i in range(doc.page_count):
            img = _render_page_png(doc, i)
            out = chat_json_from_image(cfg=cfg, prompt=prompt, image_bytes=img)
            if isinstance(out, dict):
                merged = _merge_page_dicts(merged, out)
            elif i == 0:
                # First page returned a non-dict (unlikely but safe fallback)
                return out  # type: ignore[return-value]
        return merged
    finally:
        doc.close()


def pretty_json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)
