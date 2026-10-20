from __future__ import annotations

import html as html_module
import io
import json
import os
import re
import secrets
import uuid
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pymupdf
from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.middleware.base import BaseHTTPMiddleware

from .ai import ensure_backend_ready
from .classify import classify_document
from .config import CONFIG_PATH, load_config, save_config
from .db import db, init_db
from .exporter import export_all_csv_long, export_all_csv_wide, export_all_json, export_doc_csv_long, export_doc_csv_wide, export_doc_json
from .extract import extract_document_with_meta, pretty_json
from .ollama_local import list_models_with_vision, ollama_host
from .review import compute_needs_review, compute_overall_confidence, missing_required_fields
from .store import (
    create_document_record,
    delete_document,
    extract_and_store_1099b_lots,
    generate_display_name,
    get_document,
    get_document_by_hash,
    ingest_file,
    list_documents,
    mark_error,
    mark_needs_review,
    mark_processed,
    page_count_for_pdf,
    set_display_name_if_empty,
    store_1099da_transactions,
    store_extracted_fields,
    store_raw_extraction,
    update_document_metadata,
)

cfg = load_config()
init_db()

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))

app = FastAPI(title="TaxClaw", version="0.1.2")


# ---------------------------------------------------------------------------
# Security middleware (headers + loopback host/origin enforcement)
# ---------------------------------------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        return response


class LoopbackHostOriginMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in {"POST", "DELETE"}:
            hostname = _host_header_hostname(request)
            if not _is_loopback_host(hostname):
                return Response("Forbidden", status_code=403)

            origin = request.headers.get("origin")
            if origin is not None and not _is_loopback_host(urlparse(origin).hostname):
                return Response("Forbidden", status_code=403)

        return await call_next(request)


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(LoopbackHostOriginMiddleware)


# ---------------------------------------------------------------------------
# Security helpers (CSRF + origin/host checks)
# ---------------------------------------------------------------------------

CSRF_COOKIE = "taxclaw_csrf"


def _is_loopback_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    h = hostname.lower()
    return h in {"127.0.0.1", "localhost"} or h.endswith(".localhost")


def _host_header_hostname(request: Request) -> str | None:
    host = (request.headers.get("host") or "").lower()
    return host.rsplit("@", 1)[-1].split(":", 1)[0]


def _get_or_create_csrf_token(request: Request) -> str:
    tok = request.cookies.get(CSRF_COOKIE)
    if isinstance(tok, str) and tok.strip():
        return tok
    return secrets.token_urlsafe(32)


def _assert_same_origin(request: Request) -> None:
    """Basic localhost CSRF defense.

    We only intend to serve loopback traffic. If the app is ever exposed beyond
    localhost, this (plus CSRF tokens) reduces risk of drive-by POSTs.
    """

    host = _host_header_hostname(request)
    if not _is_loopback_host(host):
        raise ValueError("TaxClaw only allows loopback (localhost) requests")

    origin = request.headers.get("origin")
    if origin:
        if not _is_loopback_host(urlparse(origin).hostname):
            raise ValueError("invalid Origin")


def _require_csrf(request: Request, token: str | None) -> None:
    cookie_tok = request.cookies.get(CSRF_COOKIE)
    if not cookie_tok or not token or token != cookie_tok:
        raise ValueError("missing/invalid CSRF token")


def _render(request: Request, name: str, context: dict[str, Any]) -> Response:
    tok = _get_or_create_csrf_token(request)
    ctx = dict(context)
    ctx.setdefault("csrf_token", tok)
    resp = templates.TemplateResponse(request, name, ctx)
    # Double-submit cookie (HTTP-only so JS can't read it, but the form token can).
    if request.cookies.get(CSRF_COOKIE) != tok:
        resp.set_cookie(CSRF_COOKIE, tok, httponly=True, samesite="lax")
    return resp


def _ollama_model_info() -> list[dict]:
    """Return installed Ollama models with a vision capability flag (vision models first).

    Vision is read from Ollama's /api/show ``capabilities`` (contains "vision");
    a model-family allowlist is only a fallback for old Ollama builds. Text-only
    models cannot read document images, so extraction with them fails.
    """
    return list_models_with_vision(timeout=1.5)


def _with_tag(name: str) -> str:
    """Ollama treats "glm-ocr" and "glm-ocr:latest" as the same model."""
    return name if ":" in name else f"{name}:latest"


# ---------------------------------------------------------------------------
# Field display helpers
# ---------------------------------------------------------------------------

# Keys (exact or partial match) that represent dollar / money amounts
_DOLLAR_KEYWORDS = frozenset([
    "withheld", "wages", "income", "comp", "proceeds", "basis",
    "penalty", "payment", "payments", "gain", "loss", "contributions",
    "dividends", "royalties", "capital", "interest", "earnings",
    "refund", "amount", "proceeds", "discount", "section_179",
    "fees", "expense", "revenue", "salary", "bonus",
])

# Abbreviation overrides applied AFTER title-casing each word
_LABEL_OVERRIDES: dict[str, str] = {
    "Ein": "EIN",
    "Tin": "TIN",
    "Ssn": "SSN",
    "Nec": "NEC",
    "Da": "DA",
    "Us": "U.S.",
    "Amt": "AMT",
    "Irs": "IRS",
    "Pct": "%",
    "Payer": "Payer",
    "Payee": "Payee",
}


