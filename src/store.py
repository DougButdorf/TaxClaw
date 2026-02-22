from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz

from .config import Config
from .db import db, json_dumps, row_to_dict


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def ingest_file(src_path: str, cfg: Config) -> tuple[str, str, str]:
    """Copy to uploads dir and return (dest_path, file_hash, original_filename)."""
    file_hash = sha256_file(src_path)
    original_filename = os.path.basename(src_path)
    dest_name = f"{file_hash[:12]}_{original_filename}"
    dest_path = str(cfg.uploads_dir / dest_name)
    if not os.path.exists(dest_path):
        shutil.copy2(src_path, dest_path)
    return dest_path, file_hash, original_filename


def create_document_record(*, cfg: Config, file_path: str, file_hash: str, original_filename: str, filer: str | None, tax_year: int | None, doc_type: str, page_count: int) -> str:
    doc_id = str(uuid.uuid4())
    with db() as con:
        con.execute(
            """INSERT INTO documents (id, file_path, file_hash, original_filename, tax_year, doc_type, filer, page_count, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'processing')""",
            (doc_id, file_path, file_hash, original_filename, tax_year, doc_type, filer, page_count),
        )
    return doc_id


def get_document_by_hash(file_hash: str) -> dict[str, Any] | None:
    with db() as con:
        r = con.execute("SELECT * FROM documents WHERE file_hash = ?", (file_hash,)).fetchone()
        return row_to_dict(r)


def get_document(doc_id: str) -> dict[str, Any] | None:
    with db() as con:
        r = con.execute("SELECT * FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return row_to_dict(r)


def list_documents(*, filer: str | None = None, year: int | None = None, doc_type: str | None = None) -> list[dict[str, Any]]:
    q = "SELECT * FROM documents WHERE 1=1"
    params: list[Any] = []
    if filer:
        q += " AND filer = ?"
        params.append(filer)
    if year:
        q += " AND tax_year = ?"
        params.append(year)
    if doc_type:
        q += " AND doc_type = ?"
        params.append(doc_type)
    q += " ORDER BY created_at DESC"
    with db() as con:
        rows = con.execute(q, tuple(params)).fetchall()
        return [row_to_dict(r) for r in rows if r is not None]  # type: ignore


def store_extraction(*, doc_id: str, form_type: str, data: Any, confidence: float | None = None) -> None:
    with db() as con:
        con.execute(
            "INSERT INTO form_extractions (id, document_id, form_type, raw_json, confidence) VALUES (?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), doc_id, form_type, json_dumps(data), confidence),
        )


def store_1099da_transactions(*, doc_id: str, extraction: dict[str, Any]) -> None:
    txns = extraction.get("transactions") or []
    if not isinstance(txns, list):
        return
    with db() as con:
        for t in txns:
            if not isinstance(t, dict):
                continue
            con.execute(
                """INSERT INTO transactions_1099da (
                    id, document_id, asset_code, asset_name, units, date_acquired, date_sold,
                    proceeds, cost_basis, accrued_market_discount, wash_sale_disallowed,
                    basis_reported_to_irs, proceeds_type, qof_proceeds, federal_withheld,
                    loss_not_allowed, gain_loss_term, cash_only, customer_info_used,
                    noncovered, aggregate_flag, transaction_count, nft_first_sale_proceeds,
                    units_transferred_in, transfer_in_date, form_8949_code, state_name,
                    state_id, state_withheld, confidence, raw_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    str(uuid.uuid4()),
                    doc_id,
                    t.get("asset_code"),
                    t.get("asset_name"),
                    t.get("units"),
                    t.get("date_acquired"),
                    t.get("date_sold"),
                    t.get("proceeds"),
                    t.get("cost_basis"),
                    t.get("accrued_market_discount"),
                    t.get("wash_sale_disallowed"),
                    _bool_to_int(t.get("basis_reported_to_irs")),
                    t.get("proceeds_type"),
                    _bool_to_int(t.get("qof_proceeds")),
                    t.get("federal_withheld"),
                    _bool_to_int(t.get("loss_not_allowed")),
                    t.get("gain_loss_term"),
                    _bool_to_int(t.get("cash_only")),
                    _bool_to_int(t.get("customer_info_used")),
                    _bool_to_int(t.get("noncovered")),
                    t.get("aggregate_flag"),
                    t.get("transaction_count"),
                    t.get("nft_first_sale_proceeds"),
                    t.get("units_transferred_in"),
                    t.get("transfer_in_date"),
                    t.get("form_8949_code"),
                    t.get("state_name"),
                    t.get("state_id"),
                    t.get("state_withheld"),
                    t.get("confidence"),
                    json_dumps(t),
                ),
            )


def mark_processed(*, doc_id: str, overall_confidence: float | None = None, notes: str | None = None) -> None:
    with db() as con:
        con.execute(
            """UPDATE documents
               SET status='processed', extracted_at=?, overall_confidence=COALESCE(?, overall_confidence), notes=COALESCE(?, notes)
               WHERE id=?""",
            (datetime.utcnow().isoformat(timespec="seconds"), overall_confidence, notes, doc_id),
        )


def delete_document(doc_id: str) -> None:
    with db() as con:
        # fetch file_path for cleanup
        r = con.execute("SELECT file_path FROM documents WHERE id=?", (doc_id,)).fetchone()
        file_path = r[0] if r else None
        con.execute("DELETE FROM transactions_1099da WHERE document_id=?", (doc_id,))
        con.execute("DELETE FROM form_extractions WHERE document_id=?", (doc_id,))
        con.execute("DELETE FROM documents WHERE id=?", (doc_id,))

    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass


def page_count_for_pdf(path: str) -> int:
    doc = fitz.open(path)
    try:
        return doc.page_count
    finally:
        doc.close()


def _bool_to_int(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, (int, float)):
        return 1 if v else 0
    return None
