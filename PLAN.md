# PLAN

## Issues
- Password screen shows 'password incorrect' message as initial state. should not show this unless incorrect password attempted.
- Chat screen - after sending initial message, response immediately comes back showing 'None'. This is wrong.

## Status Update (2026-02-26)
- Milestone 0: Completed.
- Milestone 1: Completed.
- Milestone 2: Completed.
- Milestone 3: Completed.
- Milestone 4: In progress.

Milestone 0 execution evidence:
- Script added: `server/scripts/m0_browser_use_smoke.py`
- Executed command: `python server/scripts/m0_browser_use_smoke.py`
- Result: success (agent navigated to `https://example.com`, step callback fired with screenshot metadata, terminal done result returned).

Milestone 1 execution evidence (backend API + DB wiring):
- Backend implemented in `server/`:
  - `server/main.py`
  - `server/database.py`
  - `server/models.py`
  - `server/runtime.py`
  - `server/agent_runner.py`
- Entrypoint wired: `app/main.py` now imports `server.main:app`.
- Verification run (mock agent mode for deterministic speed; SQLite only):
  - Server run: `DATABASE_URL=sqlite+aiosqlite:////workspace/dev.db AGENT_MODE=mock uvicorn server.main:app --port 8010`
  - API e2e script: `BASE_URL=http://127.0.0.1:8010/api ./scripts/curl_e2e.sh`
  - Verified endpoints: create session, get session, post message, stream SSE events, list events, delete/cancel.
  - Persistence confirmed via `/api/sessions/{id}/events` terminal records.
- Postgres verification (in app container via compose network `db`):
  - Connectivity check: `asyncpg` connected to `postgresql://postgres:postgres@db:5432/app` and `select 1` returned.
  - Server run: `DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/app AGENT_MODE=mock uvicorn server.main:app --port 8011`
  - API e2e script: `BASE_URL=http://127.0.0.1:8011/api ./scripts/curl_e2e.sh`
  - Verified endpoints: create session, post message, stream SSE events, list events (persisted in Postgres).

Project decisions (2026-02-26):
- Agent mode: real agent wired; default dev model `haiku-4-5`, switchable to `sonnet-4-6` via env.
- Frontend: clean, good-looking, not flashy.
- Single app service runs both backend + frontend dev servers.
- Migrations: required for final (dev can be loose but final must include a valid migration).
- Tests: minimal, only as needed for velocity.
- Auth: barebones single-field login; password read from `.env`.

Milestone 2 execution evidence (frontend + auth gate):
- Frontend scaffolded in `web/` with Vite + React + Tailwind.
- Core UI implemented: `web/src/App.tsx`, `web/src/components/*`, `web/src/types.ts`.
- SSE stream wiring uses `/api/sessions/{id}/stream?auth=...` and renders step + done/error events.
- Auth gate: `APP_PASSWORD` enforced via `server/auth.py` + `/api/auth/check` and login form in UI.
- Dev start script added: `start.sh` runs Vite + uvicorn; compose updated to expose `5173`.

Milestone 3 execution evidence (UX/reliability polish):
- Auto-scroll to latest message and reconnect-to-stream on refresh if session status is `running`.
- Error banners and streaming disconnect handling in UI.
- Cancel button wired to `DELETE /api/sessions/{id}`.
- Screenshot modal implemented.

Milestone 4 status:
- Docs updated with auth, ports, migrations, and run commands.
- Docker Compose updated for single app service (backend + frontend).
- Runtime verification:
- `AUTH_TOKEN=... BASE_URL=http://127.0.0.1:8000/api ./scripts/curl_e2e.sh` now authenticates and streams events.
- Real-agent smoke produced a `step` event; run was manually cancelled and emitted terminal `error` with `"Task cancelled"`.
- Frontend blank page root cause fixed: TypeScript `verbatimModuleSyntax` import errors in `web/src/App.tsx` and component type imports.
- Remaining: full real-agent done-path smoke (without manual cancellation) and final runbook confirmation.

## Goal
Build a production-demo-ready "Better Perplexity" app: a chat interface that runs a browser-use agent via Claude, streams step-by-step browser actions/screenshots in real time over SSE, persists sessions/messages/events in Postgres, and runs end-to-end in Docker Compose.

## Architecture Overview
- Frontend: React + TypeScript + Vite + Tailwind in `web/`, with session restore and live agent stream rendering.
- Backend: FastAPI in `server/` under `/api`, with async endpoints, runtime task/session management, SSE stream endpoint, and agent runner integration.
- Agent runtime: `browser-use` + `ChatAnthropic`, step callbacks mapped to structured events and persisted.
- Data: PostgreSQL 16 with SQLModel + asyncpg for `Session`, `Message`, and `AgentEventRecord`.
- Infra: Docker Compose with `app` + `db` services; single app container runs backend and frontend dev servers.