def _format_field_label(key: str) -> str:
    """Convert snake_case field key to a human-readable label.

    Examples:
        employer_name     → Employer Name
        federal_withheld  → Federal Withheld
        nonemployee_comp  → Nonemployee NEC  (comp→NEC handled via override)
        payer_tin         → Payer TIN
        profit_sharing_pct → Profit Sharing %
    """
    words = key.replace(".", " ").replace("_", " ").split()
    out = []
    for w in words:
        titled = w.title()
        out.append(_LABEL_OVERRIDES.get(titled, titled))
    return " ".join(out)


def _is_dollar_field(key: str) -> bool:
    """Return True if the field key represents a monetary amount."""
    lower = key.lower()
    return any(kw in lower for kw in _DOLLAR_KEYWORDS)


def _format_dollar(raw: str) -> str:
    """Try to format a string as a USD dollar amount.

    Returns formatted string on success, original on failure.
    """
    if raw is None:
        return ""
    # Strip common noise
    cleaned = re.sub(r"[$,\s]", "", str(raw).strip())
    # Handle parentheses as negatives: (1234.56) → -1234.56
    if cleaned.startswith("(") and cleaned.endswith(")"):
        cleaned = "-" + cleaned[1:-1]
    try:
        val = float(cleaned)
        # Format with commas and 2 decimal places, prepend $
        formatted = f"${val:,.2f}"
        if val < 0:
            formatted = f"-${abs(val):,.2f}"
        return formatted
    except (ValueError, TypeError):
        return str(raw)


def _format_fields(fields: list[tuple[str, Any]]) -> list[tuple[str, str, str]]:
    """Return (raw_key, human_label, formatted_value) triples for template rendering."""
    result: list[tuple[str, str, str]] = []
    for key, val in fields:
        label = _format_field_label(key)
        if val is None or val == "" or val == "null":
            continue  # skip nulls entirely — cleaner table
        str_val = str(val)
        if _is_dollar_field(key):
            str_val = _format_dollar(str_val)
        result.append((key, label, str_val))
    return result


def _ollama_tags() -> list[str]:
    """Return installed Ollama model names, best-effort (for backward compat)."""
    return [m["name"] for m in _ollama_model_info()]


def _cloud_models() -> list[str]:
    # Confirmed current Anthropic model IDs (balance, strongest); see src/model_catalog.yaml.
    return [
        "claude-haiku-5-5",
        "claude-sonnet-5-5",
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
    if not cfg_now.is_cloud:
        status_label = "🟢 FULLY LOCAL"
        status_pill_class = "ok"
    else:
        status_label = "🟡 PARTIALLY LOCAL"
        status_pill_class = "warn"

    with db() as con:
        rows = con.execute("SELECT * FROM documents ORDER BY created_at DESC LIMIT 5").fetchall()
        recent_docs = [{k: r[k] for k in r.keys()} for r in rows]

    return _render(
        request,
        "dashboard.html",
        {
            "request": request,
            "stats": stats,
            "status_label": status_label,
            "status_pill_class": status_pill_class,
            "recent_docs": recent_docs,
        },
    )


@app.get("/digital_assets", response_class=HTMLResponse)
def digital_assets(request: Request):
    return _render(
        request,
        "affiliate.html",
        {
            "request": request,
            "title": "Crypto tools • TaxClaw",
        },
    )


@app.get("/affiliate-info")
def affiliate_info_redirect() -> RedirectResponse:
    # Back-compat for old links
    return RedirectResponse(url="/digital_assets", status_code=301)


@app.get("/documents", response_class=HTMLResponse)
def documents_list(
    request: Request,
    filer: str | None = None,
    year: int | None = None,
    type: str | None = None,
    needs_review: int | None = None,
):
    docs = list_documents(filer=filer, year=year, doc_type=type, needs_review=needs_review)

    # Populate filter dropdowns from DB so users can't mistype values.
    with db() as con:
        filers = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT filer FROM documents WHERE filer IS NOT NULL AND filer != '' ORDER BY filer"
            ).fetchall()
        ]
        years = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT tax_year FROM documents WHERE tax_year IS NOT NULL ORDER BY tax_year DESC"
            ).fetchall()
        ]
        doc_types = [
            r[0]
            for r in con.execute(
                "SELECT DISTINCT doc_type FROM documents WHERE doc_type IS NOT NULL AND doc_type != '' ORDER BY doc_type"
            ).fetchall()
        ]

    return _render(
        request,
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
            "filter_options": {
                "filers": filers,
                "years": years,
                "doc_types": doc_types,
            },
        },
    )


@app.get("/review", response_class=HTMLResponse)
def review_queue(request: Request):
    docs = list_documents(needs_review=1)
    return _render(request, "review.html", {"request": request, "docs": docs})


@app.get("/upload", response_class=HTMLResponse)
def upload_form(request: Request):
    cfg_now = load_config()
    return _render(request, "upload.html", {
        "request": request,
        "model_backend": "cloud" if cfg_now.is_cloud else "local",
        "cloud_model": cfg_now.selected_model_label(),
        "local_model": cfg_now.local_model,
    })


