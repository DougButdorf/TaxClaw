---
name: tax-extractor
version: "0.1.0-beta"
description: "Extract, store, and export tax documents (W-2, 1099-DA, all 1099 variants, K-1) using AI. Local-first — your documents never leave your machine. Web UI at localhost:8421."
argument-hint: "extract my 1099, parse this tax form, open tax extractor, process my W-2"
allowed-tools: Bash, Read, Write
requires: python3, pip
optional: ollama (for local model mode)
---

# tax-extractor

Local-first AI tax document extraction skill for OpenClaw.

## Setup

```bash
bash ~/.openclaw/workspace/skills/tax-extractor/setup.sh
```

## Start web UI

```bash
bash ~/.openclaw/workspace/skills/tax-extractor/start.sh
# Opens http://localhost:8421
```

## CLI usage

```bash
# Ingest a document
~/.openclaw/workspace/skills/tax-extractor/venv/bin/python \
  ~/.openclaw/workspace/skills/tax-extractor/bin/tax-extract \
  ingest path/to/document.pdf --filer doug --year 2025

# List documents
~/.openclaw/workspace/skills/tax-extractor/venv/bin/python \
  ~/.openclaw/workspace/skills/tax-extractor/bin/tax-extract \
  list

# Export CSV
~/.openclaw/workspace/skills/tax-extractor/venv/bin/python \
  ~/.openclaw/workspace/skills/tax-extractor/bin/tax-extract \
  export --id <doc-id>

# Start server
~/.openclaw/workspace/skills/tax-extractor/venv/bin/python \
  ~/.openclaw/workspace/skills/tax-extractor/bin/tax-extract \
  serve
```

## Trigger phrases (OpenClaw agent)

- "extract my tax document"
- "parse this 1099" / "read this W-2"
- "open tax extractor"
- "process my tax forms"
- "show my tax documents"
