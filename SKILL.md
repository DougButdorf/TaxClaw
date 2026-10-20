---
name: taxclaw
version: "0.1.2"
description: "Extract, store, and export tax documents (W-2, 1099-DA, all 1099 variants, K-1) using AI. Local-first — your documents never leave your machine. Web UI at localhost:8421."
argument-hint: "open TaxClaw, extract my 1099, parse this tax form, process my W-2"
allowed-tools: Bash, Read, Write
requires: python3, pip
optional: ollama (for local model mode)
---

# taxclaw

Local-first AI tax document extraction skill for OpenClaw.

## 🔐 Security & Permissions Manifest

TaxClaw declares the following permissions transparently. Review before installing.

| Permission | What & Why | Default |
|---|---|---|
| **Read filesystem** | Reads uploaded PDF/image files you provide | Required |
| **Write filesystem** | Stores extracted data at `~/.local/share/taxclaw/` and config at `~/.config/taxclaw/` | Required |
| **Network (local only)** | Binds to `localhost:8421` only and talks to your local Ollama (`OLLAMA_HOST`, default `127.0.0.1:11434`) — no external network access in default mode | Required |
| **Network (cloud AI)** | Only if you explicitly enable cloud mode in config + acknowledge privacy warning | Opt-in only |
| **Network (contact form)** | Only if you submit the optional in-app Contact form: what you type (name, email, message) is sent to Formspree (formspree.io). No documents or tax data are included | Opt-in only |
| **Credentials** | None read or stored — no API keys required in local-only mode | N/A |
| **Sensitive data** | Tax documents stay on your machine. Nothing is sent externally in default (Ollama) mode | Local-only |

**TaxClaw does NOT:**
- Exfiltrate documents, fields, or extracted data
- Read files outside of paths you explicitly provide to ingest
- Phone home, send telemetry, or contact external servers (default mode; the only exceptions are cloud mode and the optional contact form, both user-initiated)
- Store or transmit SSN, EIN, or account numbers to any third party

**If you enable cloud mode (Claude):** A mandatory privacy warning is displayed. You must explicitly set `privacy_acknowledged: true` in config before processing begins.

**Audit this skill:** Source code is fully open at [github.com/DougButdorf/TaxClaw](https://github.com/DougButdorf/TaxClaw) (MIT License). Read it before you install it.

## Setup

```bash
bash ~/.openclaw/workspace/skills/taxclaw/setup.sh
```

## Config

Config lives at:
- `~/.config/taxclaw/config.yaml`

Default is local-first (Ollama on your machine) with `local_model: gemma3:4b`. The local model must support vision (`ollama pull gemma3:4b`); TaxClaw fails fast with a clear message if Ollama is not running (honours `OLLAMA_HOST`) or the configured model is text-only. If you enable cloud mode, TaxClaw will refuse to run until you explicitly acknowledge the privacy warning in config.

Supported forms: W-2, 1099-NEC, 1099-INT, 1099-DIV, 1099-B, 1099-MISC, 1099-OID, 1099-R, 1099-G, 1099-K, 1099-DA, K-1, consolidated 1099; Form 1040 is best-effort (generic extraction).

## Start web UI

```bash
bash ~/.openclaw/workspace/skills/taxclaw/start.sh
# Open: http://localhost:8421
```

## CLI usage

`bin/taxclaw` works from any working directory; relative file paths resolve against the caller's cwd. `ingest` exits non-zero with a message on stderr if the model backend is unavailable or extraction fails.

```bash
# Ingest a document
~/.openclaw/workspace/skills/taxclaw/bin/taxclaw \
  ingest path/to/document.pdf --filer doug --year 2025

# List documents
~/.openclaw/workspace/skills/taxclaw/bin/taxclaw list

# Export (wide CSV by default)
~/.openclaw/workspace/skills/taxclaw/bin/taxclaw export --id <doc-id>

# Export long CSV
~/.openclaw/workspace/skills/taxclaw/bin/taxclaw export --id <doc-id> --format long

# Export JSON
~/.openclaw/workspace/skills/taxclaw/bin/taxclaw export --id <doc-id> --format json

# Export everything as JSON (each document includes its extracted fields)
~/.openclaw/workspace/skills/taxclaw/bin/taxclaw export --all --format json

# Start server
~/.openclaw/workspace/skills/taxclaw/bin/taxclaw serve
```

## Trigger phrases (OpenClaw agent)

- "extract my tax document"
- "parse this 1099" / "read this W-2"
- "open TaxClaw" / "start taxclaw"
- "process my tax forms"
- "show my tax documents"