_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")


def _settings_context(request: Request, cfg_now: Any, *, error: str | None = None) -> dict[str, Any]:
    from .config import OPENAI_COMPAT_PRESETS
    from .models import build_report

    local_models_info = _ollama_model_info()
    vision_models = {m["name"] for m in local_models_info if m["vision"]}
    selected_is_vision = _with_tag(cfg_now.local_model) in {_with_tag(n) for n in vision_models}
    report = build_report(cfg_now, live=True, ollama_models=local_models_info)
    tier1, tier2, tier3 = report["tiers"]
    from .doctor import build_report as doctor_report

    doctor = doctor_report(cfg_now)  # the same three paths as `taxclaw doctor`

    # Model suggestions for the OpenAI-compatible picker: live vision lists per preset.
    compat_models: dict[str, list[str]] = {}
    compat_recommended: dict[str, dict[str, Any]] = {}
    for p in tier2["providers"]:
        preset = p.get("openai_compat_provider")
        if preset:
            compat_models[preset] = list(p.get("vision_models") or [])
            if p.get("recommended"):
                compat_recommended[preset] = p["recommended"]

    return {
        "request": request,
        "cfg": cfg_now,
        "backend": cfg_now.backend,
        "local_models": [m["name"] for m in local_models_info],
        "local_models_info": local_models_info,
        "vision_models": vision_models,
        "selected_is_vision": selected_is_vision,
        "cloud_models": _cloud_models(),
        "cloud_model": cfg_now.cloud_model,
        "selected_model_label": cfg_now.selected_model_label(),
        "status_level": "full_local" if not cfg_now.is_cloud else "partial_local",
        "needs_privacy_ack": bool(cfg_now.is_cloud and not cfg_now.privacy_acknowledged),
        "config_path": str(CONFIG_PATH),
        "ollama_host": ollama_host(),
        "doctor": doctor,
        "tier1": tier1,
        "tier2": tier2,
        "tier3": tier3,
        "catalog": report["catalog"],
        "compat_presets": OPENAI_COMPAT_PRESETS,
        "compat_models": compat_models,
        "compat_recommended": compat_recommended,
        "error": error,
    }


@app.get("/settings", response_class=HTMLResponse)
def settings(request: Request):
    cfg_now = load_config()
    return _render(request, "settings.html", _settings_context(request, cfg_now))


@app.post("/settings", response_class=HTMLResponse)
async def settings_save(
    request: Request,
    csrf_token: str = Form(...),
    model_backend: str = Form(...),
    local_model: str = Form(default=""),
    cloud_model: str = Form(default=""),
    openai_compat_provider: str = Form(default=""),
    openai_compat_model: str = Form(default=""),
    openai_compat_base_url: str = Form(default=""),
    openai_compat_api_key_env: str = Form(default=""),
    privacy_acknowledged: str | None = Form(default=None),
):
    from .config import OPENAI_COMPAT_PRESETS, clear_cloud_consent, is_cloud_backend, normalize_backend, record_cloud_consent

    cfg_now = load_config()

    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf_token)
    except Exception:
        return Response("Forbidden", status_code=403)

    cfg_now.model_backend = normalize_backend(model_backend)
    if local_model:
        cfg_now.local_model = local_model.strip()
    if cloud_model:
        cfg_now.cloud_model = cloud_model.strip()
    if openai_compat_provider in OPENAI_COMPAT_PRESETS:
        cfg_now.openai_compat_provider = openai_compat_provider
    if openai_compat_model:
        cfg_now.openai_compat_model = openai_compat_model.strip()
    cfg_now.openai_compat_base_url = openai_compat_base_url.strip()
    cfg_now.openai_compat_api_key_env = openai_compat_api_key_env.strip()
    cloud = is_cloud_backend(cfg_now.model_backend)
    if cloud and privacy_acknowledged:
        # Consent is recorded with a time and the provider; saving again for the same provider keeps the original time.
        record_cloud_consent(cfg_now, keep_existing=True)
    else:
        cfg_now.privacy_acknowledged = False
        if not cloud:
            clear_cloud_consent(cfg_now)
        else:
            cfg_now.privacy_acknowledged_at = ""
            cfg_now.cloud_provider = ""

    error = None
    if cfg_now.openai_compat_api_key_env and not _ENV_NAME_RE.match(cfg_now.openai_compat_api_key_env):
        error = "API key env var must be an environment variable NAME such as OPENAI_API_KEY (never the key itself)."
        cfg_now.openai_compat_api_key_env = ""
    elif cfg_now.openai_compat_base_url and not re.match(
        r"^(https://|http://(127\.0\.0\.1|localhost)(:\d+)?/)", cfg_now.openai_compat_base_url
    ):
        error = "Custom base URL must start with https:// (or http://localhost/...)."
        cfg_now.openai_compat_base_url = ""
    elif cloud and not cfg_now.privacy_acknowledged:
        error = "Cloud backends require the privacy confirmation."

    if error:
        return _render(request, "settings.html", _settings_context(request, cfg_now, error=error))

    save_config(cfg=cfg_now)
    global cfg
    cfg = load_config()
    return RedirectResponse(url="/settings", status_code=303)


