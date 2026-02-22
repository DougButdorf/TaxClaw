from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .classify import classify_document
from .config import load_config
from .db import init_db
from .exporter import export_all_csv, export_doc_csv
from .extract import extract_document, pretty_json
from .store import (
    create_document_record,
    delete_document,
    get_document,
    get_document_by_hash,
    ingest_file,
    list_documents,
    mark_processed,
    page_count_for_pdf,
    store_1099da_transactions,
    store_extraction,
)

cfg = load_config()
init_db()

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

app = FastAPI(title="taxclaw", version="0.1.0-beta")


@app.get("/", response_class=HTMLResponse)
def home(request: Request, filer: str | None = None, year: int | None = None, type: str | None = None):
    docs = list_documents(filer=filer, year=year, doc_type=type)
    return templates.TemplateResponse(
        "list.html",
        {
            "request": request,
            "docs": docs,
            "filters": {"filer": filer or "", "year": year or "", "type": type or ""},
        },
    )


@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@app.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
    filer: str | None = Form(default=None),
    year: int | None = Form(default=None),
):
    # save incoming upload to temp, then move into uploads store
    tmp_dir = cfg.uploads_dir / "_incoming"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"{uuid.uuid4()}_{file.filename}"

    content = await file.read()
    tmp_path.write_bytes(content)

    dest_path, file_hash, original_filename = ingest_file(str(tmp_path), cfg)
    try:
        tmp_path.unlink(missing_ok=True)
    except Exception:
        pass

    existing = get_document_by_hash(file_hash)
    if existing:
        return RedirectResponse(url=f"/doc/{existing['id']}", status_code=303)

    page_count = page_count_for_pdf(dest_path) if dest_path.lower().endswith(".pdf") else 1

    # classify
    cls = classify_document(dest_path, cfg)
    doc_type = cls.get("doc_type") or "unknown"

    doc_id = create_document_record(
        cfg=cfg,
        file_path=dest_path,
        file_hash=file_hash,
        original_filename=original_filename,
        filer=filer,
        tax_year=year,
        doc_type=doc_type,
        page_count=page_count,
    )

    # extract
    try:
        extracted = extract_document(dest_path, doc_type, cfg)
        store_extraction(doc_id=doc_id, form_type=doc_type, data=extracted, confidence=cls.get("confidence"))
        if doc_type == "1099-DA" and isinstance(extracted, dict):
            store_1099da_transactions(doc_id=doc_id, extraction=extracted)
        mark_processed(doc_id=doc_id, overall_confidence=float(cls.get("confidence") or 0.5))
    except Exception as e:
        # mark as needs_review
        from .db import db

        with db() as con:
            con.execute("UPDATE documents SET status='needs_review', notes=? WHERE id=?", (str(e), doc_id))

    return RedirectResponse(url=f"/doc/{doc_id}", status_code=303)


@app.get("/doc/{doc_id}", response_class=HTMLResponse)
def doc_detail(request: Request, doc_id: str):
    from .db import db

    doc = get_document(doc_id)
    if not doc:
        return Response("Not found", status_code=404)

    extraction: Any = None
    txns: list[dict[str, Any]] = []
    with db() as con:
        ext = con.execute(
            "SELECT raw_json, confidence, created_at FROM form_extractions WHERE document_id=? ORDER BY created_at DESC LIMIT 1",
            (doc_id,),
        ).fetchone()
        if ext:
            import json

            extraction = json.loads(ext[0]) if ext[0] else None
        if doc.get("doc_type") == "1099-DA":
            rows = con.execute(
                "SELECT * FROM transactions_1099da WHERE document_id=? ORDER BY rowid ASC", (doc_id,)
            ).fetchall()
            txns = [{k: r[k] for k in r.keys()} for r in rows]

    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "doc": doc,
            "extraction": extraction,
            "extraction_pretty": pretty_json(extraction) if extraction is not None else None,
            "transactions": txns,
        },
    )


@app.post("/doc/{doc_id}/delete")
def doc_delete(doc_id: str):
    delete_document(doc_id)
    return RedirectResponse(url="/", status_code=303)


@app.get("/doc/{doc_id}/export.csv")
def doc_export(doc_id: str):
    csv_text = export_doc_csv(doc_id)
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=taxclaw-{doc_id}.csv"},
    )


@app.get("/export.csv")
def export_all():
    csv_text = export_all_csv()
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=taxclaw-all.csv"},
    )
