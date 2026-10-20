# Changelog

## 1.0.0 - TBD

TaxClaw turns tax documents into structured data for accountants and tax software. It is local-first, and 1.0 is the first release built for agents as well as people. It is not tax preparation and not tax advice.

### Upgrade notes
- Python 3.11 or newer is required. Re-run `bash setup.sh` after updating so the venv picks up the new pinned dependencies.
- The default local model is now `gemma3:4b` (vision). If your `~/.config/taxclaw/config.yaml` still says `local_model: llama3.2`, change it: llama3.2 is text-only and can't read documents. TaxClaw now stops with a clear message instead of failing every page.
- `model_backend: cloud` still works and means `anthropic`. Every non-local backend needs `privacy_acknowledged: true`.
- New: `taxclaw --version`.

### Highlights
- **Dependencies:** everything upgraded and pinned to exact versions (FastAPI 0.152, Starlette 1.9, Uvicorn 0.54, PyMuPDF 2.0, Pillow 13, Jinja2 3.1.6, python-multipart 0.0.32, Anthropic SDK 1.15, Ollama 0.6.3, MCP SDK 2.3). This replaces the Jinja2 3.1.4 and Pillow 10.4.0 pins that scanners flagged in 0.1.x. Starlette 1.x had made every web page return 500 until the template calls were fixed.
- **Fixes:** the CLI works from any directory and through symlinks; Ollama errors are readable ("Ollama is not reachable at …", model missing, model has no vision) instead of raw tracebacks; replies from models like glm-ocr that add trailing text now parse; W-2 and K-1 required-field review rules actually run; `export --all --format json` includes extracted fields; the upload page shows server errors; the config template ships under a name ClawHub publishes (`config.example.yaml`), so `setup.sh` can create a config from a ClawHub install.
- **Agent Skills portability:** SKILL.md is a short, agent-first procedure that follows the Agent Skills spec and uses `{baseDir}` instead of hardcoded OpenClaw paths, and the README gives install paths for OpenClaw, Claude Code, Codex, Gemini CLI and Hermes. `ingest`, `list` and `models` take `--json`, and `ingest` has documented exit codes. Install with `openclaw skills install @dougbutdorf/taxclaw`.
- **Model tiers and backends:** `taxclaw models` (and the Settings page) shows three tiers: (1) local Ollama vision models with a recommendation for this machine's RAM, (2) cloud providers whose API keys are already set (presence only, never values), (3) Cloudflare Workers AI Clairic with setup steps. Backends: `local` (Ollama, default), `anthropic`, `openai_compat` (OpenAI, OpenRouter, Google Gemini or any OpenAI-compatible URL) and `cloudflare_clairic` (typed fields with per-field confidence). New schemas for 1099-R, 1099-G and 1099-K; K-1 coded boxes use canonical keys like `13W`.
- **MCP server:** `taxclaw mcp` runs a local stdio MCP server with `ingest_document`, `list_documents`, `get_document`, `export_documents` and `list_models`. The README has configs for Claude Code, Claude Desktop, Codex, Cursor and Gemini CLI.
- **Exports for accountants and tax software:** `taxclaw export --format 8949` writes a Form 8949 CSV with one row per sale from 1099-B, consolidated 1099 and 1099-DA documents, with the 2025 check-box category, adjustment codes (W, D) and `needs_review` flags. Missing basis or holding periods are flagged, never guessed. `--format txf` writes TXF v042 for TurboTax Desktop-style import. Both are on the dashboard, document pages and the MCP `export_documents` tool. 1099-B statements get a per-sale extraction pass.
- **Privacy and security:**
  - Every cloud backend refuses to send anything until the privacy warning is acknowledged, in the web UI, CLI and MCP alike.
  - The docs and Settings now say what actually leaves the machine in cloud mode (full page images, to the one provider you chose), name each provider host, and disclose the optional Formspree contact form, which also gets an on-page warning.
  - The web UI refuses any request, GET included, whose Host or Origin isn't loopback, which blocks DNS-rebinding reads of documents and exports. It sends a Content-Security-Policy and no longer loads htmx from unpkg (it was never used).
  - GitHub Sponsors links are removed. CI runs the smoke test and unit tests on Python 3.11 and 3.13.

### Known limitations
- **Local small-model accuracy.** Small local models such as `gemma3:4b` can misread checkboxes and miss values such as wash-sale adjustments. Treat every flagged field as unverified and check it against the original. The local model recommendations are provisional until the accuracy benchmark lands.
- **The Form 8949 CSV is a review worksheet** when produced with a small local model, not a filing-ready schedule. Check every row, especially those with `needs_review=true`.
- **TXF can't carry 1099-DA boxes G–L.** TXF v042 has no codes for them, so those sales are skipped with a warning and appear only in the 8949 CSV.
- **Clairic and `openai_compat` aren't live-tested.** Both are covered by unit tests with mocked responses only.