@app.post("/upload")
async def upload(
    request: Request,
    csrf_token: str = Form(...),
    file: UploadFile = File(...),
):
    filer: str | None = None
    year: int | None = None

    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf_token)
    except Exception:
        return Response("Forbidden", status_code=403)

    if cfg.is_cloud and not cfg.privacy_acknowledged:
        return RedirectResponse(url="/settings", status_code=303)

    # Fail fast with a clear message (Ollama not running, text-only model, ...)
    # before anything is written to disk.
    try:
        ensure_backend_ready(cfg)
    except Exception as e:  # noqa: BLE001
        return _render(
            request,
            "upload.html",
            {
                "request": request,
                "model_backend": "cloud" if cfg.is_cloud else "local",
                "cloud_model": cfg.selected_model_label(),
                "local_model": cfg.local_model,
                "error": str(e),
            },
        )

    incoming = cfg.data_path / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)

    max_upload_bytes = int(cfg.max_upload_bytes)
    max_upload_mb = max_upload_bytes / (1024 * 1024)

    raw_name = file.filename or "upload"

    # Sanitize for display/DB use only (never trust user-provided path segments)
    safe_name = Path(raw_name).name
    safe_name = safe_name.replace("..", "").replace("/", "").replace("\\", "")
    safe_name = re.sub(r"[\x00-\x1f\x7f]", "", safe_name).strip()

    ext_to_mime = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".webp": "image/webp",
    }

    claimed_ext = Path(safe_name).suffix.lower()
    if claimed_ext not in ext_to_mime:
        return _render(
            request,
            "upload.html",
            {
                "request": request,
                "model_backend": "cloud" if cfg.is_cloud else "local",
                "cloud_model": cfg.selected_model_label(),
                "local_model": cfg.local_model,
                "error": f"Unsupported file extension: {claimed_ext or '(none)'}",
            },
        )

    try:
        data = await file.read(max_upload_bytes + 1)
        if len(data) > max_upload_bytes:
            raise HTTPException(status_code=413, detail=f"File too large. Max {max_upload_mb:.0f}MB.")

        def _detect_mime(buf: bytes) -> str:
            if buf.startswith(b"%PDF"):
                return "application/pdf"
            if buf.startswith(b"\x89PNG\r\n\x1a\n"):
                return "image/png"
            if buf.startswith(b"\xff\xd8\xff"):
                return "image/jpeg"
            if buf.startswith(b"II*\x00") or buf.startswith(b"MM\x00*"):
                return "image/tiff"
            if len(buf) >= 12 and buf[0:4] == b"RIFF" and buf[8:12] == b"WEBP":
                return "image/webp"
            return "application/octet-stream"

        detected = _detect_mime(data[:2048])
        expected = ext_to_mime[claimed_ext]
        if detected != expected:
            return _render(
                request,
                "upload.html",
                {
                    "request": request,
                    "model_backend": "cloud" if cfg.is_cloud else "local",
                    "cloud_model": cfg.selected_model_label(),
                    "local_model": cfg.local_model,
                    "error": f"Unsupported file type: {detected}",
                },
            )

        if not safe_name:
            safe_name = f"upload{claimed_ext}"

        # Internal UUID-based path for disk writes
        tmp_path = incoming / f"{uuid.uuid4().hex}{claimed_ext}"
        tmp_path.write_bytes(data)
    except HTTPException as e:
        return _render(
            request,
            "upload.html",
            {
                "request": request,
                "model_backend": "cloud" if cfg.is_cloud else "local",
                "cloud_model": cfg.selected_model_label(),
                "local_model": cfg.local_model,
                "error": e.detail,
            },
        )
    except Exception as e:
        return _render(
            request,
            "upload.html",
            {
                "request": request,
                "model_backend": "cloud" if cfg.is_cloud else "local",
                "cloud_model": cfg.selected_model_label(),
                "local_model": cfg.local_model,
                "error": f"Upload failed: {str(e)}",
            },
        )

    try:
        dest_path, file_hash, original_filename, mime_type = ingest_file(str(tmp_path), cfg, original_name=safe_name)
    except Exception as e:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
        return _render(
            request,
            "upload.html",
            {
                "request": request,
                "model_backend": "cloud" if cfg.is_cloud else "local",
                "cloud_model": cfg.selected_model_label(),
                "local_model": cfg.local_model,
                "error": f"Unsupported or unsafe upload: {str(e)}",
            },
        )
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

    existing = get_document_by_hash(file_hash)
    if existing:
        return RedirectResponse(url=f"/doc/{existing['id']}", status_code=303)

    page_count = page_count_for_pdf(dest_path) if dest_path.lower().endswith(".pdf") else 1

    doc_type = "unknown"
    classification_confidence = 0.0
    classify_note: str | None = None
    try:
        cls = classify_document(dest_path, cfg)
        doc_type = cls.get("doc_type") or "unknown"
        classification_confidence = float(cls.get("confidence") or 0.0)
    except Exception as e:
        classify_note = f"classification failed: {str(e)}"

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

    if classify_note:
        update_document_metadata(doc_id=doc_id, filer=None, tax_year=None, doc_type=None, notes=classify_note)

    try:
        result = extract_document_with_meta(dest_path, doc_type, cfg)
        extracted = result.data
        section_id = store_raw_extraction(doc_id=doc_id, form_type=doc_type, data=extracted, confidence=classification_confidence)
        store_extracted_fields(doc_id=doc_id, section_id=section_id, data=extracted, confidences=result.field_confidence)
        if doc_type == "1099-DA" and isinstance(extracted, dict):
            store_1099da_transactions(doc_id=doc_id, extraction=extracted)
        _lot_count, lot_note = extract_and_store_1099b_lots(doc_id=doc_id, file_path=dest_path, doc_type=doc_type, cfg=cfg)

        missing = missing_required_fields(doc_type, extracted)
        overall = compute_overall_confidence(doc_type=doc_type, extraction=extracted, classification_confidence=classification_confidence)
        nr = compute_needs_review(classification_confidence=classification_confidence, overall_confidence=overall, missing_required=missing)
        nr = nr or bool(result.review_fields) or bool(lot_note)
        review_notes = [n for n in (
            f"low-confidence fields: {', '.join(result.review_fields)}" if result.review_fields else None,
            lot_note,
        ) if n]

        # store some common identity fields if present
        if isinstance(extracted, dict):
            header = extracted.get("header") if isinstance(extracted.get("header"), dict) else extracted
            payer_name = None
            recipient_name = None
            account_number = None
            payer_guess = None
            filer_guess = None
            if isinstance(header, dict):
                payer_name = header.get("payer_name")
                recipient_name = header.get("recipient_name")
                account_number = header.get("account_number")

                # Payer name varies by form
                for k in ["payer_name", "employer_name", "payer", "employer", "box_c", "recipient_name"]:
                    v = header.get(k)
                    if isinstance(v, str) and v.strip():
                        payer_guess = v
                        break

                # Filer = the person/entity who received this form (the taxpayer)
                # Try recipient_name first, then form-specific fields
                for k in ["recipient_name", "employee_name", "partner_name", "shareholder_name", "beneficiary_name"]:
                    v = header.get(k)
                    if isinstance(v, str) and v.strip():
                        filer_guess = v.strip()
                        break

            year_guess = None
            if isinstance(header, dict):
                for k in ["tax_year", "year", "taxYear"]:
                    v = header.get(k)
                    if isinstance(v, int) and v > 1900:
                        year_guess = v
                        break
                    if isinstance(v, str) and v.strip().isdigit():
                        try:
                            iv = int(v.strip())
                            if iv > 1900:
                                year_guess = iv
                                break
                        except Exception:
                            pass

            display_name = generate_display_name(
                payer=payer_guess or payer_name,
                doc_type=doc_type,
                tax_year=year_guess or year,
            )

            with db() as con:
                con.execute(
                    """UPDATE documents
                       SET payer_name=COALESCE(?, payer_name),
                           recipient_name=COALESCE(?, recipient_name),
                           account_number=COALESCE(?, account_number),
                           filer=COALESCE(filer, ?),
                           overall_confidence=?, needs_review=?
                       WHERE id=?""",
                    (payer_name, recipient_name, account_number, filer_guess, overall, int(nr), doc_id),
                )

            set_display_name_if_empty(doc_id=doc_id, display_name=display_name)

        mark_processed(
            doc_id=doc_id,
            overall_confidence=overall,
            needs_review=nr,
            notes="; ".join(review_notes) or None,
        )
    except Exception as e:
        # Hard failure (including JSON parse errors) → mark error, don't crash.
        mark_error(doc_id=doc_id, error=str(e))

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

        lots: list[dict[str, Any]] = []
        if doc.get("doc_type") in ("1099-B", "consolidated-1099"):
            rows3 = con.execute(
                "SELECT * FROM transactions_1099b WHERE document_id=? ORDER BY lot_index ASC", (doc_id,)
            ).fetchall()
            lots = [{k: r[k] for k in r.keys()} for r in rows3]

    return _render(
        request,
        "detail.html",
        {
            "request": request,
            "doc": doc,
            "fields": _format_fields(fields),
            "extraction": extraction,
            "extraction_pretty": pretty_json(extraction) if extraction is not None else None,
            "transactions": txns,
            "lots": lots,
        },
    )


