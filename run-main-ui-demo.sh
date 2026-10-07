#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT_DIR"

if [ -x "$ROOT_DIR/src/.venv/bin/python" ]; then
    PYTHON_BIN="$ROOT_DIR/src/.venv/bin/python"
else
    PYTHON_BIN="python3"
fi

exec "$PYTHON_BIN" "$ROOT_DIR/src/app-main-qml.py" "$@"
