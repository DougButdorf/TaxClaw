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
# No cloud calls in the smoke test: drop any provider keys from the environment.
unset ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY GOOGLE_API_KEY OPENROUTER_API_KEY \
  CLOUDFLARE_ACCOUNT_ID CLOUDFLARE_API_TOKEN OPENCLAW_CONFIG_PATH OPENCLAW_STATE_DIR || true

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

# 3b) Machine-readable CLI output for agents: list/ingest/models --json.
"$SKILL_DIR/bin/taxclaw" list --json > "$OTHER_CWD/list.json" || fail "list --json"
set +e
"$SKILL_DIR/bin/taxclaw" ingest blank.pdf --json > "$OTHER_CWD/ingest.json" 2>/dev/null
rc=$?
set -e
[ "$rc" -eq 3 ] || fail "ingest --json with Ollama down should exit 3 (got $rc)"
"$SKILL_DIR/bin/taxclaw" models --json --offline > "$OTHER_CWD/models.json" || fail "models --json --offline"
"$PY" -I - "$OTHER_CWD" <<'PY' || fail "--json outputs"
import json, sys
from pathlib import Path
w = Path(sys.argv[1])
lst = json.loads((w / "list.json").read_text())
assert lst == {"documents": [], "count": 0}, lst
ing = json.loads((w / "ingest.json").read_text())
assert ing["ok"] is False and ing["stage"] == "backend" and "Ollama is not reachable" in ing["error"], ing
m = json.loads((w / "models.json").read_text())
t1, t2, t3 = m["tiers"]
assert (t1["tier"], t2["tier"], t3["tier"]) == (1, 2, 3)
assert t1["ollama_reachable"] is False and t1["recommended"][0]["model"] == "gemma3:4b", t1
assert t1["recommended"][0]["pull_command"] == "ollama pull gemma3:4b"
assert t2["presence_only"] is True
for p in t2["providers"]:
    assert all(isinstance(v, bool) for v in p["env_presence"].values()), p
    assert p["configured"] is False, p
assert t3["options"][0]["id"] == "cloudflare_clairic" and t3["options"][0]["configured"] is False
assert m["current"]["model_backend"] == "local"
PY
echo "[smoke] list/ingest/models --json ok"

# 3c) Unit tests (Clairic adapter, openai_compat, tiers; mocked HTTP, no network).
PYTHONPATH="$SKILL_DIR" "$PY" -P -m unittest discover -s "$SKILL_DIR/tests" -t "$SKILL_DIR" 2> "$OTHER_CWD/unittest.err" \
  || { cat "$OTHER_CWD/unittest.err" >&2; fail "unit tests"; }
echo "[smoke] unit tests ok ($(grep -Eo 'Ran [0-9]+ tests' "$OTHER_CWD/unittest.err"))"

# 3d) MCP server over stdio with a real client: initialize, list tools, list_models, list_documents.
"$PY" -P "$SKILL_DIR/tests/mcp_stdio_client.py" --server "$SKILL_DIR/bin/taxclaw" > "$OTHER_CWD/mcp.out" 2> "$OTHER_CWD/mcp.err" \
  || { cat "$OTHER_CWD/mcp.out" "$OTHER_CWD/mcp.err" >&2; fail "MCP stdio client"; }
grep -q "list_documents ok: count=0" "$OTHER_CWD/mcp.out" || { cat "$OTHER_CWD/mcp.out" >&2; fail "MCP list_documents"; }
echo "[smoke] MCP stdio: $(grep -c '^\[mcp-client\]' "$OTHER_CWD/mcp.out") client checks ok"

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
for marker in ("Tier 1", "Tier 2", "Tier 3", 'value="anthropic"', 'value="openai_compat"', 'value="cloudflare_clairic"', "privacy-ack"):
    assert marker in settings_html, marker
assert "sponsors" not in client.get("/").text.lower()
print(f"[smoke] {len(routes)} HTML routes returned 200 (Settings shows tiers 1-3)")

