from __future__ import annotations

import csv
import io
import json
from typing import Any

from .db import db


DOC_BASE_COLS = [
    "document_id",
    "doc_type",
    "tax_year",
    "filer",
    "payer_name",
    "recipient_name",
    "account_number",
    "classification_confidence",
    "overall_confidence",
    "needs_review",
    "created_at",
]


def _doc_row(doc: Any) -> dict[str, Any]:
    """Normalize a sqlite3.Row (or dict) into a plain dict for exports."""
    d = dict(doc)
    return {
        "document_id": d.get("id"),
        "doc_type": d.get("doc_type"),
        "tax_year": d.get("tax_year"),
        "filer": d.get("filer"),
        "payer_name": d.get("payer_name"),
        "recipient_name": d.get("recipient_name"),
        "account_number": d.get("account_number"),
        "classification_confidence": d.get("classification_confidence"),
        "overall_confidence": d.get("overall_confidence"),
        "needs_review": d.get("needs_review"),
        "created_at": d.get("created_at"),
    }


def export_doc_json(doc_id: str) -> str:
    with db() as con:
        doc = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError("document not found")
        ext = con.execute(
            "SELECT raw_json FROM form_extractions WHERE document_id=? ORDER BY created_at DESC LIMIT 1",
            (doc_id,),
        ).fetchone()
        extraction = json.loads(ext[0]) if ext and ext[0] else None
        fields = con.execute(
            "SELECT field_path, field_value, confidence FROM extracted_fields WHERE document_id=? ORDER BY field_path ASC",
            (doc_id,),
        ).fetchall()

    payload = {
        "document": dict(doc),
        "extraction": extraction,
        "extracted_fields": [
            {"field_path": r[0], "field_value": r[1], "confidence": r[2]} for r in fields
        ],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def export_all_json() -> str:
    with db() as con:
        docs = con.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        payload = [dict(d) for d in docs]
    return json.dumps(payload, ensure_ascii=False, indent=2)


def export_doc_csv_long(doc_id: str) -> str:
    with db() as con:
        doc = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError("document not found")
        rows = con.execute(
            "SELECT field_path, field_value, confidence FROM extracted_fields WHERE document_id=? ORDER BY field_path ASC",
            (doc_id,),
        ).fetchall()

    buf = io.StringIO()
    headers = DOC_BASE_COLS + ["field_path", "field_value", "confidence"]
    w = csv.DictWriter(buf, fieldnames=headers)
    w.writeheader()

    base = _doc_row(doc)
    for r in rows:
        out = dict(base)
        out.update({"field_path": r[0], "field_value": r[1], "confidence": r[2]})
        w.writerow(out)
    return buf.getvalue()


def export_all_csv_long() -> str:
    buf = io.StringIO()
    headers = DOC_BASE_COLS + ["field_path", "field_value", "confidence"]
    w = csv.DictWriter(buf, fieldnames=headers)
    w.writeheader()

    with db() as con:
        docs = con.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        for d in docs:
            base = _doc_row(d)
            rows = con.execute(
                "SELECT field_path, field_value, confidence FROM extracted_fields WHERE document_id=? ORDER BY field_path ASC",
                (d["id"],),
            ).fetchall()
            if not rows:
                w.writerow({**base, "field_path": "", "field_value": "", "confidence": ""})
            for r in rows:
                w.writerow({**base, "field_path": r[0], "field_value": r[1], "confidence": r[2]})

    return buf.getvalue()


def export_doc_csv_wide(doc_id: str) -> str:
    with db() as con:
        doc = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError("document not found")
        fields = con.execute(
            "SELECT field_path, field_value FROM extracted_fields WHERE document_id=? ORDER BY field_path ASC",
            (doc_id,),
        ).fetchall()

    flat: dict[str, Any] = _doc_row(doc)
    for r in fields:
        key = r[0]
        flat[key] = r[1]

    headers = list(flat.keys())
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=headers)
    w.writeheader()
    w.writerow(flat)
    return buf.getvalue()


def export_all_csv_wide() -> str:
    # wide export: union of all field paths across docs
    with db() as con:
        docs = con.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
        all_paths: set[str] = set()
        for d in docs:
            rows = con.execute(
                "SELECT field_path FROM extracted_fields WHERE document_id=?",
                (d["id"],),
            ).fetchall()
            for r in rows:
                all_paths.add(r[0])

    headers = DOC_BASE_COLS + sorted(all_paths)
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=headers)
    w.writeheader()

    with db() as con:
        for d in docs:
            out: dict[str, Any] = {h: "" for h in headers}
            out.update(_doc_row(d))
            rows = con.execute(
                "SELECT field_path, field_value FROM extracted_fields WHERE document_id=?",
                (d["id"],),
            ).fetchall()
            for r in rows:
                out[r[0]] = r[1]
            w.writerow(out)

    return buf.getvalue()
