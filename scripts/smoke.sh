#!/usr/bin/env bash
# TaxClaw smoke test. No model calls: Ollama is pointed at a closed port so
# nothing here depends on (or talks to) a running model server.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP_HOME="$(mktemp -d)"
OTHER_CWD="$(mktemp -d)"
trap 'rm -rf "$TMP_HOME" "$OTHER_CWD"' EXIT

export HOME="$TMP_HOME"
export OLLAMA_HOST="http://127.0.0.1:9"
unset ANTHROPIC_API_KEY || true

fail() { echo "[smoke] FAIL: $*" >&2; exit 1; }

echo "[smoke] python version: $(python3 -V)"

bash "$SKILL_DIR/setup.sh" >/dev/null
PY="$SKILL_DIR/venv/bin/python"
echo "[smoke] setup ok ($("$PY" -V))"

# 1) CLI from a different cwd (how agents call it) must work.
cd "$OTHER_CWD"
"$SKILL_DIR/bin/taxclaw" list >/dev/null || fail "bin/taxclaw list from $OTHER_CWD"
"$SKILL_DIR/bin/tax-extract" list >/dev/null || fail "bin/tax-extract list from $OTHER_CWD"
echo "[smoke] bin/taxclaw list from foreign cwd ok"

# 2) export --all on an empty DB.
"$SKILL_DIR/bin/taxclaw" export --all --format json > "$OTHER_CWD/empty.json" || fail "export --all --format json"
"$PY" -I - "$OTHER_CWD/empty.json" <<'PY' || fail "empty export json"
import json, sys
data = json.load(open(sys.argv[1]))
assert data["documents"] == [], data
assert "_taxclaw_notice" in data
PY
"$SKILL_DIR/bin/taxclaw" export --all --format wide >/dev/null || fail "export --all --format wide"
"$SKILL_DIR/bin/taxclaw" export --all --format long >/dev/null || fail "export --all --format long"
echo "[smoke] export --all (json/wide/long) on empty DB ok"

# 3) Ollama unreachable -> ingest fails fast with a friendly message (no traceback).
"$PY" -I - "$OTHER_CWD/blank.pdf" <<'PY'
import sys, pymupdf
d = pymupdf.open(); d.new_page(); d.save(sys.argv[1])
PY
set +e
"$SKILL_DIR/bin/taxclaw" ingest blank.pdf > "$OTHER_CWD/ingest.out" 2> "$OTHER_CWD/ingest.err"
rc=$?
set -e
[ "$rc" -ne 0 ] || fail "ingest with Ollama down should exit non-zero"
grep -q "Ollama is not reachable at http://127.0.0.1:9" "$OTHER_CWD/ingest.err" || { cat "$OTHER_CWD/ingest.err" >&2; fail "friendly Ollama error"; }
if grep -q "Traceback" "$OTHER_CWD/ingest.err"; then cat "$OTHER_CWD/ingest.err" >&2; fail "traceback on Ollama down"; fi
echo "[smoke] ingest with Ollama down -> friendly error (exit $rc) ok"

# 4) Offline unit checks + web routes via FastAPI TestClient.
cd "$OTHER_CWD"
PYTHONPATH="$SKILL_DIR" "$PY" -P - "$OTHER_CWD" <<'PY'
import json
import sys
from pathlib import Path

import pymupdf

work = Path(sys.argv[1])

from src.ai import parse_json_text
from src.classify import DOC_TYPES, classify_document
from src.config import load_config
from src.extract import PROMPTS, canonical_k1_code_key, clean_null_strings, normalize_k1, schema_for
from src.ollama_local import vision_from_show

cfg = load_config()
assert cfg.local_model == "gemma3:4b", cfg.local_model

# JSON parsing tolerates fences, commentary and trailing data ("Extra data").
assert parse_json_text('{"a": 1}\n{"b": 2}\n') == {"a": 1}
assert parse_json_text('```json\n{"a": "x"}\n```') == {"a": "x"}
assert parse_json_text('Here you go: {"a": [1, 2]} hope that helps') == {"a": [1, 2]}
assert clean_null_strings({"a": "null", "b": {"c": "None"}, "d": "0.00"}) == {"a": None, "b": {"c": None}, "d": "0.00"}

