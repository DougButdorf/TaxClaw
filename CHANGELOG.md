# Changelog

## Unreleased

### Fixed
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

### Added
- Extraction schemas for 1099-R, 1099-G and 1099-K using official IRS box names; text classification recognizes 1099-G and 1099-K.
- K-1 coded boxes use canonical keys of box number + code (e.g. `13W`, `20Z`); keys returned as bare codes or "Box 13, code W" are normalized. New K-1 fields for boxes 11, 18, 19 and 21.
- `scripts/smoke.sh` is now a real test (isolated HOME, CLI from a foreign cwd, Ollama-down error, offline parser/schema/classification checks, export with fields, every HTML route 200, compileall) and fails on any error.
- GitHub Actions CI (`.github/workflows/ci.yml`): Python 3.11 and 3.13, setup + smoke + compileall.

### Changed
- README/SKILL/FAQ/Settings recommend `gemma3:4b` (glm-ocr stays a listed option). Supported-forms list updated; Form 1040 is labelled best-effort.
- Install command corrected to `openclaw skills install @dougbutdorf/taxclaw`; manual clone instructions use the `TaxClaw` directory name.
- Privacy docs disclose that the optional in-app contact form sends what you type to Formspree (never documents or tax data).

### Removed
- GitHub Sponsors links (README badge, web UI footer, `.github/FUNDING.yml` `github:` entry), the dead `https://taxclaw.net/sponsor` funding URL and the unverified `ko_fi` entry.
- `AGENTS.md` and `CLAUDE.md` (internal agent instructions); both are now gitignored.

## 0.1.2 - 2026-05-20

- Fixed setup on machines where `python3` is older than TaxClaw's current dependencies require by selecting Python 3.10+ when available and adding a clear failure message.
- Fixed POST/DELETE localhost checks so alternate local ports configured with `TAXCLAW_PORT` or config do not break forms.
- Made `start.sh` respect the configured port when `TAXCLAW_PORT` is not set.
- Aligned upload limits with `max_upload_bytes` from config and made browser upload MIME checks match the backend's supported PDF/image types.
- Corrected the OpenClaw skill documentation to use `privacy_acknowledged`, matching the actual config key.
- Made smoke tests use an isolated temporary home directory so verification does not touch a user's real TaxClaw config or data.
