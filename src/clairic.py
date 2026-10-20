"""Cloudflare Workers AI Clairic adapter (``@cf/cloudflare/clairic``).

Clairic is a typed-field model: the request names each field with a type
(text, number, date, list, ...) and the response returns, per field,
``value``, ``confidence``, ``p_null`` and a ``span`` into the input text.
Docs: https://developers.cloudflare.com/workers-ai/models/clairic/

This module maps each form's PROMPTS schema to Clairic fields:

- money          -> number, 2 decimals, unit USD (returned as "1234.56" strings,
                    matching the LLM path)
- TINs, names, codes, ids, years, percentages -> text
- dates          -> date
- checkboxes     -> integer number (1 checked / 0 unchecked) -> true/false
- coded objects  -> list of text "CODE=AMOUNT" -> {"CODE": "AMOUNT"} (K-1 boxes, W-2 box 12)
- 1099-DA transaction tables are NOT sent to Clairic (Cloudflare notes it is
  weak at many-row aggregation); extract.py runs them through the fallback
  LLM backend and keeps Clairic's header fields.

Per-field confidence fills ``extracted_fields.confidence``; a field is flagged
for review when its value is present with confidence below the threshold
(default 0.8) or when ``p_null`` is ambiguous (between 0.2 and 0.8).
Pages: at most 4 images per call (4 MiB each, 8 MiB total decoded); longer
documents are sent in batches and merged (first non-null value wins).

Status: unit-tested against the documented request/response schema with a
mocked HTTP response; not live-tested.
"""

from __future__ import annotations

import base64
import io
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .backends import ExtractionResult, image_mime

MAX_IMAGES_PER_CALL = 4
MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_BATCH_BYTES = int(7.5 * 1024 * 1024)  # documented cap is 8 MiB decoded per request
P_NULL_REVIEW_BAND = (0.2, 0.8)

# Forms Clairic handles directly. Anything else (generic, 1040, unknown) uses
# the fallback LLM backend.
_TABLE_ONLY_KEYS = {"transactions", "is_multi_transaction"}

_MONTHS = {
    "january", "february", "march", "april", "may", "june", "july",
    "august", "september", "october", "november", "december",
}
_TEXT_TOKENS = {
    "name", "tin", "ssn", "ein", "id", "code", "codes", "account", "locality", "country", "description",
    "cusip", "year", "pct", "percent", "type", "flag", "units", "number", "state",
}
_DATE_TOKENS = {"date"}
_MONEY_TOKENS = {
    "wages", "withheld", "comp", "compensation", "income", "interest", "dividends", "gain", "gains", "loss",
    "proceeds", "basis", "distribution", "distributions", "amount", "payments", "penalty", "discount",
    "premium", "contributions", "contributed", "withdrawn", "royalties", "rents", "refunds", "grants",
    "deferrals", "deferred", "liquidation", "paid", "capital", "179", "earnings", "gross", "present",
    "appreciation", "allocable", "disallowed", "insurance", "treasury", "oid", "expenses",
}
# Explicit overrides where token rules would guess wrong.
_KIND_OVERRIDES = {
    "number_of_transactions": "integer",
    "transaction_count": "integer",
    "state_income": "money",
    "state_wages": "money",
    "state_withheld": "money",
    "state_distribution": "money",
    "state_local_tax_refunds": "money",
    "term": "text",
    "gain_loss_term": "text",
}

_FORM_TYPE_FIELD = "form_type"
_KEY_COMMENT_RE = re.compile(r'"([A-Za-z0-9_]+)"\s*:\s*[a-z|]+,?\s*//\s*(.+)$', re.M)


@dataclass
class FieldPlan:
    path: str  # dotted path in the extraction dict ("wages", "header.payer_name")
    kind: str  # money|text|date|integer|number|flag|coded
    json_types: tuple[str, ...]  # from the PROMPTS schema


def field_kind(key: str, json_types: list[str] | tuple[str, ...]) -> str:
    types = set(json_types)
    if key in _KIND_OVERRIDES:
        return _KIND_OVERRIDES[key]
    if "boolean" in types:
        return "flag"
    if "object" in types:
        return "coded"
    if "number" in types:
        return "integer" if any(t in key for t in ("year", "count")) else "number"
    tokens = set(key.lower().split("_"))
    if key.lower() in _MONTHS:
        return "money"
    if tokens & _TEXT_TOKENS:
        return "text"
    if tokens & _DATE_TOKENS:
        return "date"
    if tokens & _MONEY_TOKENS:
        return "money"
    return "text"


def _hints_from_prompt(prompt: str) -> dict[str, str]:
    return {k: c.strip() for k, c in _KEY_COMMENT_RE.findall(prompt or "")}


