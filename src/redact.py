"""Mask taxpayer identifiers in data returned to an agent.

Whatever a tool returns goes into the agent's model context, wherever that model runs.
The MCP tools mask SSNs, TINs, EINs and account numbers by default (``redact_identifiers``);
CLI exports and the web UI are unchanged.

A field is an identifier when any segment of its path has an ``ssn``, ``tin``, ``ein`` (or
``itin``/``fein``) word, or contains ``account_number``/``accountnumber``: ``employee_ssn``,
``payer_tin``, ``header.employer_ein``, ``account_number``. Matching is by word, so
``reinvested`` or ``accounting`` are not masked. Values keep their last four letters/digits
and their punctuation: ``123-45-6789`` -> ``***-**-6789``.
"""

from __future__ import annotations

import csv
import io
import re
from typing import Any

_ID_WORDS = {"ssn", "tin", "ein", "itin", "fein"}
_WORD_SPLIT = re.compile(r"[^a-z0-9]+")


def is_identifier_key(path: str | None) -> bool:
    if not path:
        return False
    p = str(path).lower()
    if "account_number" in p or "accountnumber" in p:
        return True
    return any(w in _ID_WORDS for w in _WORD_SPLIT.split(p))


def mask_value(value: Any) -> Any:
    """Mask every letter/digit except the last four; None and empty values pass through."""

    if value is None or isinstance(value, bool):
        return value
    s = str(value)
    alnum = [i for i, ch in enumerate(s) if ch.isalnum()]
    if not alnum:
        return value
    keep = set(alnum[-4:]) if len(alnum) > 4 else set()
    return "".join(ch if (i in keep or not ch.isalnum()) else "*" for i, ch in enumerate(s))


def redact_obj(obj: Any, _masking: bool = False) -> Any:
    """Copy of a JSON-like value with identifier fields masked (recursively)."""

    if isinstance(obj, dict):
        out = {k: redact_obj(v, _masking or is_identifier_key(str(k))) for k, v in obj.items()}
        # Stored field rows: {"field_path": "employee_ssn", "field_value": "123-45-6789", ...}
        if "field_path" in out and "field_value" in out and is_identifier_key(out.get("field_path")):
            out["field_value"] = mask_value(out["field_value"])
        return out
    if isinstance(obj, list):
        return [redact_obj(v, _masking) for v in obj]
    return mask_value(obj) if _masking else obj


def redact_json_text(content: str) -> str:
    """A TaxClaw JSON export (string) with identifiers masked, in the same layout."""

    import json

    return json.dumps(redact_obj(json.loads(content)), ensure_ascii=False, indent=2)


def redact_csv(content: str) -> str:
    """Mask identifier columns (wide CSV) and identifier rows (long CSV: field_path/field_value).

    Leading ``#`` notice lines are kept as they are.
    """

    lines = content.splitlines(keepends=True)
    head: list[str] = []
    while lines and lines[0].startswith("#"):
        head.append(lines.pop(0))
    body = "".join(lines)
    if not body.strip():
        return content
    reader = csv.DictReader(io.StringIO(body, newline=""))
    headers = reader.fieldnames or []
    id_cols = [h for h in headers if is_identifier_key(h)]
    long_form = "field_path" in headers and "field_value" in headers
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=headers)
    w.writeheader()
    for row in reader:
        for h in id_cols:
            row[h] = mask_value(row.get(h)) if row.get(h) else row.get(h)
        if long_form and is_identifier_key(row.get("field_path")) and row.get("field_value"):
            row["field_value"] = mask_value(row["field_value"])
        w.writerow(row)
    return "".join(head) + buf.getvalue()
