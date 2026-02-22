#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SKILL_DIR/venv/bin/activate"

exec uvicorn src.main:app --host 127.0.0.1 --port 8421 --reload