def _humanize(key: str) -> str:
    return key.replace("_", " ")


def _instructions(form: str, key: str, kind: str, hint: str | None) -> str:
    base = f"{form}: {hint or _humanize(key)}."
    if kind == "money":
        return base + " Dollar amount as printed; null if blank."
    if kind == "flag":
        return base + " 1 if the checkbox is checked, 0 if it is visibly unchecked; null if not shown."
    if kind == "coded":
        return (
            base
            + " One item per code shown, written as CODE=AMOUNT (for example W=1250.00 or 13W=1250.00); "
            "empty list if none."
        )
    if kind in ("integer", "number"):
        return base + " Number as printed; null if blank."
    return base + " Copy exactly as printed (masked digits stay masked); null if blank."


def _spec_for(kind: str, instructions: str) -> dict[str, Any]:
    if kind == "money":
        return {"type": "number", "decimals": 2, "unit": "USD", "instructions": instructions}
    if kind == "flag":
        return {"type": "number", "integer": True, "instructions": instructions}
    if kind == "integer":
        return {"type": "number", "integer": True, "instructions": instructions}
    if kind == "number":
        return {"type": "number", "instructions": instructions}
    if kind == "date":
        return {"type": "date", "instructions": instructions}
    if kind == "coded":
        return {"type": "list", "items": "text", "instructions": instructions}
    return {"type": "text", "instructions": instructions}


def supports_doc_type(doc_type: str) -> bool:
    from .extract import schema_for

    return doc_type not in ("generic", "1040", "unknown") and schema_for(doc_type) is not None


def build_fields(doc_type: str) -> tuple[dict[str, dict[str, Any]], dict[str, FieldPlan]]:
    """Map a form's PROMPTS schema to Clairic ``fields`` plus a conversion plan."""

    from .extract import PROMPTS, schema_for

    schema = schema_for(doc_type)
    if not schema:
        raise ValueError(f"no schema for {doc_type}")
    hints = _hints_from_prompt(PROMPTS.get(doc_type, ""))
    form = f"IRS Form {doc_type}" if not doc_type.startswith("K-1") else "Schedule K-1 (Form 1065)"

    fields: dict[str, dict[str, Any]] = {}
    plan: dict[str, FieldPlan] = {}

    def add(prefix: str, props: dict[str, Any]) -> None:
        for key, prop in props.items():
            if key in _TABLE_ONLY_KEYS:
                continue
            json_types = prop.get("type") or ["string", "null"]
            if isinstance(json_types, str):
                json_types = [json_types]
            if prop.get("properties") and "object" in json_types and key == "header":
                add(f"{prefix}{key}.", prop["properties"])
                continue
            kind = field_kind(key, json_types)
            name = f"{prefix}{key}"
            fields[name] = _spec_for(kind, _instructions(form, key, kind, hints.get(key)))
            plan[name] = FieldPlan(path=name, kind=kind, json_types=tuple(json_types))

    add("", schema.get("properties") or {})
    return fields, plan


_CODED_ITEM_RE = re.compile(r"^\s*([A-Za-z0-9 ]{1,12}?)\s*[=:\-]\s*(.+?)\s*$")


def _convert(value: Any, fp: FieldPlan) -> Any:
    if value is None:
        return None
    k = fp.kind
    if k == "money":
        if isinstance(value, (int, float)):
            return f"{float(value):.2f}"
        return str(value)
    if k == "flag":
        try:
            return bool(int(round(float(value))))
        except (TypeError, ValueError):
            return None
    if k in ("integer", "number"):
        if "number" in fp.json_types:
            if isinstance(value, float) and value.is_integer() and k == "integer":
                return int(value)
            return value
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return str(value)
    if k == "coded":
        items = value if isinstance(value, list) else [value]
        out: dict[str, Any] = {}
        for item in items:
            m = _CODED_ITEM_RE.match(str(item))
            if m:
                out[m.group(1).replace(" ", "").upper()] = m.group(2)
        return out or None
    return str(value) if not isinstance(value, str) else value


