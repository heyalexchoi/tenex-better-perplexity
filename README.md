# Tenex Takehome

FastAPI + browser-use app with Postgres, set up for development inside a devcontainer with Claude Code and Codex.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [VS Code](https://code.visualstudio.com/) + [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) (if using devcontainer)
- An Anthropic API key (for Claude Code)
- An OpenAI API key (for Codex)


## Setup

```bash
cp .env.example .env
# Add your ANTHROPIC_API_KEY + APP_PASSWORD to .env
```

## Dev
```
# codex / claude yolo in workspace, only run in dev container
codex --yolo resume
claude --dangerously-skip-permissions --resume
```

## Running
```bash
docker compose build
docker compose up -d
```

## Services

| Service  | Local port | Description          |
|----------|------------|----------------------|
| app      | 8000       | FastAPI + browser-use |
| app      | 5173       | Vite frontend         |
| db       | 5432       | PostgreSQL 16        |

- UI: http://localhost:5173
- API: http://localhost:8000/api
- Docs: http://localhost:8000/docs

## Connections (from inside the app container)

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/app
```

Set automatically via `docker-compose.yml`. Update `.env` only for secrets and overrides.

## Auth Gate

Set `APP_PASSWORD` in `.env`. The UI will prompt for a single password and sends it to the API via `x-auth` header (or query param for SSE).

## Agent Config

- `AGENT_MODEL`: default `anthropic:claude-haiku-4-5-20251001`
- `BROWSER_AGENT_MODEL`: default `claude-haiku-4-5-20251001` (direct `browser_use.Agent` model)
- `AGENT_MODE`: `real` or `mock`
- `HEADLESS`: `true`/`false`
- `BROWSER_MAX_STEPS`: default `18`
- `MAX_HISTORY_TOKENS`: default `12000` (approximate token budget for replayed chat history)
- `SCREENSHOT_DIR`: default `/workspace/data/screenshots`
- `SCREENSHOT_URL_PREFIX`: default `/api/files/screenshots`

Runtime architecture:
- The backend delegates browsing tasks to direct `browser_use.Agent` execution.
- Step progress streams to the UI as transient events.
- The final user-facing assistant message is generated separately from a compact browser summary to keep model context bounded.

Tool outputs are persisted as `tool` messages. Screenshot blobs are written to disk and tool messages store screenshot URL references.
Tool metadata (including `tool_name` and `tool_call_id`) is stored in `message.meta_json`.

## Migrations

On new db, run:

```bash
docker compose exec app alembic upgrade head       
```
