from __future__ import annotations

import csv
import io
import json
from typing import Any

from .db import db


def _flatten(prefix: str, obj: Any, out: dict[str, str]) -> None:
    if obj is None:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            _flatten(f"{prefix}{k}.", v, out)
    elif isinstance(obj, list):
        out[prefix[:-1]] = json.dumps(obj, ensure_ascii=False)
    else:
        out[prefix[:-1]] = str(obj)


def export_doc_csv(doc_id: str) -> str:
    """Returns CSV string.

    For 1099-DA with transactions, exports one row per transaction.
    Otherwise exports one row per document (flattened fields).
    """
    with db() as con:
        doc = con.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not doc:
            raise ValueError("document not found")

        doc_type = doc["doc_type"]

        if doc_type == "1099-DA":
            txns = con.execute(
                "SELECT * FROM transactions_1099da WHERE document_id=? ORDER BY rowid ASC", (doc_id,)
            ).fetchall()
            headers = [
                "document_id",
                "tax_year",
                "filer",
                "asset_name",
                "asset_code",
                "units",
                "date_acquired",
                "date_sold",
                "proceeds",
                "cost_basis",
                "gain_loss_term",
                "form_8949_code",
                "noncovered",
            ]
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=headers)
            w.writeheader()
            for t in txns:
                w.writerow(
                    {
                        "document_id": doc_id,
                        "tax_year": doc["tax_year"],
                        "filer": doc["filer"],
                        "asset_name": t["asset_name"],
                        "asset_code": t["asset_code"],
                        "units": t["units"],
                        "date_acquired": t["date_acquired"],
                        "date_sold": t["date_sold"],
                        "proceeds": t["proceeds"],
                        "cost_basis": t["cost_basis"],
                        "gain_loss_term": t["gain_loss_term"],
                        "form_8949_code": t["form_8949_code"],
                        "noncovered": t["noncovered"],
                    }
                )
            return buf.getvalue()

        # other docs: flatten latest extraction
        ext = con.execute(
            """SELECT raw_json FROM form_extractions
               WHERE document_id=?
               ORDER BY created_at DESC
               LIMIT 1""",
            (doc_id,),
        ).fetchone()
        extracted = json.loads(ext[0]) if ext and ext[0] else {}

        flat: dict[str, str] = {
            "document_id": doc_id,
            "doc_type": doc_type,
            "tax_year": str(doc["tax_year"] or ""),
            "filer": str(doc["filer"] or ""),
        }
        _flatten("", extracted, flat)

        headers = sorted(flat.keys())
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=headers)
        w.writeheader()
        w.writerow(flat)
        return buf.getvalue()


def export_all_csv() -> str:
    with db() as con:
        docs = con.execute("SELECT id FROM documents ORDER BY created_at DESC").fetchall()
    # naive concatenation: header from each doc may differ; keep minimal common set.
    # For now, output one row per document (metadata only).
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["document_id", "doc_type", "tax_year", "filer", "created_at", "status"])
    w.writeheader()
    with db() as con:
        for r in docs:
            d = con.execute("SELECT * FROM documents WHERE id=?", (r[0],)).fetchone()
            if not d:
                continue
            w.writerow(
                {
                    "document_id": d["id"],
                    "doc_type": d["doc_type"],
                    "tax_year": d["tax_year"],
                    "filer": d["filer"],
                    "created_at": d["created_at"],
                    "status": d["status"],
                }
            )
    return buf.getvalue()
