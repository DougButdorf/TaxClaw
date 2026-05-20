#!/usr/bin/env bash
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SKILL_DIR/venv"

DATA_DIR="$HOME/.local/share/taxclaw"
CONFIG_DIR="$HOME/.config/taxclaw"
CONFIG_PATH="$CONFIG_DIR/config.yaml"

mkdir -p "$DATA_DIR" "$CONFIG_DIR"

pick_python() {
  if [ -n "${TAXCLAW_PYTHON:-}" ]; then
    printf '%s\n' "$TAXCLAW_PYTHON"
    return 0
  fi

  for candidate in python3.14 python3.13 python3.12 python3.11 python3.10 python3; do
    if ! command -v "$candidate" >/dev/null 2>&1; then
      continue
    fi
    if "$candidate" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
    then
      command -v "$candidate"
      return 0
    fi
  done

  return 1
}

PYTHON_BIN="$(pick_python || true)"
if [ -z "$PYTHON_BIN" ]; then
  echo "TaxClaw requires Python 3.10 or newer. Set TAXCLAW_PYTHON=/path/to/python3.10+ and rerun setup." >&2
  exit 2
fi
if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info >= (3, 10) else 1)
PY
then
  echo "TaxClaw requires Python 3.10 or newer; $PYTHON_BIN is too old." >&2
  exit 2
fi

echo "Using Python: $("$PYTHON_BIN" -V) ($PYTHON_BIN)"

"$PYTHON_BIN" -m venv "$VENV_DIR"

"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SKILL_DIR/requirements.txt"

if [ ! -f "$CONFIG_PATH" ]; then
  cp "$SKILL_DIR/config.yaml.example" "$CONFIG_PATH"
  echo "Created config at $CONFIG_PATH"
else
  echo "Config already exists at $CONFIG_PATH"
fi

# init db
PYTHONPATH="$SKILL_DIR" "$VENV_DIR/bin/python" -c "from src.db import init_db; init_db()"

echo
echo "✅ taxclaw setup complete"
echo "Next steps:"
echo "  1) Edit config: $CONFIG_PATH"
echo "  2) Start UI: bash $SKILL_DIR/start.sh"
