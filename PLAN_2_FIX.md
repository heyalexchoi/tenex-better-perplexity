# PLAN 2 - LANGGRAPH MCP MESSAGE-FIRST

## Objective
Migrate agent orchestration from direct `browser_use.Agent` wiring to LangGraph + browser-use MCP with a message-first runtime:
1. Persist completed messages only.
2. Stream only the currently in-progress assistant/tool activity.
3. Persist assistant + tool messages as each message completes to keep DB state aligned with runtime.

## Priority Shift
This plan supersedes the earlier fix-first sequence. We will prioritize migration infrastructure first, then close any UI/behavior regressions caused by migration.

## Scope
1. Replace current runner internals with LangGraph `create_agent` + MCP browser tools.
2. Keep streaming runtime state in-memory for current response only (no persistent event log).
3. Update SSE contract to explicit event types for token/tool/final/error.
4. Keep real-mode behavior default and retain mock mode for cheap deterministic dev checks.
5. Preserve auth, session persistence, cancel semantics, and migration/runtime DB consistency decisions.
6. Store screenshots on disk volume and persist file reference in tool messages.

## Explicit Concerns to Verify During Migration
1. MCP tool inventory and schemas must be discovered via runtime `list_tools()`, not assumed.
2. Stateful browser session behavior must be validated for `MultiServerMCPClient.get_tools()` vs explicit `session("browser")`.
3. LangGraph `astream_events(version="v2")` event names and payload shapes must be mapped carefully to new message-first SSE events.
4. `retry_with_browser_use_agent` env requirements must be verified to avoid silent fallback failures.
5. LangChain `create_agent` import compatibility must handle regression fallback if package version drifts.
6. Client refresh/reconnect continuation is de-scoped for this phase; stream continuity on reconnect is a later feature.

## Milestones
1. M2.1 Scaffold LangGraph + MCP Core
2. M2.2 Message-First Streaming State (broadcast+buffer)
3. M2.3 Stream Adapter and Frontend Contract Update
4. M2.4 Reliability and Parity Checks (cancel/refresh/persistence)
5. M2.5 Final Validation and Documentation
6. M2.6 Message Persistence + Screenshot Storage

## Task Breakdown
1. Add LangGraph/MCP dependencies and version-safe imports.
2. Implement provider-agnostic model init via `init_chat_model` and env vars:
   - `AGENT_MODEL`
   - `SUMMARY_MODEL`
3. Implement MCP client bootstrap for browser-use official MCP (`uvx --from 'browser-use[cli]' browser-use --mcp`).
4. Discover and log MCP tools at runtime; persist confirmed tool list in plan notes.
5. Build new agent factory (`create_agent`) with minimal safe middleware (call limits first; optional extras only if stable).
6. Implement per-session in-memory current-message state:
   - `assistant_text_so_far`
   - `current_tool_status` (`idle|running`, name, args preview)
   - transient stream events only for live UI
7. Stop persisting intermediate stream events; persist message completions:
   - completed assistant message text when model response completes
   - completed tool message when each tool call completes
   - terminal failure state on `error` (without partial assistant message persistence)
8. Implement streaming event adapter from `agent.astream_events(..., version="v2")` to SSE events:
   - `token`
   - `thinking` (when available from model/provider)
   - `tool_start`
   - `tool_end` (include screenshot/url when available)
   - `done`
   - `error`
9. Wire migrated runner into `/api/sessions/{id}/messages` and `/stream` lifecycle (single live stream per active request; no reconnect replay guarantee).
10. Ensure cancel path still emits terminal `error` with `Task cancelled`.
11. Verify restore path (`/sessions/{id}`) renders persisted message history including completed tool messages.
12. Keep smoke script prompt as ping roundtrip check:
    - `this is a ping test: do not think, respond as quickly as possible with any noun`
13. Validate one realistic web task to confirm token streaming, tool status updates, and final response quality.
14. Update `README.md` and this plan with migration decisions, known limitations, and runbook steps.
15. Add message schema migration for tool messages + screenshot refs:
   - `Message.role` constrained to `user|assistant|tool`
   - `Message.meta_json` nullable (tool name, tool call id, arguments summary, URL, screenshot path, status)
16. Add screenshot storage path config and serve files:
   - `SCREENSHOT_DIR` (volume-backed)
   - API/static route for screenshot retrieval
17. Anthropic tool schema compatibility patch:
   - Strip top-level union keywords (`oneOf`/`anyOf`/`allOf`) for affected tools when provider is Anthropic
   - Add pre-call validator for `browser_click` arg shape (`index` xor `coordinate_x+coordinate_y`)

