---
name: taxclaw
version: "0.1.0-beta"
description: "Extract, store, and export tax documents (W-2, 1099-DA, all 1099 variants, K-1) using AI. Local-first — your documents never leave your machine. Web UI at localhost:8421."
argument-hint: "open TaxClaw, extract my 1099, parse this tax form, process my W-2"
allowed-tools: Bash, Read, Write
requires: python3, pip
optional: ollama (for local model mode)
---

# taxclaw

Local-first AI tax document extraction skill for OpenClaw.

## Setup

```bash
bash ~/.openclaw/workspace/skills/taxclaw/setup.sh
```

## Config

Config lives at:
- `~/.config/taxclaw/config.yaml`

Default is local-first (Ollama on your machine). If you enable cloud mode, TaxClaw will refuse to run until you explicitly acknowledge the privacy warning in config.

## Start web UI

```bash
bash ~/.openclaw/workspace/skills/taxclaw/start.sh
# Open: http://localhost:8421
```

## CLI usage

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

# Start server
~/.openclaw/workspace/skills/taxclaw/bin/taxclaw serve
```

## Trigger phrases (OpenClaw agent)

- "extract my tax document"
- "parse this 1099" / "read this W-2"
- "open TaxClaw" / "start taxclaw"
- "process my tax forms"
- "show my tax documents"
