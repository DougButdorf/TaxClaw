from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from urllib.request import urlopen

import fitz
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from .classify import classify_document
from .config import CONFIG_PATH, load_config, save_config
from .db import db, init_db
from .exporter import export_all_csv_long, export_all_csv_wide, export_all_json, export_doc_csv_long, export_doc_csv_wide, export_doc_json
from .extract import extract_document, pretty_json
from .review import compute_needs_review, compute_overall_confidence, missing_required_fields
from .store import (
    create_document_record,
    delete_document,
    get_document,
    get_document_by_hash,
    ingest_file,
    list_documents,
    mark_needs_review,
    mark_processed,
    page_count_for_pdf,
    store_1099da_transactions,
    store_extracted_fields,
    store_raw_extraction,
    update_document_metadata,
)

cfg = load_config()
init_db()

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

app = FastAPI(title="TaxClaw", version="0.1.0-beta")


def _ollama_tags() -> list[str]:
    """Return installed Ollama model tags, best-effort."""
    try:
        with urlopen("http://localhost:11434/api/tags", timeout=1.5) as r:
            data = json.loads(r.read().decode("utf-8"))
        models = data.get("models") or []
        out: list[str] = []
        for m in models:
            name = m.get("name")
            if isinstance(name, str) and name:
                out.append(name)
        return sorted(set(out))
    except Exception:
        return []


def _cloud_models() -> list[str]:
    # Keep this small; can expand later.
    return [
        "claude-haiku-4-5",
        "claude-sonnet-4-5",
    ]


def _get_stats() -> dict[str, int]:
    with db() as con:
        total = int(con.execute("SELECT COUNT(*) FROM documents").fetchone()[0])
        needs_review = int(con.execute("SELECT COUNT(*) FROM documents WHERE needs_review=1").fetchone()[0])
        processed = int(con.execute("SELECT COUNT(*) FROM documents WHERE status='processed'").fetchone()[0])
        ready_to_export = int(
            con.execute(
                "SELECT COUNT(*) FROM documents WHERE status='processed' AND COALESCE(needs_review, 0)=0"
            ).fetchone()[0]
        )
        crypto_docs = int(
            con.execute(
                """SELECT COUNT(*) FROM documents
                   WHERE doc_type IN ('1099-DA', '1099-B', 'consolidated-1099')"""
            ).fetchone()[0]
        )
    return {
        "total": total,
        "needs_review": needs_review,
        "processed": processed,
        "ready_to_export": ready_to_export,
        "crypto_docs": crypto_docs,
    }


@app.get("/api/stats")
def api_stats() -> dict[str, int]:
    return _get_stats()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    stats = _get_stats()

    cfg_now = load_config()
    if cfg_now.model_backend == "local":
        status_label = "🟢 FULLY LOCAL"
        status_pill_class = "ok"
    else:
        status_label = "🟡 PARTIALLY LOCAL"
        status_pill_class = "warn"

    with db() as con:
        rows = con.execute("SELECT * FROM documents ORDER BY created_at DESC LIMIT 5").fetchall()
        recent_docs = [{k: r[k] for k in r.keys()} for r in rows]

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "stats": stats,
            "status_label": status_label,
            "status_pill_class": status_pill_class,
            "recent_docs": recent_docs,
        },
    )


@app.get("/affiliate-info", response_class=HTMLResponse)
def affiliate_info(request: Request):
    return templates.TemplateResponse(
        "affiliate.html",
        {
            "request": request,
            "title": "Crypto tools • TaxClaw",
        },
    )


@app.get("/documents", response_class=HTMLResponse)
def documents_list(
    request: Request,
    filer: str | None = None,
    year: int | None = None,
    type: str | None = None,
    needs_review: int | None = None,
):
    docs = list_documents(filer=filer, year=year, doc_type=type, needs_review=needs_review)
    return templates.TemplateResponse(
        "list.html",
        {
            "request": request,
            "docs": docs,
            "filters": {
                "filer": filer or "",
                "year": year or "",
                "type": type or "",
                "needs_review": "" if needs_review is None else str(int(needs_review)),
            },
        },
    )


@app.get("/review", response_class=HTMLResponse)
def review_queue(request: Request):
    docs = list_documents(needs_review=1)
    return templates.TemplateResponse("review.html", {"request": request, "docs": docs})