# Settings: every cloud choice requires the privacy acknowledgment; local saves.
import re as _re

from src.config import load_config as _load

tok = _re.search(r'name="csrf_token" value="([^"]+)"', settings_html).group(1)
for backend in ("anthropic", "openai_compat", "cloudflare_clairic", "cloud"):
    r = client.post("/settings", data={"csrf_token": tok, "model_backend": backend}, follow_redirects=False)
    assert r.status_code == 200 and "privacy confirmation" in r.text, (backend, r.status_code)
    assert _load().backend == "local", backend  # not saved
r = client.post("/settings", data={"csrf_token": tok, "model_backend": "openai_compat", "openai_compat_provider": "custom",
                                    "openai_compat_api_key_env": "sk-not-an-env-name", "privacy_acknowledged": "1"}, follow_redirects=False)
assert r.status_code == 200 and "environment variable NAME" in r.text, r.status_code
r = client.post("/settings", data={"csrf_token": tok, "model_backend": "openai_compat", "openai_compat_provider": "openrouter",
                                    "openai_compat_model": "vendor/some-vision-model", "privacy_acknowledged": "1"}, follow_redirects=False)
assert r.status_code == 303, r.status_code
c = _load()
assert (c.backend, c.openai_compat_provider, c.privacy_acknowledged) == ("openai_compat", "openrouter", True), c
assert client.get("/settings").status_code == 200
r = client.post("/settings", data={"csrf_token": tok, "model_backend": "local", "local_model": "gemma3:4b"}, follow_redirects=False)
assert r.status_code == 303 and _load().backend == "local" and _load().privacy_acknowledged is False
print("[smoke] settings: cloud choices require privacy ack; save/restore ok")
PY

# 5) Packaging: ClawHub publishes only text files with allowed extensions (plus
# extensionless text) and honours .gitignore/.clawhubignore. Runtime files must survive.
"$PY" -I - "$SKILL_DIR" <<'PY' || fail "packaging check"
import subprocess, sys
from pathlib import Path
root = Path(sys.argv[1])
# clawhub 0.23.0 dist/schema/textFiles.js
allowed = set("md mdx txt json json5 yaml yml toml js cjs mjs ts tsx jsx py sh ps1 psm1 psd1 r rb go rs swift kt java cs cpp c h hpp sql csv tsv ini cfg conf env properties dat xml html css scss sass svg".split())
required = ["SKILL.md", "setup.sh", "start.sh", "requirements.txt", "config.example.yaml", "bin/taxclaw", "bin/tax-extract",
            "src/model_catalog.yaml", "src/mcp_server.py", "templates/settings.html", "scripts/smoke.sh"]
try:
    tracked = subprocess.run(["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True).stdout.split()
except Exception:
    print("[smoke] packaging: git unavailable, checking required files only")
    tracked = required
for rel in tracked:
    if rel.split("/")[0] not in ("bin", "src", "templates", "scripts", "tests") and rel not in required:
        continue
    ext = rel.rsplit(".", 1)[-1].lower() if "." in Path(rel).name else ""
    assert (root / rel).is_file(), rel
    assert ext in allowed or not ext, f"{rel}: .{ext} would be dropped by ClawHub"
    if not ext:
        (root / rel).read_bytes().decode("utf-8")
for rel in required:
    assert (root / rel).is_file(), rel
    ignored = subprocess.run(["git", "-C", str(root), "check-ignore", "-q", "--no-index", rel]).returncode == 0
    assert not ignored, f"{rel} is excluded by an ignore file"
print(f"[smoke] packaging: {len(required)} required runtime files present, not ignored, ClawHub-publishable")
PY

cd "$SKILL_DIR"
"$PY" -m compileall -q src >/dev/null || fail "compileall src"
echo "[smoke] compileall src ok"

echo "[smoke] ok"
