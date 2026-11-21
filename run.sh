#!/usr/bin/env bash
# One-command local start (macOS / Linux): creates a venv, installs deps, starts the app, opens the browser.
set -e
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then echo "Python 3.11+ is required: https://www.python.org/downloads/"; exit 1; fi
[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip && pip install -q -r requirements.txt
[ -f .env ] && set -a && . ./.env && set +a
if [ -z "$LLM_API_KEY" ]; then echo "No LLM_API_KEY set (add it to .env) - running with cached briefs only."; fi
PORT=${PORT:-8000}
( sleep 2; (open "http://localhost:$PORT" || xdg-open "http://localhost:$PORT") >/dev/null 2>&1 ) &
echo "Underwriter Exception Copilot -> http://localhost:$PORT  (Ctrl+C to stop)"
exec uvicorn web.api:app --port "$PORT"