@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    cfg_now = load_config()
    local_models = _ollama_tags()

    status_level = "full_local" if cfg_now.model_backend == "local" else "partial_local"
    needs_privacy_ack = bool(cfg_now.model_backend == "cloud" and not cfg_now.privacy_acknowledged)

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "cfg": cfg_now,
            "local_models": local_models,
            "cloud_models": _cloud_models(),
            "cloud_model": cfg_now.cloud_model,
            "status_level": status_level,
            "needs_privacy_ack": needs_privacy_ack,
            "config_path": str(CONFIG_PATH),
            "error": None,
        },
    )


@app.post("/settings", response_class=HTMLResponse)
async def settings_save(
    request: Request,
    model_backend: str = Form(...),
    local_model: str = Form(default=""),
    cloud_model: str = Form(default=""),
    privacy_acknowledged: str | None = Form(default=None),
):
    cfg_now = load_config()

    cfg_now.model_backend = "cloud" if model_backend == "cloud" else "local"
    if local_model:
        cfg_now.local_model = local_model
    if cloud_model:
        cfg_now.cloud_model = cloud_model
    cfg_now.privacy_acknowledged = bool(privacy_acknowledged) if cfg_now.model_backend == "cloud" else False

    if cfg_now.model_backend == "cloud" and not cfg_now.privacy_acknowledged:
        return templates.TemplateResponse(
            "settings.html",
            {
                "request": request,
                "cfg": cfg_now,
                "local_models": _ollama_tags(),
                "cloud_models": _cloud_models(),
                "cloud_model": cfg_now.cloud_model,
                "status_level": "partial_local",
                "needs_privacy_ack": True,
                "config_path": str(CONFIG_PATH),
                "error": "Cloud mode requires privacy confirmation.",
            },
        )

    save_config(cfg=cfg_now)
    global cfg
    cfg = load_config()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/upload")
async def upload(
    request: Request,
    file: UploadFile = File(...),
):
    filer: str | None = None
    year: int | None = None
    if cfg.model_backend == "cloud" and not cfg.privacy_acknowledged:
        return RedirectResponse(url="/settings", status_code=303)

    # save incoming upload to temp
    incoming = cfg.data_path / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    tmp_path = incoming / f"{uuid.uuid4()}_{file.filename}"
    tmp_path.write_bytes(await file.read())

    dest_path, file_hash, original_filename, mime_type = ingest_file(str(tmp_path), cfg)
    try:
        tmp_path.unlink(missing_ok=True)
    except Exception:
        pass

    existing = get_document_by_hash(file_hash)
    if existing:
        return RedirectResponse(url=f"/doc/{existing['id']}", status_code=303)

    page_count = page_count_for_pdf(dest_path) if dest_path.lower().endswith(".pdf") else 1

    cls = classify_document(dest_path, cfg)
    doc_type = cls.get("doc_type") or "unknown"
    classification_confidence = float(cls.get("confidence") or 0.0)

    doc_id = create_document_record(
        cfg=cfg,
        file_path=dest_path,
        file_hash=file_hash,
        original_filename=original_filename,
        mime_type=mime_type,
        filer=filer,
        tax_year=year,
        doc_type=doc_type,
        page_count=page_count,
        classification_confidence=classification_confidence,
    )

    try:
        extracted = extract_document(dest_path, doc_type, cfg)
        section_id = store_raw_extraction(doc_id=doc_id, form_type=doc_type, data=extracted, confidence=classification_confidence)
        store_extracted_fields(doc_id=doc_id, section_id=section_id, data=extracted)
        if doc_type == "1099-DA" and isinstance(extracted, dict):
            store_1099da_transactions(doc_id=doc_id, extraction=extracted)

        missing = missing_required_fields(doc_type, extracted)
        overall = compute_overall_confidence(doc_type=doc_type, extraction=extracted, classification_confidence=classification_confidence)
        nr = compute_needs_review(classification_confidence=classification_confidence, overall_confidence=overall, missing_required=missing)

        # store some common identity fields if present
        if isinstance(extracted, dict):
            header = extracted.get("header") if isinstance(extracted.get("header"), dict) else extracted
            payer_name = None
            recipient_name = None
            account_number = None
            if isinstance(header, dict):
                payer_name = header.get("payer_name")
                recipient_name = header.get("recipient_name")
                account_number = header.get("account_number")
            with db() as con:
                con.execute(
                    """UPDATE documents
                       SET payer_name=COALESCE(?, payer_name), recipient_name=COALESCE(?, recipient_name), account_number=COALESCE(?, account_number),
                           overall_confidence=?, needs_review=?
                       WHERE id=?""",
                    (payer_name, recipient_name, account_number, overall, int(nr), doc_id),
                )

        mark_processed(doc_id=doc_id, overall_confidence=overall, needs_review=nr)
    except Exception as e:
        mark_needs_review(doc_id=doc_id, notes=str(e))

    return RedirectResponse(url=f"/doc/{doc_id}", status_code=303)