@app.post("/doc/{doc_id}/update")
async def doc_update(
    request: Request,
    doc_id: str,
    csrf_token: str = Form(...),
    display_name: str | None = Form(default=None),
    filer: str | None = Form(default=None),
    year: int | None = Form(default=None),
    doc_type: str | None = Form(default=None),
    notes: str | None = Form(default=None),
):
    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf_token)
    except Exception:
        return Response("Forbidden", status_code=403)

    # Allow clearing the name
    dn = None
    if display_name is not None:
        dn = display_name.strip() or None

    update_document_metadata(doc_id=doc_id, filer=filer, tax_year=year, doc_type=doc_type, notes=notes, display_name=dn)
    return RedirectResponse(url=f"/doc/{doc_id}", status_code=303)


@app.post("/doc/{doc_id}/delete")
def doc_delete(request: Request, doc_id: str, csrf_token: str = Form(...)):
    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf_token)
    except Exception:
        return Response("Forbidden", status_code=403)

    delete_document(doc_id)
    return RedirectResponse(url="/documents", status_code=303)


@app.post("/doc/{doc_id}/fields/{field_path:path}")
async def doc_field_update(
    request: Request,
    doc_id: str,
    field_path: str,
    csrf_token: str = Form(...),
    value: str = Form(...),
):
    """Inline edit of a single extracted field value."""

    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf_token)
    except Exception:
        return JSONResponse({"ok": False, "error": "forbidden"}, status_code=403)

    # Normalize (UI may send surrounding whitespace)
    v = value.strip()

    with db() as con:
        cur = con.execute(
            "UPDATE extracted_fields SET field_value=? WHERE document_id=? AND field_path=?",
            (v, doc_id, field_path),
        )
        if cur.rowcount == 0:
            con.execute(
                """INSERT INTO extracted_fields(id, document_id, field_path, field_value)
                   VALUES(?, ?, ?, ?)""",
                (str(uuid.uuid4()), doc_id, field_path, v),
            )

    return JSONResponse({"ok": True, "field_path": field_path, "value": v})


