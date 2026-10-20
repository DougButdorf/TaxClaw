# TaxClaw v1.0.0 Runbook

## Setup

```bash
cd /path/to/taxclaw   # the skill directory
bash setup.sh

# Config is created (if missing) at:
#   ~/.config/taxclaw/config.yaml
```

TaxClaw requires Python 3.11+. If `python3` points to an older interpreter,
`setup.sh` will try `python3.11` through `python3.14`. Override with
`TAXCLAW_PYTHON=/path/to/python3.11+ bash setup.sh` when needed.

`setup.sh` creates `venv/` inside the skill directory and installs the pinned
packages in `requirements.txt` from PyPI (the only network access during setup).

Check the installed version with `./bin/taxclaw --version`.

## Start the web UI

```bash
cd /path/to/taxclaw   # the skill directory
bash start.sh
# open http://localhost:8421
```

## Ingest via CLI

```bash
cd /path/to/taxclaw   # the skill directory
./bin/taxclaw ingest /path/to/doc.pdf --filer doug --year 2025

./bin/taxclaw list
```

## Export

Exports contain the same sensitive data as the documents themselves (names,
SSNs/TINs, account numbers, amounts). Write them to a private directory, not
a synced or shared folder, and delete them when you are done. The examples
use `umask 077` so the files are readable only by you.

### Single document

```bash
umask 077
./bin/taxclaw export --id <doc-id> --format wide > out-wide.csv
./bin/taxclaw export --id <doc-id> --format long > out-long.csv
./bin/taxclaw export --id <doc-id> --format json > out.json
```

### All documents

```bash
umask 077
./bin/taxclaw export --all --format wide > taxclaw-all-wide.csv
./bin/taxclaw export --all --format long > taxclaw-all-long.csv
./bin/taxclaw export --all --format json > taxclaw-all.json
```

### Capital-gain sales for an accountant or tax software

```bash
umask 077
./bin/taxclaw export --all --format 8949 > form8949-review.csv   # review worksheet; check needs_review rows
./bin/taxclaw export --all --format txf > taxclaw.txf            # TXF v042 (TurboTax Desktop-style import)
```

Warnings (skipped rows, missing basis or dates) go to stderr. TXF cannot carry
1099-DA boxes G–L, so those sales appear only in the 8949 CSV.

## Smoke test

```bash
cd /path/to/taxclaw   # the skill directory
./scripts/smoke.sh
```