## Verification Matrix
1. Fast ping roundtrip:
   - Command: `AUTH_TOKEN=... BASE_URL=http://127.0.0.1:8000/api ./scripts/curl_e2e.sh`
   - Expect: non-empty terminal `done` assistant text.
2. Live message streaming:
   - Expect: token-level assistant text arrives incrementally before terminal event.
3. Tool activity streaming:
   - Expect: `tool_start`/`tool_end` reflect active tool status and include context when available.
4. Cancel parity:
   - Trigger delete mid-run.
   - Expect: terminal `error` with `Task cancelled` persisted.
5. Refresh behavior (de-scoped):
   - Reload mid-run and after done.
   - Expect: after refresh, feed reconstructs from persisted completed messages only; no guarantee of in-progress stream continuation.
6. Real task sanity:
   - Expect: final assistant response is user-meaningful and not fallback text in normal runs.
7. Persistence policy:
   - Expect: no intermediate streaming events persisted to DB; only completed user/assistant/tool messages + terminal status updates.
8. Tool schema compatibility:
   - Expect: Anthropic runs include click capability via schema patch + runtime arg validator.

## File Targets
- `server/agent_runner.py` (primary migration surface)
- `server/main.py` (only if runtime/session orchestration needs minor glue updates)
- `server/runtime.py` (if event model extensions needed)
- `server/models.py`
- `server/migrations/*` (new migration for message metadata)
- `requirements.txt`
- `scripts/curl_e2e.sh`
- `README.md`

## Preserved Decisions
1. Keep `AGENT_MODE=mock|real`; `real` for product validation, `mock` for fast plumbing tests.
2. Schema ownership remains Alembic; runtime performs DB readiness check only.
3. Keep current simple password gate in this phase.
4. Message-centric model is primary.
5. Tool execution is persisted as completed `tool` messages (not as free-form step events).
6. Screenshot binary data is not stored in DB; only path/URL refs are persisted.

## Status
- M2.1 Scaffold LangGraph + MCP Core: Completed
- M2.2 Message-First Streaming State (broadcast+buffer): Completed
- M2.3 Stream Adapter and Frontend Contract Update: Completed
- M2.4 Reliability and Parity Checks: Completed
- M2.5 Final Validation and Documentation: Completed
- M2.6 Message Persistence + Screenshot Storage: Completed

## Implementation Notes (2026-02-27)
1. Migrated runner to LangGraph `create_agent` + browser-use MCP via `MultiServerMCPClient` session + `load_mcp_tools(...)`.
2. Implemented message-first streaming with per-session in-memory broadcast buffer for only the current in-progress assistant response.
3. Removed intermediate DB event persistence; `/sessions/{id}/events` now intentionally returns an empty list.
4. SSE event contract now emits: `token`, `thinking`, `tool_start`, `tool_end`, `done`, `error`.
5. Refresh reconnect support was de-scoped for this phase. Persisted history is the source of truth after refresh.
6. Env vars updated to `AGENT_MODEL` + `SUMMARY_MODEL`; defaults set to Haiku.
7. Anthropic compatibility issue found and addressed:
   - browser-use MCP `browser_click` tool schema includes top-level `oneOf`.
   - Anthropic tool schema validation rejects this.
   - Updated approach: provider-specific schema patch + click arg validator (instead of dropping the tool).
8. Added message metadata migration (`20260227_0002`) for tool-message persistence:
   - `message.meta_json`
9. Tool completions now persist as `role=\"tool\"` messages with structured metadata summaries.
10. Screenshot storage path and static route wiring added:
   - `SCREENSHOT_DIR`
   - `SCREENSHOT_URL_PREFIX`
   - static mount at `/api/files/screenshots`
11. Schema simplification decision:
   - Removed dedicated `tool_name` and `tool_call_id` columns.
   - Keep tool metadata entirely in `message.meta_json` to reduce schema surface.
12. Follow-up migration added (`20260227_0003`) to drop `tool_name`/`tool_call_id` and keep meta-only tool payloads.
13. Verified `browser_click` flow under Anthropic with schema patch + validator; tool completion persisted with `tool_name` and `tool_call_id` inside `meta_json`.
14. Final validation pass complete:
   - ping e2e streamed `token` + `done` and persisted assistant message.
   - real browser tasks persisted `tool` messages with `meta_json` payloads.
   - screenshot persistence verified: file path saved in `meta_json`, file served via `/api/files/screenshots/...` (HTTP 200).
15. Documentation updates complete for env vars and tool-message persistence behavior.
