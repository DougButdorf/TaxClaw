# 🦅 TaxClaw
**Your taxes. Your machine. Your data.**

TaxClaw turns messy tax PDFs into clean, reviewable structured data — locally by default — so you can stop retyping boxes like it’s 1999.

- 🔒 **Local-first privacy**: keep PDFs + extracted data on your machine (SQLite)
- 🤖 **AI extraction**: local models by default, optional cloud models (Claude) if you choose
- 🧾 **Tax-form aware**: W-2, 1099s (incl. **1099-DA**), K-1, consolidated brokerage statements
- 📤 **Export-ready**: CSV today, more accountant/TurboTax/Koinly formats coming

## 🚀 Quick Start

> This repo is designed to be “clone → run.” If you hit an issue, open one — we’re iterating fast.

```bash
git clone https://github.com/DougButdorf/TaxClaw
cd TaxClaw

./setup.sh
./start.sh
# then open: http://localhost:8421
```

## 📋 What It Does
TaxClaw helps you **extract**, **organize**, and **export** the important fields from common tax documents.

**What “extraction” means:**
- You upload a PDF (scan or digital)
- TaxClaw identifies the form type (e.g., 1099-INT vs 1099-DA)
- It pulls the box/field values into typed data
- You review/edit anything that looks off
- You export structured output for the next step (CPA, spreadsheet, tax software)

**Who it’s for:**
- Anyone tired of manual data entry
- Crypto filers dealing with **1099-DA** (TY2025 is the first mandatory year)
- DIY spreadsheet workflows
- Accountants/CPAs who want clients to hand over clean data

## 🔒 Privacy First
Tax documents contain some of the most sensitive data in your life — your income, your Social Security number, your assets. Yet every tool that promises to “simplify” your taxes asks you to hand all of it to a server you don’t control.

TaxClaw is built on a different premise: **your tax documents belong on your machine.**

### Local mode (default) ✅
- 🗄️ PDFs + extracted fields stay local
- 🧾 Data stored in a local **SQLite** database
- 📡 No required account. No telemetry.

### Cloud mode (optional) ⚠️
You can opt into a cloud model (e.g., Claude) for higher accuracy on tricky scans.

- 📤 When cloud mode is enabled, document content may be sent to the selected AI provider
- ⚠️ TaxClaw should show a clear privacy warning when cloud inference is configured

**Rule of thumb:** If “never leave my machine” is non-negotiable, keep it local-only.

## 🤖 Supported Forms

| Form | Supported | Notes |
|---|---:|---|
| 🧾 W-2 | ✅ | Wages, withholding, employer info |
| 🪙 1099-DA | ✅ | First mandatory reporting year (TY2025); proceeds often present, basis often missing |
| 🧑‍💼 1099-NEC | ✅ | Nonemployee compensation |
| 🏦 1099-INT | ✅ | Interest income |
| 📈 1099-DIV | ✅ | Dividends & distributions |
| 🧓 1099-R | ✅ | Retirement distributions |
| 📉 1099-B | ✅ | Brokerage proceeds (may be within consolidated statements) |
| 🧾 1099-MISC | ✅ | Misc income |
| 🏛️ 1099-G | ✅ | Government payments (refunds, unemployment) |
| 🧾 1099-K | ✅ | Payment card / third-party network transactions |
| 🧩 K-1 | ✅ | Partnership/S-corp trust reporting |
| 📚 Consolidated 1099 | ✅ | Brokerage “mega-PDFs” (1099-INT/DIV/B bundled) |

## 📊 How It Works

1) 📥 **Upload** a PDF
2) 🏷️ **Classify** the form type (W-2, 1099-DA, etc.)
3) 🤖 **Extract** fields into structured data
4) ✅ **Review** and correct any fields that look off
5) 📤 **Export** to CSV (and more formats as they land)

## 💾 Installation

### Requirements
- 🐍 Python **3.11+**
- 🧰 macOS/Linux/WSL supported (Windows native support may vary)

### Setup
```bash
./setup.sh
```

### Run
```bash
./start.sh
```

Then open:
- 🌐 `http://localhost:8421`

### Where your data lives
- 🗄️ Local SQLite database (path configured by the app)
- 📁 Uploaded PDFs stored locally (never committed to git)

## 📤 Export & Integrations

### Exports available
- 📄 **CSV** export for spreadsheets / CPA handoff

### Coming soon
- 🧾 **TurboTax Form 8949** export (especially for 1099-DA workflows)
- 🧮 **Koinly / CoinTracker handoff** (affiliate-supported; you do calculations there, TaxClaw does document extraction here)

> TaxClaw does **not** attempt to compute cost basis. It extracts what’s on the form, so you can reconcile basis in the right specialized tool.

## 💰 Free vs Pro (planned)

|  | 🆓 Free | 💼 Pro (planned) |
|---|---|---|
| Local extraction | ✅ | ✅ |
| Unlimited documents | ✅ | ✅ |
| CSV export | ✅ | ✅ |
| Cloud model option (Claude) | — | ✅ |
| Consolidated brokerage 1099 handling | — | ✅ |
| TurboTax 8949 export | — | ✅ |
| Batch/CPA mode | — | ✅ |

## 🗺️ Roadmap

### ✅ v0.1 — MVP
- Core local-first app (FastAPI + SQLite)
- Form classification + extraction
- Reviewable structured outputs
- CSV export

### 🔜 v0.2 — Power-user exports
- TurboTax 8949 export
- Better consolidated brokerage statement parsing
- Batch/CPA workflows

### 🧠 v0.3 — Integrations
- Koinly/CoinTracker export + handoff flow
- Exchange history import (Coinbase first)
- More export templates for accountants/tax software

## 🤝 Contributing
Contributions are welcome — especially:
- new form schemas
- tricky edge-case PDFs
- export templates

(We’ll add `CONTRIBUTING.md` next.)

## 📄 License
MIT