# Vision detection: capabilities first, family list only as fallback.
assert vision_from_show({"capabilities": ["completion", "vision"]})
assert not vision_from_show({"capabilities": ["completion", "tools"]})
assert not vision_from_show({"capabilities": ["embedding", "vision"]})
assert vision_from_show({"details": {"families": ["mllama"]}})

# Every classifiable form type (except best-effort 1040) has a schema-backed prompt.
for t in DOC_TYPES:
    if t in ("1040", "unknown"):
        continue
    assert t in PROMPTS, t
    sc = schema_for(t)
    assert sc and sc["properties"], t
assert schema_for("generic") is None

# K-1 coded keys are canonical box+code.
assert canonical_k1_code_key("W", "13") == "13W"
assert canonical_k1_code_key("Box 20, code Z", "20") == "20Z"
assert normalize_k1({"other_deductions": {"W": "5", "13A": "1"}})["other_deductions"] == {"13W": "5", "13A": "1"}

# Text classification routes new forms to their schemas (no model call).
def mkpdf(name: str, text: str) -> str:
    p = work / name
    d = pymupdf.open()
    pg = d.new_page()
    pg.insert_text((50, 72), text, fontsize=10)
    d.save(p)
    return str(p)

for form, text in {
    "1099-R": "Form 1099-R Distributions From Pensions, Annuities ... OMB No. 1545-0119",
    "1099-G": "Form 1099-G Certain Government Payments OMB No. 1545-0120",
    "1099-K": "Form 1099-K Payment Card and Third Party Network Transactions OMB No. 1545-2205",
    "W-2": "Form W-2 Wage and Tax Statement OMB No. 1545-0008",
}.items():
    got = classify_document(mkpdf(f"{form}.pdf", text), cfg)["doc_type"]
    assert got == form, (form, got)
print("[smoke] offline unit checks ok")

# Seed one processed document (no model) so detail/export routes have data.
from src.db import init_db
from src.store import create_document_record, ingest_file, mark_processed, store_extracted_fields, store_raw_extraction

init_db()
src_pdf = mkpdf("seed.pdf", "Form W-2 Wage and Tax Statement (synthetic smoke seed)")
dest, fhash, orig, mime = ingest_file(src_pdf, cfg)
doc_id = create_document_record(
    cfg=cfg, file_path=dest, file_hash=fhash, original_filename=orig, mime_type=mime,
    filer="smoke", tax_year=2025, doc_type="W-2", page_count=1, classification_confidence=0.9,
)
extraction = {"employer_name": "Synthetic Widgets LLC", "wages": "54321.00"}
sid = store_raw_extraction(doc_id=doc_id, form_type="W-2", data=extraction, confidence=0.9)
store_extracted_fields(doc_id=doc_id, section_id=sid, data=extraction)
mark_processed(doc_id=doc_id, overall_confidence=0.9, needs_review=False)

from src.exporter import export_all_json

data = json.loads(export_all_json())
docs = data["documents"]
assert len(docs) == 1 and docs[0]["id"] == doc_id, docs
fields = {f["field_path"]: f["field_value"] for f in docs[0]["extracted_fields"]}
assert fields.get("wages") == "54321.00", fields
assert docs[0]["extraction"] == extraction
print("[smoke] export_all_json includes extracted fields ok")

# Web UI: every HTML route returns 200.
from fastapi.testclient import TestClient

from src.main import app

client = TestClient(app, base_url="http://127.0.0.1:8421")
routes = ["/", "/documents", "/review", "/upload", "/settings", "/digital_assets",
          "/faq", "/contact", "/terms", "/privacy", f"/doc/{doc_id}"]
for r in routes:
    resp = client.get(r)
    assert resp.status_code == 200, (r, resp.status_code)
    assert "text/html" in resp.headers.get("content-type", ""), (r, resp.headers.get("content-type"))
assert client.get("/api/stats").status_code == 200
assert client.get("/affiliate-info", follow_redirects=False).status_code == 301
settings_html = client.get("/settings").text
assert "not reachable" in settings_html and "127.0.0.1:9" in settings_html
assert "sponsors" not in client.get("/").text.lower()
print(f"[smoke] {len(routes)} HTML routes returned 200")
PY

cd "$SKILL_DIR"
"$PY" -m compileall -q src >/dev/null || fail "compileall src"
echo "[smoke] compileall src ok"

echo "[smoke] ok"
