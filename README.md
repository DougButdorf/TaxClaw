# 🧾🦀 TaxClaw
**Your taxes. Your machine. Your data.**

TaxClaw turns messy tax PDFs into clean, reviewable structured data — **locally by default** — so you can stop retyping boxes like it’s 1999.

- 🔒 **Local-first privacy**: PDFs + extracted data stored locally (SQLite)
- 🤖 **AI extraction**: local models via Ollama by default, optional cloud models if you choose
- 🧾 **Tax-form aware**: W-2, 1099s (incl. **1099-DA**), K-1, consolidated brokerage statements
- 📤 **Export-ready**: wide/long CSV and JSON

## 🚀 Quick Start

### Install (OpenClaw)
```bash
openclaw skill install taxclaw
```

### Run
```bash
cd ~/.openclaw/workspace/skills/taxclaw
./setup.sh
./start.sh
# then open: http://localhost:8421
```

## 📋 What It Does

1) 📥 **Upload** a PDF (or image)
2) 🏷️ **Classify** the form type (W-2, 1099-DA, etc.)
3) 🤖 **Extract** fields into structured data
4) ✅ **Review** anything flagged as low-confidence
5) 📤 **Export** (CSV/JSON)

## 🔒 Privacy & Model Settings

Tax documents are extremely sensitive.

- **Local mode (default)**: extraction runs on your machine via Ollama; nothing leaves.
- **Cloud mode (optional)**: document content is sent to the configured AI provider.

You can configure the backend + model via the settings UI:
- `http://localhost:8421/settings`

## 🤖 Supported Forms (v0.1)

| Form | Supported | Notes |
|---|---:|---|
| W-2 | ✅ | Wages, withholding, employer info |
| 1099-DA | ✅ | Proceeds commonly present; basis often missing |
| 1099-NEC | ✅ | Nonemployee compensation |
| 1099-INT | ✅ | Interest income |
| 1099-DIV | ✅ | Dividends & distributions |
| 1099-R | ✅ | Retirement distributions |
| 1099-B | ✅ | Brokerage proceeds (often within consolidated statements) |
| 1099-MISC | ✅ | Misc income |
| 1099-G | ✅ | Government payments (refunds, unemployment) |
| 1099-K | ✅ | Payment card / third-party network transactions |
| K-1 | ✅ | Partnership/S-corp trust reporting |
| Consolidated 1099 | ✅ | Brokerage “mega-PDFs” (1099-INT/DIV/B bundled) |

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
