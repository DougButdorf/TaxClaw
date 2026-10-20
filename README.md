# 🧾🦀 TaxClaw
**Your taxes. Your machine. Your data.**

> **DISCLAIMER:** TaxClaw is a data extraction tool, not a tax preparation or tax advice service.
> It extracts text fields printed on tax documents and stores them in a local database for your
> review. TaxClaw does not prepare tax returns, file returns, compute cost basis, or provide
> tax, legal, or financial advice of any kind. AI extraction may produce errors — **always
> verify extracted data against your original documents before use.** Outbranch Network LLC
> is not a law firm, CPA firm, or tax preparation service. Use of this software does not create
> a professional relationship of any kind. See [Terms of Use](TERMS.md) and [Privacy Policy](PRIVACY.md).

TaxClaw turns messy tax PDFs into clean, reviewable structured data — **locally by default** — so you can stop retyping boxes like it’s 1999.

- 🔒 **Local-first privacy**: PDFs + extracted data stored locally (SQLite)
- 🤖 **AI extraction**: local models via Ollama by default, optional cloud models if you choose
- 🧾 **Tax-form aware**: W-2, 1099s (incl. **1099-DA**), K-1, consolidated brokerage statements; Form 1040 best-effort
- 📤 **Export-ready**: wide/long CSV and JSON

## 🚀 Quick Start

### Install (OpenClaw)
```bash
openclaw skills install @dougbutdorf/taxclaw
```

Or install manually from GitHub. The skill is named `taxclaw` and Agent Skills
clients (OpenClaw, Claude Code, Codex, Gemini CLI, Hermes, ...) require the
directory name to match, so clone into a directory named `taxclaw` (the repo
itself is `TaxClaw`):
```bash
git clone https://github.com/DougButdorf/TaxClaw.git taxclaw && cd taxclaw
```

### Local model (Ollama)
Local mode needs [Ollama](https://ollama.com) running with a **vision** model.
The default is `gemma3:4b`:
```bash
ollama pull gemma3:4b
```
Text-only models (e.g. `llama3.2`) cannot read documents; TaxClaw refuses to
run with them and tells you why. If Ollama runs somewhere other than
`http://127.0.0.1:11434`, set `OLLAMA_HOST`.

### Run
From the skill directory (wherever you installed it; OpenClaw shows it with
`openclaw skills info taxclaw`):
```bash
./setup.sh
./start.sh
# then open: http://localhost:8421
```

The CLI works from any directory (relative paths resolve against where you run it);
add `--json` to `ingest`, `list` and `models` for machine-readable output:
```bash
/path/to/taxclaw/bin/taxclaw models              # model choices for this machine
/path/to/taxclaw/bin/taxclaw ingest ./w2.pdf --json
/path/to/taxclaw/bin/taxclaw list --needs-review 1 --json
/path/to/taxclaw/bin/taxclaw export --all --format json
```

Requirements: Python 3.11+ and pip. If your system `python3` is older,
`setup.sh` will look for `python3.11` through `python3.14`; you can also
set `TAXCLAW_PYTHON=/path/to/python3.11+`.

## 📋 What It Does

1) 📥 **Upload** a PDF (or image)
2) 🏷️ **Classify** the form type (W-2, 1099-DA, etc.)
3) 🤖 **Extract** fields into structured data
4) ✅ **Review** anything flagged as low-confidence
5) 📤 **Export** (CSV/JSON)

## 🔒 Privacy & Model Settings

Tax documents are extremely sensitive.

