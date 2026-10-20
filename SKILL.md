---
name: taxclaw
description: Turn tax documents (W-2, 1099-NEC/INT/DIV/B/MISC/OID/R/G/K, 1099-DA, K-1, consolidated 1099s; PDF or image) into structured JSON/CSV for accountants and tax software, locally by default. Use when the user wants to extract, read, parse or export the data on a tax form, find fields that need review, or choose a model for that. Does not prepare or file returns and is not tax advice.
license: MIT
compatibility: Python 3.11+ and bash on macOS or Linux. Local mode needs Ollama with a vision model (e.g. gemma3:4b); cloud backends are opt-in. Install into a directory named taxclaw.
metadata:
  version: "0.1.2"
  homepage: https://github.com/DougButdorf/TaxClaw
  openclaw:
    emoji: "🧾"
    homepage: https://github.com/DougButdorf/TaxClaw
    os:
      - darwin
      - linux
    requires:
      bins:
        - bash
      anyBins:
        - python3
        - python3.11
        - python3.12
        - python3.13
        - python3.14
---

# TaxClaw

Extracts the printed fields from tax documents into a local SQLite database and exports them as JSON or CSV. Local-first: the default backend (Ollama) never sends documents off the machine.

**Paths.** `{baseDir}` is this skill's directory (OpenClaw fills it in; in other Agent Skills clients use the directory that contains this SKILL.md). Every command below works from any working directory; relative file arguments resolve against the caller's cwd, but prefer absolute paths.

## Procedure

1. **Check setup.** If `{baseDir}/venv/bin/python` is missing, run `bash {baseDir}/setup.sh` (creates the venv and `~/.config/taxclaw/config.yaml`; touches nothing else). Then run `{baseDir}/bin/taxclaw models --json --offline` and read `current` (backend in use) and `tiers[0]` (Ollama reachable? vision models installed?).

2. **Choose a model.** Run `{baseDir}/bin/taxclaw models` (add `--json` to parse). Three tiers:
   - **Tier 1, local (default):** installed Ollama vision models plus a recommendation for this machine's RAM, with the `ollama pull` command if it is missing. Text-only models cannot read documents.
   - **Tier 2, cloud already configured:** providers whose API keys are present (presence only; values are never shown), with their vision models and a recommended balance/strongest pick.
   - **Tier 3, strongest with setup:** Cloudflare Clairic (per-field confidence), with setup steps.

   Keep the local backend unless the user asks for cloud. A cloud backend sends document content (SSNs, income) to that provider, so only the user may switch to it and set `privacy_acknowledged: true` (Settings page at `http://localhost:8421/settings`, or `~/.config/taxclaw/config.yaml`). Never set it on the user's behalf.

3. **Ingest.** `{baseDir}/bin/taxclaw ingest /abs/path/to/doc.pdf --filer NAME --year 2025 --json`
   Exit codes: `0` ok (JSON has `document_id`, `doc_type`, `needs_review`, `overall_confidence`); `1` extraction failed, document kept and flagged; `2` invalid file (missing, wrong type, too large); `3` backend not ready (message says why, e.g. Ollama not running). A local model takes about 15-100 s per page.

4. **Review low-confidence items.** `{baseDir}/bin/taxclaw list --needs-review 1 --json`, then `{baseDir}/bin/taxclaw export --id ID --format json` to show the fields. Ask the user to check flagged values against the original document; corrections are made in the web UI (`bash {baseDir}/start.sh`, then `http://localhost:8421/doc/ID`).

5. **Export.** `{baseDir}/bin/taxclaw export --all --format json` (or `wide` / `long` CSV; `--id ID` for one document). Write to a file the user names, e.g. `> ~/taxclaw-2025.json`.

**MCP.** `{baseDir}/bin/taxclaw mcp` runs a local stdio MCP server with `ingest_document`, `list_documents`, `get_document`, `export_documents` and `list_models`; see README for client configs.

Supported forms: W-2, 1099-NEC, 1099-INT, 1099-DIV, 1099-B, 1099-MISC, 1099-OID, 1099-R, 1099-G, 1099-K, 1099-DA, K-1 (Form 1065), consolidated 1099; Form 1040 is best-effort.

## Security and permissions

| Permission | Scope | Default |
|---|---|---|
| Read files | Only the paths you pass to `ingest` | Required |
| Write files | `~/.local/share/taxclaw/` (database, stored copies) and `~/.config/taxclaw/` | Required |
| Network, local | Web UI on `127.0.0.1:8421`; Ollama at `OLLAMA_HOST` (default `127.0.0.1:11434`) | Required |
| Network, cloud AI | Only after the user selects a cloud backend and acknowledges the privacy warning | Opt-in |
| Network, model lists | `taxclaw models` asks a provider for its model list only when that provider's key is already set | Opt-in |
| Credentials | Read from env vars at call time; presence checks only; never printed or stored by TaxClaw | Opt-in |

TaxClaw does not send telemetry, read files you did not pass to it, or send documents anywhere in local mode. The optional in-app contact form sends only what the user types to Formspree. Source: https://github.com/DougButdorf/TaxClaw (MIT).

## Not tax advice

TaxClaw is a data-extraction tool, not a tax preparation or tax advice service. It does not prepare or file returns, compute cost basis, or give tax, legal or financial advice. AI extraction can be wrong: verify every value against the original document before use. See TERMS.md and PRIVACY.md.

## Install note

The skill name is `taxclaw` and Agent Skills clients require the directory name to match, so install into a directory named `taxclaw` (for example `git clone https://github.com/DougButdorf/TaxClaw.git taxclaw`). `openclaw skills install @dougbutdorf/taxclaw` does this for you.
