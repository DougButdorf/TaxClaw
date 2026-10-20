"""TaxClaw local MCP server (stdio).

Run with ``taxclaw mcp`` (or ``bin/taxclaw mcp``). Uses whatever backend
~/.config/taxclaw/config.yaml selects (local Ollama by default). Tools:

- ingest_document(path, filer?, tax_year?)
- list_documents(filer?, tax_year?, doc_type?, needs_review?)
- get_document(document_id)
- export_documents(document_id? | all, format)
- list_models()

Safety:
- ingest reads only the explicit absolute path it is given, which must be an
  existing regular file of an allowed type (PDF/PNG/JPEG/TIFF/WebP) within
  ``max_upload_bytes``; the same validators as web uploads apply;
- tools never return original file bytes (only extracted data and metadata);
- nothing but protocol messages is written to stdout (the SDK diverts fd 1 to
  stderr while serving; this module never prints);
- cloud backends still require ``privacy_acknowledged: true``.

Not tax advice: TaxClaw extracts data from documents; it does not prepare or
file returns. Verify extracted values against the original documents.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import Field

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from .config import load_config
from .db import init_db

SERVER_INSTRUCTIONS = (
    "TaxClaw turns tax documents (W-2, 1099 variants, 1099-DA, K-1, consolidated 1099s) into structured data "
    "stored locally. Typical flow: list_models (check the backend is ready) -> ingest_document(path) -> "
    "list_documents(needs_review=true) to find items a human should check -> get_document for fields and "
    "confidence -> export_documents. Extraction is local by default; cloud backends only run after the user "
    "has acknowledged the privacy warning in TaxClaw settings. TaxClaw does not prepare or file returns and "
    "is not tax advice; always verify values against the original document."
)

mcp = MCPServer(name="taxclaw", instructions=SERVER_INSTRUCTIONS, log_level="WARNING")

_DOC_KEYS = (
    "id", "doc_type", "tax_year", "filer", "status", "needs_review", "overall_confidence",
    "classification_confidence", "original_filename", "display_name", "payer_name", "page_count",
    "created_at", "extracted_at", "notes",
)


def _doc_public(d: dict[str, Any]) -> dict[str, Any]:
    out = {k: d.get(k) for k in _DOC_KEYS}
    out["needs_review"] = bool(out.get("needs_review"))
    return out


@mcp.tool(
    title="Ingest a tax document",
    description=(
        "Classify and extract one tax document (PDF, PNG, JPEG, TIFF or WebP) from an absolute local file path, "
        "and store the structured fields in TaxClaw's local database. Uses the backend configured in TaxClaw "
        "(local Ollama by default). Returns the document id, detected form type, confidence and whether it needs "
        "human review. Re-ingesting the same file returns the existing document (duplicate=true). Takes ~30-120 s "
        "per page on a local model."
    ),
)
def ingest_document(
    path: Annotated[str, Field(description="Absolute path to the document file on this machine (~ is expanded).")],
    filer: Annotated[str | None, Field(description="Optional label for whose document this is, e.g. 'doug'.")] = None,
    tax_year: Annotated[int | None, Field(description="Optional tax year, e.g. 2025.", ge=1990, le=2100)] = None,
) -> dict[str, Any]:
    from .pipeline import IngestError, ingest_path

    p = Path(os.path.expanduser(path))
    if not p.is_absolute():
        raise ToolError("path must be absolute (the server does not resolve paths against its own working directory)")
    cfg = load_config()
    try:
        return ingest_path(str(p), cfg, filer=filer, tax_year=tax_year)
    except IngestError as e:
        prefix = {"validate": "invalid file", "backend": "backend not ready", "extract": "extraction failed"}[e.stage]
        suffix = f" (document_id={e.document_id}, flagged for review)" if e.document_id else ""
        raise ToolError(f"{prefix}: {e}{suffix}") from None


@mcp.tool(
    title="List stored documents",
    description="List documents in TaxClaw's local database, newest first, optionally filtered. Metadata only.",
)
def list_documents(
    filer: Annotated[str | None, Field(description="Only documents with this filer label.")] = None,
    tax_year: Annotated[int | None, Field(description="Only this tax year.")] = None,
    doc_type: Annotated[str | None, Field(description="Only this form type, e.g. 'W-2', '1099-INT', 'K-1'.")] = None,
    needs_review: Annotated[bool | None, Field(description="true = only documents flagged for human review; false = only unflagged.")] = None,
) -> dict[str, Any]:
    from .store import list_documents as _list

    init_db()
    docs = _list(
        filer=filer,
        year=tax_year,
        doc_type=doc_type,
        needs_review=None if needs_review is None else int(needs_review),
    )
    return {"count": len(docs), "documents": [_doc_public(d) for d in docs]}


@mcp.tool(
    title="Get one document's extracted fields",
    description=(
        "Return a document's metadata and every extracted field (field_path, field_value, confidence). "
        "confidence is per-field when the backend provides it (Cloudflare Clairic) and null otherwise; "
        "overall_confidence and needs_review are always set. Never returns the original file."
    ),
)
def get_document(
    document_id: Annotated[str, Field(description="Document id from ingest_document or list_documents.")],
) -> dict[str, Any]:
    from .db import db
    from .store import get_document as _get

    init_db()
    d = _get(document_id)
    if not d:
        raise ToolError(f"document not found: {document_id}")
    with db() as con:
        rows = con.execute(
            "SELECT field_path, field_value, confidence FROM extracted_fields WHERE document_id=? ORDER BY field_path ASC",
            (document_id,),
        ).fetchall()
        raw = con.execute(
            "SELECT raw_json FROM form_extractions WHERE document_id=? ORDER BY created_at DESC LIMIT 1",
            (document_id,),
        ).fetchone()
    extraction = None
    if raw and raw[0]:
        try:
            extraction = json.loads(raw[0])
        except Exception:  # noqa: BLE001
            extraction = None
    return {
        "document": _doc_public(d),
        "fields": [{"field_path": r[0], "field_value": r[1], "confidence": r[2]} for r in rows],
        "extraction": extraction,
        "notice": "Extracted by AI; verify against the original document. Not tax advice.",
    }


@mcp.tool(
    title="Export documents",
    description=(
        "Export one document (document_id) or all documents (all=true) as a string in the chosen format: "
        "json (documents with extracted fields), wide_csv (one row per document), long_csv "
        "(one row per field), 8949_csv (Form 8949-ready CSV, one row per sale from 1099-B, consolidated 1099 "
        "and 1099-DA documents, with the check-box category and needs_review per row) or txf (TXF v042 for "
        "desktop tax software import; 1099-DA rows and rows missing basis/dates are skipped and listed in "
        "warnings). Returns the content, never the original files. AI-extracted data; not tax advice."
    ),
)
def export_documents(
    format: Annotated[
        Literal["json", "wide_csv", "long_csv", "8949_csv", "txf"], Field(description="Output format.")
    ] = "json",
    document_id: Annotated[str | None, Field(description="Export only this document.")] = None,
    all: Annotated[bool, Field(description="Export every document. Set this or document_id.")] = False,  # noqa: A002
) -> dict[str, Any]:
    from . import exporter
    from .store import get_document as _get

    init_db()
    if bool(document_id) == bool(all):
        raise ToolError("set exactly one of document_id or all=true")
    if document_id and not _get(document_id):
        raise ToolError(f"document not found: {document_id}")
    if format in ("8949_csv", "txf"):
        from .accountant_exports import NOTICE_TEXT, build_8949, export_txf

        ids = None if all else [document_id]
        if format == "8949_csv":
            res = build_8949(ids)
            extra = {"rows": res.rows, "rows_needing_review": res.needs_review, "content_type": "text/csv"}
        else:
            res = export_txf(ids)
            extra = {"records": res.records, "content_type": "text/plain", "line_endings": "CRLF"}
        return {
            "format": format,
            "scope": "all" if all else document_id,
            **extra,
            "warnings": res.warnings,
            "notice": NOTICE_TEXT,
            "content": res.content,
        }
    fn = {
        ("json", False): exporter.export_doc_json,
        ("wide_csv", False): exporter.export_doc_csv_wide,
        ("long_csv", False): exporter.export_doc_csv_long,
        ("json", True): exporter.export_all_json,
        ("wide_csv", True): exporter.export_all_csv_wide,
        ("long_csv", True): exporter.export_all_csv_long,
    }[(format, bool(all))]
    content = fn() if all else fn(document_id)
    return {
        "format": format,
        "scope": "all" if all else document_id,
        "content_type": "application/json" if format == "json" else "text/csv",
        "content": content,
    }


@mcp.tool(
    title="List model choices",
    description=(
        "Show TaxClaw's three model tiers: (1) local Ollama vision models installed and recommended for this "
        "machine's RAM, (2) cloud providers whose API keys are present (presence only, values never shown) with "
        "their vision-capable models, (3) the strongest option that needs setup (Cloudflare Clairic). Also shows "
        "the backend currently configured."
    ),
)
def list_models() -> dict[str, Any]:
    from .models import build_report

    return build_report(load_config(), live=True)


def main() -> None:
    # Keep library chatter off the protocol stream; stderr only, warnings and up.
    logging.basicConfig(level=logging.WARNING, stream=__import__("sys").stderr)
    init_db()
    mcp.run("stdio")


if __name__ == "__main__":  # pragma: no cover
    main()
