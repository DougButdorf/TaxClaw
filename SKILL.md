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

1. **Run the doctor.** If `{baseDir}/venv/bin/python` is missing, run `bash {baseDir}/setup.sh` first (creates the venv and `~/.config/taxclaw/config.yaml`; it ends by running the doctor). Then run `{baseDir}/bin/taxclaw doctor --json`. It is read-only and exits 0. Read `ready`, `next_step`, `local.state`, `current`, `cloud.usable` and `hosted`.
   - If `ready` is true, go to step 3.
   - If it is false, stop and present the three paths to the user in plain words, then ask which they want:
     1. **Local, on this machine (private).** Say what `local.state` means and give `local.next_step`: `ollama_missing` (install Ollama; a new terminal or an agent restart may be needed so PATH finds it), `server_unreachable` (open the Ollama app or run `ollama serve`), `no_vision_model` (the recommended model with its approx. download size and `ollama pull <model>`), `model_not_selected` (`taxclaw use-local --model <name>`). Pass on any `local.warnings` about RAM or disk.
     2. **Cloud with their own API keys.** List `cloud.usable` best to worst. Say plainly that full page images of their tax documents (SSNs, income, account numbers) would leave this machine, that the provider's terms apply, and that they switch with `taxclaw use-cloud <backend> --accept-privacy`, which prints the privacy text first and records their consent.
     3. **TaxClaw Cloud (hosted).** Say it is coming soon. Quote pricing only if `hosted.enabled` is true.
   - **Never choose cloud on the user's behalf.** Do not run `use-cloud`, and do not set `privacy_acknowledged` or edit config for them; that consent is theirs. The MCP server has no tool that does it.
   - **Never run install or pull commands** (`brew install`, the Ollama install script, `ollama pull`) without the user's OK. After they approve and the command finishes, run the doctor again.
   - Run `{baseDir}/bin/taxclaw use-local [--model NAME]` only to switch back to local (no consent needed), when the user asks.

2. **Choose a model (optional).** `{baseDir}/bin/taxclaw models` (add `--json`) lists installed local vision models, cloud models for keys that are present, and Cloudflare Clairic with its setup steps. Keep the local backend unless the user chose cloud in step 1.

3. **Ingest.** `{baseDir}/bin/taxclaw ingest /abs/path/to/doc.pdf --filer NAME --year 2025 --json`
   Exit codes: `0` ok (JSON has `document_id`, `doc_type`, `needs_review`, `overall_confidence` and `processed_by`: backend, model, `documents_left_machine`); `1` extraction failed, document kept and flagged; `2` invalid file (missing, wrong type, too large); `3` backend not ready (the message says why and `next_step` says what to do; take it to the user, step 1). A local model takes about 15-100 s per page.

4. **Review low-confidence items.** `{baseDir}/bin/taxclaw list --needs-review 1 --json`, then `{baseDir}/bin/taxclaw export --id ID --format json` to show the fields. Ask the user to check flagged values against the original document; corrections are made in the web UI (`bash {baseDir}/start.sh`, then `http://localhost:8421/doc/ID`).

5. **Export.** `{baseDir}/bin/taxclaw export --all --format json` (or `wide` / `long` CSV; `--id ID` for one document). Write to a file the user names, e.g. `> ~/taxclaw-2025.json`.
   For an accountant or tax software, export capital-gain sales from 1099-B, consolidated 1099 and 1099-DA documents:
   - `--format 8949` writes a Form 8949-ready CSV: one row per sale, with the check-box `category` and `needs_review`/`review_reasons`.
   - `--format txf` writes TXF v042 for TurboTax Desktop-style import.
   - Both take `--all` or one or more `--id`. The notice and warnings go to stderr. Relay them to the user, including the rows TXF skipped: 1099-DA sales, missing basis, missing dates.
   - Tell the user that rows with `needs_review=true` have a blank gain/loss or category on purpose.
   - Never fill in missing basis or holding periods yourself.

**MCP.** `{baseDir}/bin/taxclaw mcp` runs a local stdio MCP server with `setup_status` (the doctor), `ingest_document`, `list_documents`, `get_document`, `export_documents` and `list_models`; see README for client configs.

Supported forms: W-2, 1099-NEC, 1099-INT, 1099-DIV, 1099-B, 1099-MISC, 1099-OID, 1099-R, 1099-G, 1099-K, 1099-DA, K-1 (Form 1065), consolidated 1099; Form 1040 is best-effort.

## Security and permissions

| Permission | Scope | Default |
|---|---|---|
| Read files | Only the paths you pass to `ingest` | Required |
| Write files | `~/.local/share/taxclaw/` (database, stored copies) and `~/.config/taxclaw/` (`doctor` writes nothing) | Required |
| Network, local | Web UI on `127.0.0.1:8421`; Ollama at `OLLAMA_HOST` (default `127.0.0.1:11434`) | Required |
| Network, cloud AI | Only after the user selects a cloud backend and gives recorded consent (`use-cloud --accept-privacy` or Settings) | Opt-in |
| Network, model lists | `taxclaw models` (not `doctor`) asks a provider for its model list only when that provider's key is already set | Opt-in |
| Credentials | Read from env vars at call time; presence checks only; never printed or stored by TaxClaw | Opt-in |

TaxClaw does not send telemetry, read files you did not pass to it, or send documents anywhere in local mode. The optional in-app contact form sends only what the user types to Formspree. Source: https://github.com/DougButdorf/TaxClaw (MIT).

## Not tax advice

TaxClaw is a data-extraction tool, not a tax preparation or tax advice service. It does not prepare or file returns, compute cost basis, or give tax, legal or financial advice. AI extraction can be wrong: verify every value against the original document before use. See TERMS.md and PRIVACY.md.

## Install note

The skill name is `taxclaw` and Agent Skills clients require the directory name to match, so install into a directory named `taxclaw` (for example `git clone https://github.com/DougButdorf/TaxClaw.git taxclaw`). `openclaw skills install @dougbutdorf/taxclaw` does this for you.
