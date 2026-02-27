#!/usr/bin/env bash
set -euo pipefail

cleanup() {
  if [[ -n "${VITE_PID:-}" ]]; then
    kill "$VITE_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT

if [[ -d "web" ]]; then
  pushd web >/dev/null
  if [[ ! -d "node_modules" ]]; then
    npm install
  fi
  npm run dev -- --host 0.0.0.0 --port 5173 &
  VITE_PID=$!
  popd >/dev/null
fi

uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
