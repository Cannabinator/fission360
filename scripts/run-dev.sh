#!/usr/bin/env bash
# Run from a source checkout using a local virtualenv (.venv).
set -euo pipefail
HERE="$(cd "$(dirname "$0")/.." && pwd)"
if [ ! -x "$HERE/.venv/bin/python" ]; then
  python3 -m venv "$HERE/.venv"
  "$HERE/.venv/bin/pip" install -e "$HERE[dev]"
fi
exec "$HERE/.venv/bin/python" -m fission360 "$@"
