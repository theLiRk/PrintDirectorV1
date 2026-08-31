#!/usr/bin/env bash
set -eu

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python || true)}"
if [ -z "$PYTHON_BIN" ]; then
  echo "Python 3 is required but was not found on PATH." >&2
  exit 1
fi

if [ ! -d .venv ]; then
  echo "Creating virtual environment..."
  "$PYTHON_BIN" -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ ! -f config.yaml ]; then
  cp config.example.yaml config.yaml
fi

if [ ! -f .env ]; then
  cp .env.example .env
fi

if [ -n "${OBS_WEBSOCKET_PASSWORD:-}" ]; then
  python - <<'PY'
import os
from pathlib import Path
path = Path('.env')
value = os.environ.get('OBS_WEBSOCKET_PASSWORD', '')
if value:
    lines = path.read_text(encoding='utf-8').splitlines()
    updated = False
    for i, line in enumerate(lines):
        if line.startswith('OBS_WEBSOCKET_PASSWORD='):
            lines[i] = f'OBS_WEBSOCKET_PASSWORD={value}'
            updated = True
            break
    if not updated:
        lines.append(f'OBS_WEBSOCKET_PASSWORD={value}')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
PY
fi

echo
printf 'PrintDirector installed successfully.\n'
printf '\nNext steps:\n'
printf '  source .venv/bin/activate\n'
printf '  set -a && source .env && set +a\n'
printf '  python -m printdirector.main\n'
printf '\nIf you prefer to run it in demo mode:\n'
printf '  python -m printdirector.main --demo\n'
