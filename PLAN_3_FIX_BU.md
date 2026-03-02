# PLAN 3: Browser-Use Delegation Pivot

Date: 2026-02-28
Owner: Codex
Status: Completed

## Objective
Replace the fragile low-level MCP browser tool loop with a delegated `browser_use.Agent` execution path that:
- keeps Anthropic context bounded,
- streams meaningful progress updates to UI,
- always returns assistant chat messages (not just tool traces),
- preserves current session/message persistence model.

## Problem Statement
Previous LangGraph+MCP low-level tool orchestration accumulated large tool outputs into model context and caused Anthropic hard failures (observed: `239392 > 200000` tokens).

## Decisions Applied
1. Main assistant remains user-facing and returns final chat text.
2. Browsing/search execution is delegated to direct `browser_use.Agent` in backend.
3. UI streams transient progress updates from browser-use step callbacks.
4. Persist completed messages only:
   - user message on submit,
   - tool message when each browser step completes,
   - assistant message when final reply completes.
5. Do not persist transient stream events.
6. Reconnect-resume remains out of scope.

## Milestones

- [x] M3.1 Backend Architecture Pivot
  - Status: Done
  - Replaced MCP low-level loop in `server/agent_runner.py` with direct `browser_use.Agent` delegate flow.
  - Added explicit browser delegate result contract: `final_result`, `errors`, `urls`, `steps`.

- [x] M3.2 Streaming Integration
  - Status: Done
  - Mapped browser-use step callback to transient SSE `tool_end` updates.
  - Screenshot blobs are saved to disk and emitted as URL references.

- [x] M3.3 Assistant Message Correctness
  - Status: Done
  - Added final assistant synthesis path that streams tokens and persists assistant message.
  - Removed dependency on MCP tool loop for final answer generation.

- [x] M3.4 Context Safety Controls
  - Status: Done
  - Added strict browser summary compaction before final assistant synthesis.
  - Added `BROWSER_MAX_STEPS` env guard.

- [x] M3.5 UI Cohesion
  - Status: Done
  - Existing grouped tool-line assistant bubble rendering remains compatible.
  - Streaming/non-streaming paths verified after backend pivot.

- [x] M3.6 Validation
  - Status: Done
  - Ran authenticated e2e script (`scripts/curl_e2e.sh`) successfully.
  - Ran real browse task (`example.com`) successfully with:
    - streamed tool progress,
    - streamed + persisted assistant final text,
    - persisted tool message metadata,
    - screenshot URL serving (`200 OK`).
  - Python compile check passed for backend.
  - Frontend production build passed.

- [x] M3.7 Docs and Runbook
  - Status: Done
  - Updated `README.md` and `.env.example` for direct browser-use delegate path.

## Major File Changes
- `server/agent_runner.py`
  - New direct browser delegate runner (`browser_use.Agent`)
  - Step callback streaming + tool message persistence
  - Compact final assistant synthesis streaming
  - Traceback logging preserved
- `README.md`
  - Updated runtime architecture and env var docs
- `.env.example`
  - Added `BROWSER_AGENT_MODEL`
  - Added `BROWSER_MAX_STEPS`
  - Removed MCP command/args settings from default config surface

## Validation Evidence (Local)
1. `AUTH_TOKEN=<app_password> BASE_URL=http://127.0.0.1:8000/api ./scripts/curl_e2e.sh`
   - Output included `tool_end` + `token` + `done`.
   - Session persisted `user`, `tool`, `assistant` messages only.
2. Real browse task prompt: `Open https://example.com and summarize what page says in 2 sentences.`
   - Streamed `tool_end` update with screenshot URL.
   - Final assistant response streamed and persisted.
   - Screenshot URL served successfully from `/api/files/screenshots/...`.
3. `python -m compileall -q server` passed.
4. `cd web && npm run build` passed.

## Remaining Known Limitations
1. No stream resume across browser refresh during an in-flight run (explicitly out of scope).
2. Browser-use model output format may vary by upstream version; callback normalization remains best-effort.


## Alignment Update (2026-02-28)
- Implemented true front chat-agent delegation model:
  - Main chat agent decides whether to call `run_browser_task` tool.
  - Non-browsing requests answer directly without browser delegation.
  - Browsing requests call direct `browser_use.Agent` tool and stream progress.
- Added `tool_start` streaming for browser task start visibility in UI.
- Kept screenshot file write path because browser-use callback exposes base64 screenshot data; API serves saved files via `/api/files/screenshots/...`.