@app.post("/doc/{doc_id}/mark-reviewed")
def doc_mark_reviewed(request: Request, doc_id: str, csrf_token: str = Form(...)):
    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf_token)
    except Exception:
        return Response("Forbidden", status_code=403)

    with db() as con:
        con.execute("UPDATE documents SET needs_review=0 WHERE id=?", (doc_id,))
    return RedirectResponse(url=f"/doc/{doc_id}", status_code=303)


@app.post("/doc/{doc_id}/flag-review")
def doc_flag_review(request: Request, doc_id: str, csrf_token: str = Form(...)):
    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf_token)
    except Exception:
        return Response("Forbidden", status_code=403)

    with db() as con:
        con.execute("UPDATE documents SET needs_review=1 WHERE id=?", (doc_id,))
    return RedirectResponse(url=f"/doc/{doc_id}", status_code=303)


@app.get("/doc/{doc_id}/download")
def doc_download(doc_id: str):
    doc = get_document(doc_id)
    if not doc:
        return Response("Not found", status_code=404)
    return FileResponse(path=doc["file_path"], filename=doc.get("original_filename") or Path(doc["file_path"]).name)


@app.get("/doc/{doc_id}/preview.png")
def doc_preview_png(doc_id: str):
    """First-page preview (kept for backward compat)."""
    return doc_preview_page_png(doc_id, 0)


@app.get("/doc/{doc_id}/preview/{page}.png")
def doc_preview_page_png(doc_id: str, page: int = 0):
    """Render a single page (0-indexed) of a document as PNG."""
    doc = get_document(doc_id)
    if not doc:
        return Response("Not found", status_code=404)

    path = doc["file_path"]
    if path.lower().endswith(".pdf"):
        pdf = pymupdf.open(path)
        try:
            page_count = pdf.page_count
            if page < 0 or page >= page_count:
                return Response("Page out of range", status_code=404)
            pix = pdf[page].get_pixmap(matrix=pymupdf.Matrix(2, 2))
            return Response(pix.tobytes("png"), media_type="image/png")
        finally:
            pdf.close()

    # Non-PDF: only page 0 makes sense
    if page != 0:
        return Response("Page out of range", status_code=404)
    return FileResponse(path)


@app.get("/doc/{doc_id}/export.wide.csv")
def doc_export_wide(request: Request, doc_id: str, csrf: str = Query("")):
    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf)
    except Exception:
        return Response("Forbidden", status_code=403)

    csv_text = export_doc_csv_wide(doc_id)
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=taxclaw-{doc_id}-wide.csv"},
    )


@app.get("/doc/{doc_id}/export.long.csv")
def doc_export_long(request: Request, doc_id: str, csrf: str = Query("")):
    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf)
    except Exception:
        return Response("Forbidden", status_code=403)

    csv_text = export_doc_csv_long(doc_id)
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=taxclaw-{doc_id}-long.csv"},
    )


@app.get("/doc/{doc_id}/export.json")
def doc_export_json(request: Request, doc_id: str, csrf: str = Query("")):
    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf)
    except Exception:
        return Response("Forbidden", status_code=403)

    txt = export_doc_json(doc_id)
    return Response(
        txt,
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=taxclaw-{doc_id}.json"},
    )


def _accountant_export_response(request: Request, csrf: str, kind: str, doc_id: str | None) -> Response:
    """Form 8949 CSV / TXF download (same loopback + CSRF checks as the other exports)."""

    from .accountant_exports import NOTICE_TEXT, build_8949, export_txf

    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf)
    except Exception:
        return Response("Forbidden", status_code=403)
    if doc_id is not None and not get_document(doc_id):
        return Response("Not found", status_code=404)

    ids = None if doc_id is None else [doc_id]
    stem = f"taxclaw-{doc_id}" if doc_id else "taxclaw-all"
    headers = {"X-TaxClaw-Notice": NOTICE_TEXT}
    if kind == "8949":
        res = build_8949(ids)
        headers["X-TaxClaw-Processed-By"] = res.processed_by_line
        headers["Content-Disposition"] = f"attachment; filename={stem}-form8949.csv"
        headers["X-TaxClaw-Rows-Needing-Review"] = str(res.needs_review)
        return Response(res.content, media_type="text/csv", headers=headers)
    txf = export_txf(ids)
    headers["X-TaxClaw-Processed-By"] = txf.processed_by_line
    headers["Content-Disposition"] = f"attachment; filename={stem}.txf"
    headers["X-TaxClaw-Warnings"] = str(len(txf.warnings))
    return Response(txf.content.encode("ascii"), media_type="text/plain; charset=us-ascii", headers=headers)


