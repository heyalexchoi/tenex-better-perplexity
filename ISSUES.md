# Issues

- [x] 1. Backend error visibility: capture and log full runtime exceptions (including ExceptionGroup/TaskGroup failures) so they show in container logs.
  - Status: Done
  - Notes: Added `logger.exception(...)` in `server/agent_runner.py` exception path.

- [x] 2. Remove low-value session info bubble from UI.
  - Status: Done
  - Notes: Removed session stats sidebar from `web/src/App.tsx`.

- [x] 3. Chat layout: make composer stick to bottom, always visible; message feed scrolls independently.
  - Status: Done
  - Notes: Updated layout in `web/src/App.tsx` to full-height flex with scrollable feed and sticky composer footer.

- [x] 4. Composer behavior: Enter sends, Shift+Enter inserts newline.
  - Status: Done
  - Notes: Added key handling in `web/src/components/ChatInput.tsx`.

- [x] 5. Screenshot rendering: display persisted tool screenshots correctly in UI.
  - Status: Done
  - Notes: Screenshot resolver now supports URL paths (`/api/files/screenshots/...`) in `web/src/components/AgentMessage.tsx`.

- [x] 6. Tool stream UX: do not keep separate tool-start item after tool completes; replace with completed tool state.
  - Status: Done
  - Notes: `tool_start` events no longer render as feed items; `tool_end` renders completion line.

- [x] 7. Turn rendering: collapse tool calls/messages within a turn into a single assistant bubble with secondary (gray) styling and no "step" labels.
  - Status: Done
  - Notes: Reworked feed construction in `web/src/App.tsx`; assistant bubble now carries grouped tool lines and optional screenshots.
