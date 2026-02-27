# Tenex Takehome

FastAPI + browser-use app with Postgres and Redis, set up for development inside a devcontainer with Claude Code and Codex.

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
# codex yolo in workspace, only run in dev container
codex --yolo resume
```

## Running

### Option A: Devcontainer (recommended)

Makes Claude Code available inside the container alongside the app.

1. Set your API keys in your local environment (the devcontainer forwards them in):
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   export OPENAI_API_KEY=sk-...
   ```
2. Open the project in VS Code and select **Reopen in Container** when prompted (or run `Dev Containers: Reopen in Container` from the command palette).
3. VS Code will build the image and start all services. Once inside, both `claude` and `codex` are available in the terminal.

### Option B: Docker Compose only

```bash
docker compose up --build
```

## Services

| Service  | Local port | Description          |
|----------|------------|----------------------|
| app      | 8000       | FastAPI + browser-use |
| app      | 5173       | Vite frontend         |
| db       | 5432       | PostgreSQL 16        |
| redis    | 6379       | Redis 7              |

- UI: http://localhost:5173
- API: http://localhost:8000/api
- Docs: http://localhost:8000/docs

## Connections (from inside the app container)

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/app
REDIS_URL=redis://redis:6379/0
```

These are set automatically via `docker-compose.yml`. Update `.env` only for secrets and overrides.

## Auth Gate

Set `APP_PASSWORD` in `.env`. The UI will prompt for a single password and sends it to the API via `x-auth` header (or query param for SSE).

## Agent Config

- `AGENT_MODEL`: default `anthropic:claude-haiku-4-5-20251001`
- `SUMMARY_MODEL`: default `anthropic:claude-haiku-4-5-20251001` (reserved for summarization middleware wiring)
- `AGENT_MODE`: `real` or `mock`
- `HEADLESS`: `true`/`false`
- `BROWSER_MCP_COMMAND`: default `browser-use`
- `BROWSER_MCP_ARGS`: default `--mcp`
- `SCREENSHOT_DIR`: default `/workspace/data/screenshots`
- `SCREENSHOT_URL_PREFIX`: default `/api/files/screenshots`

Tool outputs are persisted as `tool` messages. Screenshot blobs are written to disk and tool messages store screenshot URL references.
Tool metadata (including `tool_name` and `tool_call_id`) is stored in `message.meta_json`.

## Migrations

Initial Alembic migration is included. For production, run:

```bash
alembic upgrade head
```