@app.get("/doc/{doc_id}/export.8949.csv")
def doc_export_8949(request: Request, doc_id: str, csrf: str = Query("")):
    return _accountant_export_response(request, csrf, "8949", doc_id)


@app.get("/doc/{doc_id}/export.txf")
def doc_export_txf(request: Request, doc_id: str, csrf: str = Query("")):
    return _accountant_export_response(request, csrf, "txf", doc_id)


@app.get("/export.8949.csv")
def export_all_8949(request: Request, csrf: str = Query("")):
    return _accountant_export_response(request, csrf, "8949", None)


@app.get("/export.txf")
def export_all_txf(request: Request, csrf: str = Query("")):
    return _accountant_export_response(request, csrf, "txf", None)


@app.get("/export.wide.csv")
def export_all_wide(request: Request, csrf: str = Query("")):
    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf)
    except Exception:
        return Response("Forbidden", status_code=403)

    csv_text = export_all_csv_wide()
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=taxclaw-all-wide.csv"},
    )


@app.get("/export.long.csv")
def export_all_long(request: Request, csrf: str = Query("")):
    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf)
    except Exception:
        return Response("Forbidden", status_code=403)

    csv_text = export_all_csv_long()
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=taxclaw-all-long.csv"},
    )


@app.get("/export.json")
def export_all_as_json(request: Request, csrf: str = Query("")):
    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf)
    except Exception:
        return Response("Forbidden", status_code=403)

    txt = export_all_json()
    return Response(
        txt,
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=taxclaw-all.json"},
    )


@app.get("/export.originals.zip")
def export_all_originals_zip(request: Request, csrf: str = Query("")):
    """Bundle every stored original document into a single ZIP for handoff to a tax preparer or the IRS."""

    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf)
    except Exception:
        return Response("Forbidden", status_code=403)
    with db() as con:
        rows = con.execute(
            "SELECT id, original_filename, file_path, tax_year FROM documents ORDER BY created_at ASC"
        ).fetchall()

    # Build a year label from whatever tax years are present
    years = sorted({str(r["tax_year"]) for r in rows if r["tax_year"]})
    if len(years) == 1:
        year_label = years[0]
    elif len(years) > 1:
        year_label = f"{years[0]}-{years[-1]}"
    else:
        year_label = None

    zip_filename = (
        f"{year_label} Collected Tax Documents.zip" if year_label
        else "Collected Tax Documents.zip"
    )

    buf = io.BytesIO()
    seen: dict[str, int] = {}  # deduplicate filenames inside the ZIP

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        manifest_lines = [
            "TaxClaw — Original Documents Export",
            f"Tax year(s): {year_label or 'unknown'}",
            "Generated by TaxClaw (https://github.com/DougButdorf/TaxClaw)",
            "NOTICE: AI-extracted data may contain errors. Verify against source documents.",
            "",
            f"{'Filename':<60} {'Document ID'}",
            "-" * 100,
        ]
        for row in rows:
            doc_id, orig_name, file_path = row["id"], row["original_filename"], row["file_path"]
            if not file_path or not Path(file_path).exists():
                manifest_lines.append(f"{'[FILE MISSING] ' + (orig_name or doc_id):<60} {doc_id}")
                continue

            # Deduplicate filenames in ZIP (and sanitize arcnames)
            zip_name = orig_name or f"{doc_id}.pdf"
            zip_name = Path(zip_name).name
            zip_name = zip_name.replace("..", "").replace("/", "").replace("\\", "")

            if zip_name in seen:
                seen[zip_name] += 1
                stem, _, ext = zip_name.rpartition(".")
                zip_name = f"{stem}_({seen[zip_name]}).{ext}" if ext else f"{zip_name}_({seen[zip_name]})"
            else:
                seen[zip_name] = 0

            zf.write(file_path, arcname=zip_name)
            manifest_lines.append(f"{zip_name:<60} {doc_id}")

        zf.writestr("MANIFEST.txt", "\n".join(manifest_lines))

    buf.seek(0)
    # RFC 5987 encode the filename for proper Unicode/space handling in browsers
    safe_name = zip_filename.replace('"', '')
    return Response(
        buf.read(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe_name}"'},
    )


# ---------------------------------------------------------------------------
# Legal pages: /terms and /privacy
# ---------------------------------------------------------------------------

