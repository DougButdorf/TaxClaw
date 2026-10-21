"""Ingest pipeline shared by the CLI and the MCP server.

validate -> backend ready check -> copy into the data dir -> classify ->
extract -> store fields (with per-field confidence when the backend has it)
-> review flags. Returns a JSON-serializable summary (never file bytes).
"""

from __future__ import annotations

from typing import Any

from .ai import ensure_backend_ready
from .classify import classify_document
from .config import Config
from .db import init_db
from .provenance import parse_processed_by
from .extract import extract_document_with_meta
from .review import compute_needs_review, compute_overall_confidence, missing_required_fields
from .store import (
    create_document_record,
    extract_and_store_1099b_lots,
    get_document,
    get_document_by_hash,
    ingest_file,
    mark_needs_review,
    mark_processed,
    page_count_for_pdf,
    store_1099da_transactions,
    store_extracted_fields,
    store_raw_extraction,
    validate_input_file,
)


class IngestError(RuntimeError):
    """A user-facing ingest failure. ``stage`` is validate|backend|extract."""

    def __init__(self, message: str, *, stage: str, exit_code: int, document_id: str | None = None):
        super().__init__(message)
        self.stage = stage
        self.exit_code = exit_code
        self.document_id = document_id


def document_summary(doc_id: str) -> dict[str, Any]:
    d = get_document(doc_id) or {}
    return {
        "document_id": doc_id,
        "doc_type": d.get("doc_type"),
        "tax_year": d.get("tax_year"),
        "filer": d.get("filer"),
        "status": d.get("status"),
        "needs_review": bool(d.get("needs_review")),
        "overall_confidence": d.get("overall_confidence"),
        "classification_confidence": d.get("classification_confidence"),
        "original_filename": d.get("original_filename"),
        "notes": d.get("notes"),
        # Where the document was read. null only for documents stored before this was recorded.
        "processed_by": parse_processed_by(d.get("processed_by")),
    }


def ingest_path(path: str, cfg: Config, *, filer: str | None = None, tax_year: int | None = None) -> dict[str, Any]:
    """Ingest one file. Raises IngestError; on extraction failure the document is kept and flagged."""

    init_db()
    try:
        validate_input_file(path, cfg)
    except (FileNotFoundError, ValueError) as e:
        raise IngestError(str(e), stage="validate", exit_code=2) from None

    # Fail fast before copying/recording anything if the model backend can't run
    # (Ollama down, text-only local model, cloud privacy not acknowledged, missing key ...).
    try:
        ensure_backend_ready(cfg)
    except Exception as e:  # noqa: BLE001
        raise IngestError(str(e), stage="backend", exit_code=3) from None

    dest_path, file_hash, original_filename, mime_type = ingest_file(path, cfg)
    existing = get_document_by_hash(file_hash)
    if existing:
        out = document_summary(existing["id"])
        out["duplicate"] = True
        return out

    page_count = page_count_for_pdf(dest_path) if dest_path.lower().endswith(".pdf") else 1

    try:
        cls = classify_document(dest_path, cfg)
    except Exception as e:  # noqa: BLE001
        cls = {"doc_type": "unknown", "confidence": 0.0, "error": str(e)}
    doc_type = cls.get("doc_type") or "unknown"
    classification_confidence = float(cls.get("confidence") or 0.0)

    doc_id = create_document_record(
        cfg=cfg,
        file_path=dest_path,
        file_hash=file_hash,
        original_filename=original_filename,
        mime_type=mime_type,
        filer=filer,
        tax_year=tax_year,
        doc_type=doc_type,
        page_count=page_count,
        classification_confidence=classification_confidence,
    )

    try:
        result = extract_document_with_meta(dest_path, doc_type, cfg)
        extracted = result.data
        section_id = store_raw_extraction(doc_id=doc_id, form_type=doc_type, data=extracted, confidence=classification_confidence)
        store_extracted_fields(doc_id=doc_id, section_id=section_id, data=extracted, confidences=result.field_confidence)
        if doc_type == "1099-DA" and isinstance(extracted, dict):
            store_1099da_transactions(doc_id=doc_id, extraction=extracted)
        lot_count, lot_note = extract_and_store_1099b_lots(doc_id=doc_id, file_path=dest_path, doc_type=doc_type, cfg=cfg)

        missing = missing_required_fields(doc_type, extracted)
        overall = compute_overall_confidence(doc_type=doc_type, extraction=extracted, classification_confidence=classification_confidence)
        nr = compute_needs_review(classification_confidence=classification_confidence, overall_confidence=overall, missing_required=missing)
        nr = nr or bool(result.review_fields) or bool(lot_note)
        mark_processed(doc_id=doc_id, overall_confidence=overall, needs_review=nr)
        notes = []
        if missing:
            notes.append(f"missing required fields: {', '.join(missing)}")
        if result.review_fields:
            notes.append(f"low-confidence fields: {', '.join(result.review_fields)}")
        if lot_note:
            notes.append(lot_note)
        if nr and notes:
            mark_needs_review(doc_id=doc_id, notes="; ".join(notes))
    except Exception as e:  # noqa: BLE001
        mark_needs_review(doc_id=doc_id, notes=str(e))
        raise IngestError(f"extraction failed for {doc_id} ({doc_type}): {e}", stage="extract", exit_code=1, document_id=doc_id) from None

    out = document_summary(doc_id)
    out["duplicate"] = False
    out["extraction_method"] = result.method
    out["missing_required"] = missing
    out["low_confidence_fields"] = list(result.review_fields)
    if lot_count is not None:
        out["capital_lots"] = lot_count
    return out