- **Local mode (default)**: extraction runs on your machine via Ollama; your documents and extracted data never leave it.
- **Cloud mode (optional)**: document content is sent to the configured AI provider.
- **Contact form (optional)**: the in-app Contact page sends only what you type into it (name, email, message) to [Formspree](https://formspree.io), which forwards it to us. It never includes your documents or extracted tax data, and nothing is sent unless you submit the form.

You can configure the backend + model via the settings UI:
- `http://localhost:8421/settings`

## 🧠 Choosing a model (three tiers)

`taxclaw models` (or `--json`, or the Settings page) shows:

1. **Local-first (default)**: Ollama vision models installed on this machine, and a
   recommendation for its RAM, with the `ollama pull` command if it is missing.
   Starting points, *provisional until the accuracy benchmark*: 8 GB or less:
   `gemma3:4b`; 16 GB (reference: M4 Mac mini 16 GB): `gemma3:4b` default,
   `gemma3:12b` for higher accuracy (slower); 32 GB or more: `gemma3:12b`.
2. **Cloud you already have configured**: detected by the *presence* of
   `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`/`GOOGLE_API_KEY`,
   `OPENROUTER_API_KEY`, `CLOUDFLARE_ACCOUNT_ID`+`CLOUDFLARE_API_TOKEN` (values are
   never read into output). For each, the live list of vision-capable models and a
   recommended balance/strongest pick. Anthropic picks are confirmed IDs
   (`claude-haiku-5-5`, `claude-sonnet-5-5`); other providers' picks are an
   unbenchmarked heuristic over the live list. Providers configured in OpenClaw
   are listed by name only; export the key to TaxClaw's environment to use them.
3. **Strongest with setup**: Cloudflare Workers AI **Clairic**
   (`@cf/cloudflare/clairic`, preview, $0.10 per million input tokens), which
   returns per-field confidence that TaxClaw uses to flag fields for review.
   Setup steps are printed by `taxclaw models`.

Backends (`model_backend` in `config.yaml`): `local`, `anthropic` (`cloud` still
works as an alias), `openai_compat` (OpenAI, OpenRouter, Gemini's OpenAI-compatible
endpoint, or a custom base URL plus the *name* of the env var holding its key) and
`cloudflare_clairic`. Every cloud backend requires `privacy_acknowledged: true`.
Recommendations live in [`src/model_catalog.yaml`](src/model_catalog.yaml) and
can be refreshed without code changes.

## 🔌 Use TaxClaw from any agent (MCP)

`bin/taxclaw mcp` starts a local MCP server over stdio. It uses whatever backend
`~/.config/taxclaw/config.yaml` selects (local Ollama by default), so documents
stay on your machine unless you chose a cloud backend in TaxClaw.

| Tool | What it does |
|---|---|
| `ingest_document(path, filer?, tax_year?)` | Classify + extract one PDF/image at an absolute path |
| `list_documents(filer?, tax_year?, doc_type?, needs_review?)` | List stored documents |
| `get_document(document_id)` | Fields with per-field confidence (when the backend provides it) |
| `export_documents(document_id? \| all, format)` | `json`, `wide_csv` or `long_csv` content as a string |
| `list_models()` | The three model tiers above |

The server only reads the exact file path it is given (an existing regular PDF,
PNG, JPEG, TIFF or WebP within the upload size limit), never returns original
file bytes, and writes nothing but protocol messages to stdout.

Run `setup.sh` first, then use the **absolute** path to `bin/taxclaw`
(below: `/ABS/PATH/taxclaw/bin/taxclaw`).

**Claude Code** (verified with `claude mcp add` + `claude mcp list`: Connected):
```bash
claude mcp add taxclaw -- /ABS/PATH/taxclaw/bin/taxclaw mcp
```

**Claude Desktop** (`~/Library/Application Support/Claude/claude_desktop_config.json`
on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows; format per
modelcontextprotocol.io "Connect to local MCP servers"):
```json
{
  "mcpServers": {
    "taxclaw": {
      "command": "/ABS/PATH/taxclaw/bin/taxclaw",
      "args": ["mcp"]
    }
  }
}
```

**Codex** (`~/.codex/config.toml`; this is exactly what `codex mcp add taxclaw -- /ABS/PATH/taxclaw/bin/taxclaw mcp` writes):
```toml
[mcp_servers.taxclaw]
command = "/ABS/PATH/taxclaw/bin/taxclaw"
args = ["mcp"]
```

**Cursor** (`~/.cursor/mcp.json`, or `.cursor/mcp.json` in a project; format per
cursor.com/docs/mcp):
```json
{
  "mcpServers": {
    "taxclaw": {
      "type": "stdio",
      "command": "/ABS/PATH/taxclaw/bin/taxclaw",
      "args": ["mcp"]
    }
  }
}
```

**Gemini CLI** (`~/.gemini/settings.json`, or `gemini mcp add -s user taxclaw /ABS/PATH/taxclaw/bin/taxclaw mcp`;
format per the gemini-cli MCP docs):
```json
{
  "mcpServers": {
    "taxclaw": {
      "command": "/ABS/PATH/taxclaw/bin/taxclaw",
      "args": ["mcp"]
    }
  }
}
```
Gemini CLI strips variables named like `*KEY*`/`*TOKEN*` from MCP server
environments. Local mode needs none; for a TaxClaw cloud backend, pass the key
variable explicitly in that server's `env` block (e.g. `"OPENAI_API_KEY": "$OPENAI_API_KEY"`).

Claude Desktop, Cursor and Gemini CLI snippets were checked against each
product's current documentation but not run on this machine; the Claude Code and
Codex commands were run.

## 🤖 Supported Forms

| Form | Supported | Notes |
|---|---:|---|
| W-2 | ✅ | Wages, withholding, employer info, box 12 codes |
| 1099-NEC | ✅ | Nonemployee compensation |
| 1099-INT | ✅ | Interest income |
| 1099-DIV | ✅ | Dividends & distributions |
| 1099-B | ✅ | Brokerage proceeds (often within consolidated statements) |
| 1099-MISC | ✅ | Misc income |
| 1099-OID | ✅ | Original issue discount |
| 1099-R | ✅ | Retirement distributions (boxes 1–19, distribution codes, IRA/SEP/SIMPLE) |
| 1099-G | ✅ | Government payments (unemployment, state/local refunds) |
| 1099-K | ✅ | Payment card / third-party network transactions (incl. monthly 5a–5l) |
| 1099-DA | ✅ | Digital asset proceeds; basis often missing |
| K-1 (Form 1065) | ✅ | Partner's share; coded boxes keyed as box + code (e.g. `13W`, `20Z`) |
| Consolidated 1099 | ✅ | Brokerage “mega-PDFs” (1099-INT/DIV/B bundled) |
| Form 1040 | ⚠️ best-effort | Generic label/value extraction only; no form-specific schema |

## 📁 Where your data lives

By default:
- Config: `~/.config/taxclaw/config.yaml`
- Data dir: `~/.local/share/taxclaw/`
  - SQLite DB: `tax.db`
  - Stored uploads: `uploads/`

## 🤝 Contributing

PRs welcome — especially new form schemas, tricky edge-case PDFs (redacted/synthetic), and export templates.

## 📄 License

MIT (core).
