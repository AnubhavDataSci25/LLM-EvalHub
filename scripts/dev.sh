#!/usr/bin/env bash
# Start the backend and frontend together for local development.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "→ backend  http://localhost:8000  (docs at /docs)"
(cd "$ROOT/backend" && uvicorn app.main:app --reload --port 8000) &

echo "→ frontend http://localhost:5173"
(cd "$ROOT/frontend" && npm run dev) &

wait
