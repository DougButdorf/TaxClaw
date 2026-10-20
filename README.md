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

Or install manually from GitHub (note the repo directory is `TaxClaw`):
```bash
git clone https://github.com/DougButdorf/TaxClaw.git && cd TaxClaw
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
```bash
cd ~/.openclaw/workspace/skills/taxclaw   # or your TaxClaw clone
./setup.sh
./start.sh
# then open: http://localhost:8421
```

The CLI works from any directory (relative paths resolve against where you run it):
```bash
~/.openclaw/workspace/skills/taxclaw/bin/taxclaw ingest ./w2.pdf
~/.openclaw/workspace/skills/taxclaw/bin/taxclaw export --all --format json
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
