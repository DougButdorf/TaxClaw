#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$SKILL_DIR/venv/bin/activate"

# Use TAXCLAW_PORT first, then ~/.config/taxclaw/config.yaml, then default.
PORT="${TAXCLAW_PORT:-}"
if [ -z "$PORT" ]; then
  PORT="$("$SKILL_DIR/venv/bin/python" - <<'PY'
from pathlib import Path
import os
import yaml

cfg_path = Path(os.path.expanduser("~/.config/taxclaw/config.yaml"))
if cfg_path.exists():
    data = yaml.safe_load(cfg_path.read_text()) or {}
    print(data.get("port") or 8421)
else:
    print(8421)
PY
)"
fi

cd "$SKILL_DIR"
exec uvicorn src.main:app --host 127.0.0.1 --port "$PORT" --reload