def _set_path(data: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur = data
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value


def needs_review(answer: dict[str, Any], threshold: float) -> bool:
    value = answer.get("value")
    conf = answer.get("confidence")
    p_null = answer.get("p_null")
    if value is not None and isinstance(conf, (int, float)) and conf < threshold:
        return True
    if isinstance(p_null, (int, float)) and P_NULL_REVIEW_BAND[0] < p_null < P_NULL_REVIEW_BAND[1]:
        return True
    return False


def convert_answers(
    answers: dict[str, Any], plan: dict[str, FieldPlan], *, threshold: float
) -> ExtractionResult:
    data: dict[str, Any] = {}
    conf: dict[str, float] = {}
    review: list[str] = []
    for name, fp in plan.items():
        ans = answers.get(name)
        if not isinstance(ans, dict):
            _set_path(data, fp.path, None)
            continue
        _set_path(data, fp.path, _convert(ans.get("value"), fp))
        c = ans.get("confidence")
        if isinstance(c, (int, float)):
            conf[fp.path] = float(c)
        if needs_review(ans, threshold):
            review.append(fp.path)
    return ExtractionResult(data=data, field_confidence=conf, review_fields=review, method="clairic")


def _fit_image(png: bytes) -> bytes:
    """Keep each image under Clairic's 4 MiB cap (re-encode as JPEG if needed)."""

    if len(png) <= MAX_IMAGE_BYTES:
        return png
    from PIL import Image

    img = Image.open(io.BytesIO(png)).convert("RGB")
    for quality, scale in ((85, 1.0), (75, 0.75), (65, 0.5)):
        im = img if scale == 1.0 else img.resize((int(img.width * scale), int(img.height * scale)))
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= MAX_IMAGE_BYTES:
            return buf.getvalue()
    raise ValueError("page image is too large for Clairic even after re-encoding")


def batch_pages(pages: list[tuple[bytes, str]]) -> list[list[tuple[bytes, str]]]:
    """Group pages into calls of at most 4 images and ~7.5 MiB."""

    batches: list[list[tuple[bytes, str]]] = []
    cur: list[tuple[bytes, str]] = []
    cur_bytes = 0
    for img, text in pages:
        img = _fit_image(img)
        if cur and (len(cur) >= MAX_IMAGES_PER_CALL or cur_bytes + len(img) > MAX_BATCH_BYTES):
            batches.append(cur)
            cur, cur_bytes = [], 0
        cur.append((img, text))
        cur_bytes += len(img)
    if cur:
        batches.append(cur)
    return batches


def build_request(fields: dict[str, Any], batch: list[tuple[bytes, str]]) -> dict[str, Any]:
    state_parts = [f"--- page {i + 1} ---\n{t.strip()}" for i, (_img, t) in enumerate(batch) if (t or "").strip()]
    return {
        "model": "clairic",
        "state": "\n\n".join(state_parts),
        "fields": fields,
        "images": [
            {"content_type": image_mime(img), "base64": base64.b64encode(img).decode("ascii")} for img, _t in batch
        ],
    }


def _merge_answers(per_batch: list[dict[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    for answers in per_batch:
        for name, ans in answers.items():
            if not isinstance(ans, dict):
                continue
            prev = merged.get(name)
            if prev is None or (prev.get("value") in (None, [], "") and ans.get("value") not in (None, [], "")):
                merged[name] = ans
    return merged


def extract_with_clairic(
    *,
    doc_type: str,
    pages: list[tuple[bytes, str]],
    run: Callable[[dict[str, Any]], dict[str, Any]],
    threshold: float = 0.8,
) -> ExtractionResult:
    fields, plan = build_fields(doc_type)
    per_batch = [run(build_request(fields, batch))["answers"] for batch in batch_pages(pages)]
    return convert_answers(_merge_answers(per_batch), plan, threshold=threshold)


def normalize_form_type(raw: Any) -> str | None:
    from .classify import DOC_TYPES

    if not isinstance(raw, str) or not raw.strip():
        return None
    s = raw.upper().replace("FORM", " ").replace("SCHEDULE", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if "CONSOLIDATED" in s or "COMPOSITE" in s:
        return "consolidated-1099"
    compact = s.replace(" ", "").replace("–", "-")
    for t in sorted((d for d in DOC_TYPES if d not in ("unknown", "consolidated-1099")), key=len, reverse=True):
        if t.replace("-", "") in compact.replace("-", ""):
            return t
    return None


def classify_with_clairic(*, image_bytes: bytes, run: Callable[[dict[str, Any]], dict[str, Any]]) -> dict[str, Any]:
    fields = {
        _FORM_TYPE_FIELD: {
            "type": "text",
            "instructions": (
                "The US tax form number printed on this document, e.g. W-2, 1099-INT, 1099-DA, 1099-R, "
                "Schedule K-1, 1040, or 'Consolidated 1099' for a combined brokerage statement."
            ),
        }
    }
    out = run(build_request(fields, [(_fit_image(image_bytes), "")]))
    ans = (out.get("answers") or {}).get(_FORM_TYPE_FIELD) or {}
    doc_type = normalize_form_type(ans.get("value"))
    conf = ans.get("confidence")
    return {
        "doc_type": doc_type or "unknown",
        "confidence": float(conf) if isinstance(conf, (int, float)) and doc_type else 0.3,
        "method": "clairic",
    }
