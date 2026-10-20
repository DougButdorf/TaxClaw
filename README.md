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
5) 📤 **Export** (CSV/JSON, plus Form 8949-ready CSV and TXF for capital-gain sales)

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

## 🧾 Exports for accountants and tax software

TaxClaw can export capital-gain sales from 1099-B, consolidated 1099 and
1099-DA documents in two extra formats. Both formats are built from the same
normalized sales: 1099-DA transactions, plus the per-sale rows that a separate
extraction pass reads from 1099-B detail tables. They are not a tax return,
and TaxClaw does not decide how anything should be reported.

```bash
bin/taxclaw export --format 8949 --all > form8949.csv        # or --id DOC [--id DOC2 ...]
bin/taxclaw export --format txf  --all > capital-gains.txf
```

The same exports are on the dashboard ("Form 8949 CSV", "TXF") and on each
1099-B/1099-DA/consolidated document page. The MCP `export_documents` tool also
offers them as `format: "8949_csv"` and `format: "txf"`, and returns `warnings`
and `notice` alongside the content.

**Form 8949 CSV.** The file has one row per sale, in the 2025 Form 8949 layout:
- `a_description`, `b_date_acquired`, `c_date_sold`, `d_proceeds`, `e_cost_basis`, `f_adjustment_codes`, `g_adjustment_amount`, `h_gain_or_loss`;
- `category`, the box to check;
- `part` (I = short-term, II = long-term) and `term`;
- `source_document_id`, `source_form`, `payer` and `confidence`;
- `needs_review` and `review_reasons`.

| Reported on | Basis reported to IRS | Short-term (Part I) | Long-term (Part II) |
|---|---|---|---|
| Form 1099-B | yes | A | D |
| Form 1099-B | no | B | E |
| Form 1099-DA | yes | G | J |
| Form 1099-DA | no | H | K |

Boxes C/F/I/L cover sales that weren't reported on a 1099-B or 1099-DA. TaxClaw
never assigns them, because every sale it exports comes from a broker form.

Rules the CSV follows:
- **Column (h).** It is (d) − (e) + (g), computed with `Decimal` and rounded half-up to cents. It is filled in only when proceeds and basis are both present. Otherwise (h) is blank and the row is flagged; a common example is "basis missing — common for 1099-DA". Basis is never guessed.
- **Holding period.** TaxClaw uses the form's short/long flag, or a Form 8949 box letter printed on the statement. If neither is there, it uses the dates: more than one year is long-term, counting from the day after acquisition. If none of these work, the term and category are blank and the row is flagged. "INHERITED" counts as long-term. When the form's flag and the dates disagree, the flag is used and the row is flagged.
- **Basis reporting.** This decides between A/D and B/E (or G/J and H/K). TaxClaw reads it from the form's "basis reported to IRS" or "noncovered" checkbox. If neither is visible, the category is left blank and the row is flagged. A box letter printed on the statement is only a cross-check, and a mismatch is flagged.
- **Adjustments.**
  - A wash-sale loss disallowed on the form becomes code `W`, with the amount as a positive number in (g).
  - Accrued market discount becomes code `D`. The amount comes from the IRS worksheet: minus the smaller of the gain and the discount. That figure is 0 if you elected to include market discount in income currently, so these rows are always flagged.
  - Multiple codes are written in alphabetical order (e.g. `DW`), with the net amount in (g).
  - A row is flagged when the gain or loss printed on the statement differs from the computed (h). This usually means a wash sale or basis value was misread.
- **Review flags.** Every row from a document flagged for review is also flagged.

**TXF (Tax Exchange Format) v042.** TXF records are written in Format 4, or in Format 5 when there is a wash-sale amount:
- Each record has a `TD` type, a refnum, `C1`, `L1`, `P` for the description, two `D` lines (date acquired, date sold), `$` cost, `$` sales net and an optional `$` for the disallowed wash sale.
- Refnums are 321/711 (short-term, 8949 box A/B) and 323/713 (long-term, box D/E). The file uses ASCII with CR+LF line endings.
- TXF has no comment lines, so the AI-extraction/not-tax-advice notice is printed on stderr by the CLI, returned as `notice` by MCP and sent as an `X-TaxClaw-Notice` header by the web app.

TaxClaw skips the following rows rather than writing a partial or guessed record, and lists each one as a warning:
- **1099-DA sales (boxes G–L).** TXF v042 was last revised in 2011 and has no reference numbers for these boxes; use the 8949 CSV for them.
- **Rows missing basis or dates, or with an unknown box.**
- **Rows with adjustment codes other than W.**
- **Rows whose extracted values contradict each other.** Examples: the computed (h) differs from the statement's printed gain/loss, the form's flag and the dates disagree on the term, or the printed box letter doesn't match the form's checkboxes.

Which software imports TXF, as of October 2026:
- **TurboTax Desktop: yes.** Intuit documents File → Import → From Accounting Software (Windows) / From TXF Files (Mac).
- **TurboTax Online: no.** Intuit has no page that says so directly. Its TXF help article covers Desktop only, [Quicken](https://www.quicken.com/support/quicken-windows-how-transfer-tax-information-quicken-turbotax) says TurboTax Online no longer supports Quicken import, and [Tax Data Exchange](https://taxdataexchange.org/docs/txf/v042/index.html) knows of no web-based software that imports TXF.
- **H&R Block Desktop: probably.** Only third-party guides document importing TXF through File → Import Financial Information; we found no H&R Block page that mentions TXF.
- **H&R Block Online: no evidence of TXF import.**
- **TaxAct: no evidence.** Its current help pages describe CSV import of 1099-B/8949 data. TaxAct also limits descriptions to 34 characters and doesn't accept "various" as a date sold.
- **FreeTaxUSA: no evidence.** Its import page offers PDF and stock/crypto form uploads.

Whether TurboTax Desktop maps imported TXF rows to the new 2025 boxes has not been verified. If in doubt, give your preparer the 8949 CSV.

Sources:
- [Form 8949 (2025)](https://www.irs.gov/pub/irs-pdf/f8949.pdf) and its [instructions](https://www.irs.gov/pub/irs-pdf/i8949.pdf). The [2026 draft form](https://www.irs.gov/pub/irs-dft/f8949--dft.pdf) has the same boxes and columns.
- The [TXF v042 spec](https://taxdataexchange.org/docs/txf/v042/txf-spec.html) and its [overview](https://taxdataexchange.org/docs/txf/v042/index.html), as published by Tax Data Exchange.
- Intuit, [Import a TXF file](https://ttlc.intuit.com/turbotax-support/en-us/help-article/import-export-data-files/import-txf-file/L47YK56cd_US_en_US).
- TaxAct, [Form 8949 and Form 1099-B](https://support.taxact.com/support/22389/form-8949-and-form-1099-b-enter-stock-transactions).

> AI-extracted data may contain errors. Check every row against the broker statement, especially rows with `needs_review=true`. This is not tax advice.

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