def _md_to_html(md_text: str) -> str:
    """Very lightweight Markdown → HTML converter (no external deps).
    Handles: headings, bold, horizontal rules, blockquotes, code, paragraphs.
    """
    lines = md_text.splitlines()
    html_lines: list[str] = []

    def inline(text: str) -> str:
        # Escape HTML entities first
        text = html_module.escape(text)
        # Bold: **text**
        text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
        # Italic: *text* (single)
        text = re.sub(r"\*(.+?)\*", r"<em>\1</em>", text)
        # Inline code: `text`
        text = re.sub(r"`(.+?)`", r"<code>\1</code>", text)
        # Links: [text](url)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
        return text

    in_list = False
    in_blockquote = False

    for line in lines:
        stripped = line.strip()

        # Horizontal rule
        if re.match(r"^---+$", stripped):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if in_blockquote:
                html_lines.append("</blockquote>")
                in_blockquote = False
            html_lines.append("<hr/>")
            continue

        # Headings
        m = re.match(r"^(#{1,6})\s+(.*)", stripped)
        if m:
            level = len(m.group(1))
            text = inline(m.group(2))
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            if in_blockquote:
                html_lines.append("</blockquote>")
                in_blockquote = False
            html_lines.append(f"<h{level}>{text}</h{level}>")
            continue

        # Blockquote
        if stripped.startswith("> "):
            if not in_blockquote:
                html_lines.append("<blockquote>")
                in_blockquote = True
            html_lines.append(f"<p>{inline(stripped[2:])}</p>")
            continue
        elif in_blockquote and stripped:
            html_lines.append("</blockquote>")
            in_blockquote = False

        # Unordered list items
        m2 = re.match(r"^[-*]\s+(.*)", stripped)
        if m2:
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{inline(m2.group(1))}</li>")
            continue

        # Numbered list items
        m3 = re.match(r"^\d+\.\s+(.*)", stripped)
        if m3:
            if not in_list:
                html_lines.append("<ol>")
                in_list = True
            html_lines.append(f"<li>{inline(m3.group(1))}</li>")
            continue

        # Close list on blank or non-list line
        if in_list and not stripped:
            html_lines.append("</ul>")
            in_list = False

        # Blank line → paragraph break
        if not stripped:
            html_lines.append("")
            continue

        # Regular paragraph text
        html_lines.append(f"<p>{inline(stripped)}</p>")

    if in_list:
        html_lines.append("</ul>")
    if in_blockquote:
        html_lines.append("</blockquote>")

    return "\n".join(html_lines)


_TERMS_PATH = Path(__file__).parent.parent / "TERMS.md"
_PRIVACY_PATH = Path(__file__).parent.parent / "PRIVACY.md"


@app.get("/terms", response_class=HTMLResponse)
def terms_page(request: Request):
    md_text = _TERMS_PATH.read_text(encoding="utf-8") if _TERMS_PATH.exists() else "# Terms of Use\n\nNot found."
    content_html = _md_to_html(md_text)
    return _render(
        request,
        "terms.html",
        {"request": request, "title": "Terms of Use — TaxClaw", "content": content_html},
    )


@app.get("/privacy", response_class=HTMLResponse)
def privacy_page(request: Request):
    md_text = _PRIVACY_PATH.read_text(encoding="utf-8") if _PRIVACY_PATH.exists() else "# Privacy Policy\n\nNot found."
    content_html = _md_to_html(md_text)
    return _render(
        request,
        "privacy.html",
        {"request": request, "title": "Privacy Policy — TaxClaw", "content": content_html},
    )


@app.get("/faq", response_class=HTMLResponse)
def faq_page(request: Request):
    return _render(request, "faq.html", {"request": request, "title": "FAQ — TaxClaw"})


@app.get("/contact", response_class=HTMLResponse)
def contact_page(request: Request, sent: bool = False, error: str | None = None):
    return _render(
        request,
        "contact.html",
        {
            "request": request,
            "title": "Contact & Feature Requests — TaxClaw",
            "sent": sent,
            "error": error,
        },
    )


@app.post("/contact")
async def contact_submit(
    request: Request,
    csrf_token: str = Form(...),
    name: str = Form(default=""),
    email: str = Form(default=""),
    subject: str = Form(default=""),
    message: str = Form(...),
    request_type: str = Form(default="feedback"),
):
    import json as _json
    import urllib.parse as _up
    import urllib.request as _ur

    FORMSPREE_ID = "xpqjowpa"

    try:
        _assert_same_origin(request)
        _require_csrf(request, csrf_token)
    except Exception:
        return Response("Forbidden", status_code=403)

    payload = _up.urlencode(
        {
            "name": name,
            "email": email,
            "_subject": f"[TaxClaw {request_type.title()}] {subject or message[:60]}",
            "message": message,
            "request_type": request_type,
            "_replyto": email,
        }
    ).encode()

    try:
        req = _ur.Request(
            f"https://formspree.io/f/{FORMSPREE_ID}",
            data=payload,
            headers={"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"},
        )
        with _ur.urlopen(req, timeout=8) as resp:
            result = _json.loads(resp.read())
            if result.get("ok"):
                return RedirectResponse(url="/contact?sent=true", status_code=303)
    except Exception as e:
        return _render(
            request,
            "contact.html",
            {
                "request": request,
                "title": "Contact & Feature Requests — TaxClaw",
                "sent": False,
                "error": f"Couldn't send — please email lando@outbranch.net directly. ({e})",
            },
        )

    return RedirectResponse(url="/contact?sent=true", status_code=303)
