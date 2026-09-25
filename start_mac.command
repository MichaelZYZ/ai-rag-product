#!/bin/bash
set -e

cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.9 or newer is required."
  exit 1
fi
if ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 9))'; then
  echo "Python 3.9 or newer is required."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi

.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python seed.py

echo "Open http://127.0.0.1:8000 in your browser. Press Ctrl+C to stop."
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