<details>
<summary>Detailed change list</summary>

### Security
- Web UI: the loopback Host/Origin check now covers every request, not only POST/DELETE, so a DNS-rebinding page can't read document pages, previews, downloads or exports. IPv6 loopback (`[::1]`) is parsed correctly.
- Web UI: `Content-Security-Policy` header (same-origin scripts, styles, images and fetches only; `object-src 'none'`; `frame-ancestors 'self'`). Removed the unused `https://unpkg.com/htmx.org` script from `templates/base.html`.
- `requirements.txt`: `starlette` and `python-multipart` pinned to exact versions like the rest.
- PRIVACY.md, README, SKILL.md and Settings: cloud mode sends full rendered page images (plus the text layer for Clairic) to the selected provider; all provider hosts listed; model-list requests and `OLLAMA_HOST` disclosed; export files flagged as sensitive (RUNBOOK uses `umask 077`). SKILL.md's permission table lists every environment variable and file TaxClaw reads, setup's PyPI install, and the contact form.
- Contact page: warning that the form is sent to Formspree and shouldn't contain tax details.
- Version: `src/__init__.py` `__version__` is the single source; the FastAPI app, export metadata, TXF header, MCP server info, `taxclaw --version` and `setup.sh` use it, and unit tests check SKILL.md and RUNBOOK.md against it.

