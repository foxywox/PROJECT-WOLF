#!/usr/bin/env bash
# Start WOLF. On a Mac, double-click this file. On Linux: ./start-wolf.command
# First run: sets everything up and asks for your Claude API key. Later runs: just starts.
set -euo pipefail
cd "$(dirname "$0")"

pause() { if [ -t 0 ]; then read -r -p "Press Enter to close..." _; fi; }

PY=""
for c in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
    PY="$c"; break
  fi
done
if [ -z "$PY" ]; then
  echo "WOLF needs Python 3.10 or newer."
  echo "Install it from https://www.python.org/downloads/ and then run this again."
  pause; exit 1
fi

if [ ! -x .venv/bin/wolf ] || [ pyproject.toml -nt .venv/.wolf-installed ]; then
  echo "Setting up WOLF (first run takes a minute)..."
  [ -d .venv ] || "$PY" -m venv .venv
  if ! { .venv/bin/python -m pip install --upgrade pip && .venv/bin/python -m pip install -e .; } > .venv/install.log 2>&1; then
    echo "Setup failed. Details:"; tail -n 30 .venv/install.log; pause; exit 1
  fi
  touch .venv/.wolf-installed
fi

# Asks for your API key the first time, then opens the app in your browser.
# Add --host 0.0.0.0 to use WOLF from your phone on the same Wi-Fi.
.venv/bin/wolf serve --open "$@" || { pause; exit 1; }