@app.get("/doc/{doc_id}", response_class=HTMLResponse)
def doc_detail(request: Request, doc_id: str):
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
            extraction = json.loads(ext[0]) if ext[0] else None

        rows = con.execute(
            "SELECT field_path, field_value FROM extracted_fields WHERE document_id=? ORDER BY field_path ASC",
            (doc_id,),
        ).fetchall()
        fields = [(r[0], r[1]) for r in rows]

        if doc.get("doc_type") == "1099-DA":
            rows2 = con.execute(
                "SELECT * FROM transactions_1099da WHERE document_id=? ORDER BY rowid ASC", (doc_id,)
            ).fetchall()
            txns = [{k: r[k] for k in r.keys()} for r in rows2]

    return templates.TemplateResponse(
        "detail.html",
        {
            "request": request,
            "doc": doc,
            "fields": fields,
            "extraction": extraction,
            "extraction_pretty": pretty_json(extraction) if extraction is not None else None,
            "transactions": txns,
        },
    )


@app.post("/doc/{doc_id}/update")
async def doc_update(
    doc_id: str,
    filer: str | None = Form(default=None),
    year: int | None = Form(default=None),
    doc_type: str | None = Form(default=None),
    notes: str | None = Form(default=None),
):
    update_document_metadata(doc_id=doc_id, filer=filer, tax_year=year, doc_type=doc_type, notes=notes)
    return RedirectResponse(url=f"/doc/{doc_id}", status_code=303)


@app.post("/doc/{doc_id}/delete")
def doc_delete(doc_id: str):
    delete_document(doc_id)
    return RedirectResponse(url="/documents", status_code=303)


@app.get("/doc/{doc_id}/download")
def doc_download(doc_id: str):
    doc = get_document(doc_id)
    if not doc:
        return Response("Not found", status_code=404)
    return FileResponse(path=doc["file_path"], filename=doc.get("original_filename") or Path(doc["file_path"]).name)


@app.get("/doc/{doc_id}/preview.png")
def doc_preview_png(doc_id: str):
    doc = get_document(doc_id)
    if not doc:
        return Response("Not found", status_code=404)

    path = doc["file_path"]
    if path.lower().endswith(".pdf"):
        pdf = fitz.open(path)
        try:
            page = pdf[0]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            return Response(pix.tobytes("png"), media_type="image/png")
        finally:
            pdf.close()

    # image file
    return FileResponse(path)


@app.get("/doc/{doc_id}/export.wide.csv")
def doc_export_wide(doc_id: str):
    csv_text = export_doc_csv_wide(doc_id)
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=taxclaw-{doc_id}-wide.csv"},
    )


@app.get("/doc/{doc_id}/export.long.csv")
def doc_export_long(doc_id: str):
    csv_text = export_doc_csv_long(doc_id)
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=taxclaw-{doc_id}-long.csv"},
    )


@app.get("/doc/{doc_id}/export.json")
def doc_export_json(doc_id: str):
    txt = export_doc_json(doc_id)
    return Response(
        txt,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=taxclaw-{doc_id}.json"},
    )


@app.get("/export.wide.csv")
def export_all_wide():
    csv_text = export_all_csv_wide()
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=taxclaw-all-wide.csv"},
    )


@app.get("/export.long.csv")
def export_all_long():
    csv_text = export_all_csv_long()
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=taxclaw-all-long.csv"},
    )


@app.get("/export.json")
def export_all_as_json():
    txt = export_all_json()
    return Response(
        txt,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=taxclaw-all.json"},
    )