### Added
- Accountant/tax-software exports (WP-G): `taxclaw export --format 8949|txf [--id ID ...|--all]`, dashboard and document-page buttons (same CSRF check as other exports), and MCP `export_documents` formats `8949_csv` and `txf` (with `warnings` and `notice`). `src/accountant_exports.py` normalizes sales from 1099-DA transactions (UI-edited `extracted_fields` first), 1099-B/consolidated-1099 lots and the flat single-sale 1099-B fields. The Form 8949 CSV has one row per sale with columns (a)–(h), the 2025 check-box `category` (A/B/D/E for 1099-B, G/H/J/K for 1099-DA), `payer`, `confidence`, `needs_review` and `review_reasons`. Gain/loss is `Decimal` arithmetic, filled in only when proceeds and basis are both present. Wash sales map to code W and market discount to code D (IRS worksheet). Missing basis, unknown holding period or basis reporting, and a mismatch with the statement's printed gain/loss are flagged, never guessed. TXF v042 writes Format 4/5 records (refnums 321/711/323/713, CR+LF) and skips rows it can't represent, with warnings. TXF has no refnums for 1099-DA boxes G–L. README documents sources and which tax software still imports TXF.
- 1099-B and consolidated-1099 documents get a second, per-page extraction pass that reads individual sales (description, dates, proceeds, basis, wash sale, market discount, printed gain/loss, term, basis-reported flag, printed 8949 box) into a new `transactions_1099b` table, shown on the document page. Pages with a text layer that don't look like 1099-B detail are skipped. A failure here flags the document for review but keeps the main extraction. The main extraction output is unchanged.
- Three-tier model selection (WP-D): `taxclaw models [--json] [--offline] [--short]`, the Settings page and the MCP `list_models` tool show (1) installed Ollama vision models with a RAM-based recommendation and `ollama pull` commands, (2) cloud providers detected by API-key presence only (values never read into output; OpenClaw-configured providers by name only) with live vision-model lists and a balance/strongest pick, (3) Cloudflare Clairic with setup steps. Recommendations live in `src/model_catalog.yaml` with `source`/`as_of` (local picks are provisional until the accuracy benchmark). `setup.sh` prints a short version.
- Backend interface (`src/backends.py`) with `local`, `anthropic`, `openai_compat` (OpenAI, OpenRouter, Gemini's OpenAI-compatible endpoint or a custom base URL + key env var name; image as data URL; `json_schema` -> `json_object` -> plain fallback) and `cloudflare_clairic` (typed fields mapped from each form schema, per-field confidence stored in `extracted_fields.confidence`, review flags from confidence < 0.8 or ambiguous `p_null`, max 4 images per call with batching; 1099-DA transaction tables and generic forms use `clairic_fallback_backend`). Clairic is unit-tested with mocked responses only; not live-tested.
- Local MCP server (WP-E): `taxclaw mcp` (stdio, official `mcp` SDK `MCPServer`) with `ingest_document`, `list_documents`, `get_document`, `export_documents`, `list_models`. README has config snippets for Claude Code, Claude Desktop, Codex, Cursor and Gemini CLI.
- `--json` output for `taxclaw ingest`, `list` and `models`.
- Unit tests (`tests/`, stdlib unittest; mocked HTTP) and an MCP stdio client check, both run by `scripts/smoke.sh`, which also checks that runtime files survive ClawHub packaging.
- Extraction schemas for 1099-R, 1099-G and 1099-K using official IRS box names; text classification recognizes 1099-G and 1099-K.
- K-1 coded boxes use canonical keys of box number + code (e.g. `13W`, `20Z`); keys returned as bare codes or "Box 13, code W" are normalized. New K-1 fields for boxes 11, 18, 19 and 21.
- `scripts/smoke.sh` is now a real test (isolated HOME, CLI from a foreign cwd, Ollama-down error, offline parser/schema/classification checks, export with fields, every HTML route 200, compileall) and fails on any error.
- GitHub Actions CI (`.github/workflows/ci.yml`): Python 3.11 and 3.13, setup + smoke + compileall.

### Changed
- SKILL.md rewritten as a short agent-first procedure that follows the Agent Skills spec (validates with `skills-ref`): frontmatter is `name`, `description`, `license`, `compatibility`, `metadata` (version, homepage, `metadata.openclaw` gating); dropped `version`, `argument-hint`, `requires`, `optional` and `allowed-tools`; hardcoded `~/.openclaw/workspace/skills/taxclaw` paths replaced with `{baseDir}`; documents that installs must land in a directory named `taxclaw`.
- `model_backend: cloud` is now an alias for `anthropic`; any non-local backend requires `privacy_acknowledged: true` (CLI, web upload, MCP).
- The Anthropic "strongest" choice in Settings is `claude-sonnet-5-5`.
- Settings lets you choose among all three tiers; the old two-option local/cloud form is gone.
- Ollama's runner-internal digest aliases (e.g. `llamacpp:<sha256>`, Ollama 0.40+) are hidden from model lists.
- README/SKILL/FAQ/Settings recommend `gemma3:4b` (glm-ocr stays a listed option). Supported-forms list updated; Form 1040 is labelled best-effort.
- Install command corrected to `openclaw skills install @dougbutdorf/taxclaw`; manual clone instructions use the `TaxClaw` directory name.
- Privacy docs disclose that the optional in-app contact form sends what you type to Formspree (never documents or tax data).

### Fixed
- `config.yaml.example` was renamed to `config.example.yaml`: ClawHub only publishes files with known text extensions, so the old name was dropped from the published bundle and `setup.sh` could not create a config.
- `bin/taxclaw` and `bin/tax-extract` now work from any working directory (and through symlinks); previously they failed with `ModuleNotFoundError: No module named 'src'` unless run from the skill directory. Relative file arguments still resolve against the caller's cwd.
- Default `local_model` is now `gemma3:4b` (vision-capable). The old default `llama3.2` is text-only, so every extraction failed with "model does not support multimodal requests".
- Local extraction fails fast with a clear message when the configured Ollama model is not installed or lacks vision, before anything is stored.
- Ollama not running now produces "Ollama is not reachable at <host> ..." with next steps instead of a raw `[Errno 111] Connection refused` (#1). `OLLAMA_HOST` is respected.
- Vision detection in Settings uses Ollama's `/api/show` `capabilities` (falls back to the model-family list only on old Ollama builds), so gemma3, gemma4, qwen3.5 and mllama models are correctly shown as vision models.
- Ollama extraction uses structured outputs (a JSON schema derived from each form prompt is passed as `format`), and replies are parsed with `JSONDecoder.raw_decode` from the first `{`/`[`, so trailing content (e.g. glm-ocr's "Extra data") no longer breaks parsing.
- `taxclaw export --all --format json` (and `/export.json`) now include each document's `extraction` and `extracted_fields`, matching the single-document JSON export.
- Required-field review rules for W-2 and K-1 were never applied (keys `w2`/`k1` never matched the normalized types `w_2`/`k_1`).
- CLI `ingest` refuses cloud mode until `privacy_acknowledged: true`, matching the web UI, and exits non-zero with a message on stderr when extraction fails.
- Upload page now shows server-side errors (e.g. Ollama not running) instead of silently reloading.
- Starlette BadHost exposure (2026-05-27): loopback checks read the raw `Host` header instead of `request.url.hostname`.

### Removed
- GitHub Sponsors links (README badge, web UI footer, `.github/FUNDING.yml` `github:` entry), the dead `https://taxclaw.net/sponsor` funding URL and the unverified `ko_fi` entry.
- `AGENTS.md` and `CLAUDE.md` (internal agent instructions); both are now gitignored.

</details>

## 0.1.2 - 2026-05-20

- Fixed setup on machines where `python3` is older than TaxClaw's current dependencies require by selecting Python 3.10+ when available and adding a clear failure message.
- Fixed POST/DELETE localhost checks so alternate local ports configured with `TAXCLAW_PORT` or config do not break forms.
- Made `start.sh` respect the configured port when `TAXCLAW_PORT` is not set.
- Aligned upload limits with `max_upload_bytes` from config and made browser upload MIME checks match the backend's supported PDF/image types.
- Corrected the OpenClaw skill documentation to use `privacy_acknowledged`, matching the actual config key.
- Made smoke tests use an isolated temporary home directory so verification does not touch a user's real TaxClaw config or data.