## Milestones
1. Milestone 0: Validate browser-use + Claude execution in container (bare-bones smoke run).
2. Milestone 1: Backend API + DB + runtime wiring complete and curl-verified.
3. Milestone 2: Frontend chat + SSE UI wired to backend with event rendering.
4. Milestone 3: UX/reliability polish (errors, cancel, reconnect-safe restore, responsive UI).
5. Milestone 4: Dockerized end-to-end runbook and deployment readiness checks.

## Task Breakdown (Ordered)
1. Scaffold repository into `server/` and `web/` target structure. (partially complete: `server/` done, `web/` pending)
2. Implement DB layer (engine/session/init) and SQLModel entities/schemas. (complete)
3. Implement backend API skeleton with `/api` routes and startup lifecycle. (complete)
4. Implement in-memory session runtime manager (`active_sessions`, queue, task tracking). (complete)
5. Implement agent runner with step callback, screenshot extraction, and DB persistence hooks. (complete for Milestone 1; includes `AGENT_MODE=mock|real`)
6. Implement SSE streaming endpoint and event serialization contract. (complete)
7. Implement cancel flow and status transitions (`idle`, `running`, `error`) across happy/error/cancel paths. (complete)
8. Verify backend flow with curl script: create session -> post message -> stream events -> inspect persistence. (complete)
9. Scaffold frontend app (Vite + TS + Tailwind) and API proxy.
10. Build chat components and normalized feed rendering (user + step + final/error).
11. Build `useAgentStream` hook and wire stream lifecycle to send-message flow.
12. Implement refresh restoration (load session/messages/past events).
13. Add screenshot thumbnail + expand modal behavior.
14. Add UX polish: loading indicators, auto-scroll, responsive layout, error banners.
15. Finalize Docker Compose, start script, env docs, and deployment runbook checks.

## Files To Create Per Task
1. Structure alignment
- `server/`
- `web/`
- `start.sh`

2. DB layer and models
- `server/database.py`
- `server/models.py`

3. Backend API skeleton
- `server/main.py`

4. Runtime manager
- `server/runtime.py`

5. Agent runner
- `server/agent_runner.py`

6. SSE/event contract helpers
- `server/events.py`

7. Backend tests and integration helpers
- `server/tests/test_api_sessions.py`
- `server/tests/test_sse_stream.py`
- `scripts/curl_e2e.sh`

8. Frontend scaffold
- `web/package.json`
- `web/vite.config.ts`
- `web/tailwind.config.js`
- `web/src/main.tsx`
- `web/src/App.tsx`

9. Frontend types/hook/components
- `web/src/types.ts`
- `web/src/hooks/useAgentStream.ts`
- `web/src/components/ChatInput.tsx`
- `web/src/components/MessageFeed.tsx`
- `web/src/components/UserMessage.tsx`
- `web/src/components/AgentStep.tsx`
- `web/src/components/AgentMessage.tsx`
- `web/src/components/StatusIndicator.tsx`
- `web/src/components/ScreenshotModal.tsx`

10. Infra/docs
- `docker-compose.yml` (update)
- `Dockerfile` (update)
- `.env.example` (update)
- `README.md` (update with run/deploy/test flow)

## Test Strategy
- Prioritize fastest confidence path first: backend unit/integration + one e2e smoke script.
- Unit tests (backend):
  - Model and schema validation.
  - Session lifecycle/status transition logic.
  - Event serialization shape and timestamp presence.
- Integration tests (backend):
  - `/api/sessions` create/get lifecycle.
  - `/api/sessions/{id}/messages` persists user message and starts task.
  - `/api/sessions/{id}/stream` emits `step` then terminal `done|error`.
  - `/api/sessions/{id}/events` returns persisted history after stream.
  - `DELETE /api/sessions/{id}` cancels active run and records terminal cancellation error event.
- End-to-end smoke test:
  - Docker Compose up.
  - Real prompt execution produces visible step cards and final response.
  - Refresh preserves history.
- Frontend tests are optional in first pass; add only if velocity remains high after core backend/e2e is green.

## Definition of Done
- All required `/api` endpoints from SPEC are implemented and functioning.
- Agent runs via browser-use + Claude and streams real-time step events with screenshots.
- Session/messages/events persist in Postgres and reload correctly after refresh.
- Frontend supports send, live progress, terminal result/error, and cancel action.
- Cancellation contract: terminal event uses `type: "error"` with `data.error: "Task cancelled"`.
- Docker Compose launches app and db cleanly with documented setup.
- Automated backend critical-path tests pass locally; smoke e2e script passes.
- README documents setup, env vars, run commands, and deployment procedure.
