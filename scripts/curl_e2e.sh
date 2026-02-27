#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000/api}"
AUTH_HEADER=()
if [[ -n "${AUTH_TOKEN:-}" ]]; then
  AUTH_HEADER=(-H "x-auth: ${AUTH_TOKEN}")
fi

session_json="$(curl -sS -X POST "${AUTH_HEADER[@]}" "$BASE_URL/sessions")"
session_id="$(python -c 'import json,sys; print(json.loads(sys.stdin.read())["id"])' <<< "$session_json")"

echo "session_id=$session_id"

curl -sS -X POST "$BASE_URL/sessions/$session_id/messages" \
  "${AUTH_HEADER[@]}" \
  -H 'content-type: application/json' \
  -d '{"content":"this is a ping test: do not think, respond as quickly as possible with any noun"}' >/dev/null

# stream stops on done/error
if [[ -n "${AUTH_TOKEN:-}" ]]; then
  curl -sS -N "$BASE_URL/sessions/$session_id/stream?auth=${AUTH_TOKEN}"
else
  curl -sS -N "$BASE_URL/sessions/$session_id/stream"
fi

echo
curl -sS "${AUTH_HEADER[@]}" "$BASE_URL/sessions/$session_id"
