# Better Perplexity — Agent Browser

## Project Spec for Coding Agent

### What This Is

A take-home assignment for Tenex (AI dev agency). The prompt: build a "Better Perplexity" — a chat agent with internet search capabilities, then take it one step further with a technically compelling feature.

**Our angle:** Perplexity answers questions. This agent *does things*. It has a browser and can navigate, interact, extract, and complete tasks on the web — not just search and summarize. This is the trajectory of search: from retrieval to action.

### Core Feature

A chat interface where users type natural language requests and a browser-use agent powered by Claude executes them in a real browser. The user sees the agent's reasoning, actions, and browser screenshots streamed in real-time.

**Example tasks:**
- "Compare the pricing tiers of Vercel vs Netlify vs Cloudflare Pages for 100k monthly visitors"
- "What's the best-reviewed ramen spot near me that's open right now?"
- "Read the top HN thread right now and summarize the actual consensus"
- "Find me 1BR apartments in Bushwick under $2500 on StreetEasy"

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                  React Frontend (Vite)               │
│                                                      │
│  ┌───────────┐  ┌────────────────────────────────┐   │
│  │ Chat      │  │ Message Feed                   │   │
│  │ Input     │  │  - User messages               │   │
│  │           │  │  - Agent thinking/reasoning     │   │
│  │           │  │  - Agent actions (tool calls)   │   │
│  │           │  │  - Browser screenshots          │   │
│  │           │  │  - Final results                │   │
│  └───────────┘  └────────────────────────────────┘   │
└──────────┬──────────────┬────────────────────────────┘
           │              │
      POST /api/sessions  GET /api/sessions/{id}/stream (SSE)
      /{id}/messages      
           │              │
┌──────────▼──────────────▼────────────────────────────┐
│              Docker Compose                           │
│                                                       │
│  ┌─────────────────────────────────────────────────┐  │
│  │ app container                                   │  │
│  │                                                 │  │
│  │  FastAPI Backend (uvicorn)                      │  │
│  │    All endpoints under /api                     │  │
│  │                                                 │  │
│  │  Agent Runner (asyncio.create_task)             │  │
│  │    browser-use Agent + lifecycle hooks           │  │
│  │    Hooks → asyncio.Queue → SSE stream           │  │
│  │                                                 │  │
│  │  browser-use BrowserSession (Chromium)          │  │
│  │  Vite Dev Server (frontend)                     │  │
│  └──────────────────┬──────────────────────────────┘  │
│                     │                                  │
│  ┌──────────────────▼──────────────────────────────┐  │
│  │ db container (postgres:16-alpine)               │  │
│  │   SQLModel ORM + asyncpg                        │  │
│  └─────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## Tech Stack

| Layer | Choice | Notes |
|-------|--------|-------|
| Frontend | React + TypeScript + Vite | Latest stable |
| Styling | Tailwind CSS | v3 or v4 |
| Backend | FastAPI + uvicorn | Python 3.11+ |
| ORM | SQLModel + asyncpg | By FastAPI author, combines Pydantic + SQLAlchemy |
| Database | PostgreSQL 16 | postgres:16-alpine in compose |
| Agent | browser-use | Latest (0.10.x+) |
| LLM | Claude via `ChatAnthropic` | Haiku for dev, Sonnet for demo |
| Browser | browser-use BrowserSession | Manages Chromium in same container |
| Deployment | Docker Compose on DigitalOcean droplet | Two services: app + db |

---

## Backend Detail

### Database Models (SQLModel)

SQLModel is by the same author as FastAPI. Models double as both SQLAlchemy table definitions and Pydantic schemas — no duplication. Use asyncpg as the async Postgres driver.

```python
from sqlmodel import SQLModel, Field
from datetime import datetime
from uuid import uuid4
from typing import Optional

# --- Table models ---

class Session(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    status: str = Field(default="idle")  # idle | running | error

class Message(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    role: str  # "user" | "assistant"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class AgentEventRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    type: str  # "step" | "done" | "error"
    data: str  # JSON string
    timestamp: datetime = Field(default_factory=datetime.utcnow)

# --- Request/response schemas (data-only models, no table=True) ---

class MessageCreate(SQLModel):
    content: str

class SessionResponse(SQLModel):
    id: str
    created_at: datetime
    status: str
    messages: list[Message] = []
```

### Database Setup

```python
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/app")

engine = create_async_engine(DATABASE_URL)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

async def get_session():
    async with async_session() as session:
        yield session
```

### Endpoints

All endpoints prefixed with `/api` so Vite can proxy cleanly.

```python
# POST /api/sessions
# Creates a new Session row in Postgres
# Returns: SessionResponse

# GET /api/sessions/{session_id}
# Returns session + message history + past agent events
# (for page refresh / reload)

# POST /api/sessions/{session_id}/messages
# Body: MessageCreate { content: str }
# Saves user message to DB
# Creates SessionRuntime if not exists
# Kicks off agent as asyncio.create_task()
# Returns: Message immediately

# GET /api/sessions/{session_id}/stream
# SSE endpoint. Client opens EventSource, receives events for current agent run.
# Events also saved to DB as they arrive.
# Stream stays open until "done" or "error" event.

# GET /api/sessions/{session_id}/events
# Returns past agent events from DB (for page refresh)

# DELETE /api/sessions/{session_id}
# Cancels running agent task via task.cancel()
```

### In-Memory Runtime State (not persisted)

```python
from dataclasses import dataclass, field
from asyncio import Queue, Task

@dataclass
class AgentEvent:
    """Events streamed to frontend via SSE"""
    type: str  # "step" | "done" | "error"
    data: dict
    timestamp: str

@dataclass
class SessionRuntime:
    """In-memory state for active agent runs. NOT persisted."""
    session_id: str
    events_queue: Queue = field(default_factory=Queue)
    current_task: Task | None = None

active_sessions: dict[str, SessionRuntime] = {}
```

### Agent Runner

```python
from browser_use import Agent, BrowserSession, ChatAnthropic
import os

# Browser session — one per server process, manages Chromium
browser_session = BrowserSession(
    headless=bool(os.getenv("HEADLESS", "true").lower() == "true"),
    user_data_dir=os.getenv("CHROME_PROFILE_PATH", None),
)

# Model config — swap between haiku (dev) and sonnet (demo)
MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")

async def run_agent_task(runtime: SessionRuntime, user_message: str, db_session):
    """
    Runs browser-use agent for a user message.
    Pushes events to runtime.events_queue AND persists to Postgres.
    Called via asyncio.create_task() from the message endpoint.
    """
    llm = ChatAnthropic(model=MODEL)

    agent = Agent(
        task=user_message,
        llm=llm,
        browser_session=browser_session,
    )

    # Hook: fires after each agent step
    async def on_step(agent_instance):
        step_num = agent_instance.state.n_steps
        actions = agent_instance.history.model_actions()
        last_action = str(actions[-1]) if actions else "thinking..."
        current_url = await agent_instance.browser_session.get_current_page_url()

        # Get screenshot
        screenshot_b64 = None
        state = await agent_instance.browser_session.get_browser_state_summary()
        if state.screenshot:
            screenshot_b64 = state.screenshot

        event = AgentEvent(
            type="step",
            data={
                "step": step_num,
                "action": last_action,
                "url": current_url,
                "screenshot": screenshot_b64,
            },
            timestamp=datetime.utcnow().isoformat()
        )
        await runtime.events_queue.put(event)
        await persist_event(runtime.session_id, event)

    agent.register_new_step_callback(on_step)

    try:
        await update_session_status(runtime.session_id, "running")
        result = await agent.run()

        done_event = AgentEvent(
            type="done",
            data={"result": str(result)},
            timestamp=datetime.utcnow().isoformat()
        )
        await runtime.events_queue.put(done_event)
        await persist_event(runtime.session_id, done_event)
        await persist_message(runtime.session_id, "assistant", str(result))
        await update_session_status(runtime.session_id, "idle")

    except asyncio.CancelledError:
        err_event = AgentEvent(
            type="error",
            data={"error": "Task cancelled"},
            timestamp=datetime.utcnow().isoformat()
        )
        await runtime.events_queue.put(err_event)
        await persist_event(runtime.session_id, err_event)
        await update_session_status(runtime.session_id, "idle")

    except Exception as e:
        err_event = AgentEvent(
            type="error",
            data={"error": str(e)},
            timestamp=datetime.utcnow().isoformat()
        )
        await runtime.events_queue.put(err_event)
        await persist_event(runtime.session_id, err_event)
        await update_session_status(runtime.session_id, "error")
```

### SSE Streaming Endpoint

```python
from fastapi.responses import StreamingResponse

@app.get("/api/sessions/{session_id}/stream")
async def stream_session(session_id: str):
    runtime = active_sessions.get(session_id)
    if not runtime:
        raise HTTPException(status_code=404, detail="No active agent run")

    async def event_generator():
        while True:
            event = await runtime.events_queue.get()
            yield f"data: {json.dumps(asdict(event))}\n\n"
            if event.type in ("done", "error"):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )
```

### CORS

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### App Startup

```python
@app.on_event("startup")
async def on_startup():
    await init_db()  # creates tables if they don't exist
```

---

## Frontend Detail

### Component Structure

```
src/
  App.tsx              — Main layout, session management
  components/
    ChatInput.tsx      — Text input + submit, disabled while agent running
    MessageFeed.tsx    — Scrollable feed of all messages and agent events
    UserMessage.tsx    — Simple chat bubble for user messages
    AgentMessage.tsx   — Card showing agent's final response
    AgentStep.tsx      — Compact card showing one agent action (collapsible)
                         Shows: step number, action description, current URL
                         Expandable: shows screenshot if available
    StatusIndicator.tsx — "Agent is working..." with pulse animation
  hooks/
    useAgentStream.ts  — EventSource hook for SSE
  types.ts             — Shared TypeScript types
  main.tsx
```

### Key Frontend Behavior

1. **On load:** If session exists, fetch message history + past events from `/api/sessions/{id}` to reconstruct the feed (handles page refresh).

2. **User sends message** → POST to `/api/sessions/{id}/messages` → immediately open EventSource on `/api/sessions/{id}/stream`

3. **As SSE events arrive:**
   - `type: "step"` → append AgentStep card to feed (action description + optional screenshot)
   - `type: "done"` → append AgentMessage with final result, close EventSource, re-enable input
   - `type: "error"` → show error, close EventSource, re-enable input

4. **UI aesthetic:** Clean, dark mode, Claude-like chat interface. Agent step cards are compact and expandable. Screenshots are thumbnails that expand on click.

### SSE Client Hook

```typescript
// hooks/useAgentStream.ts
import { useState, useCallback } from 'react';

interface AgentEvent {
  type: 'step' | 'done' | 'error';
  data: Record<string, any>;
  timestamp: string;
}

export function useAgentStream(sessionId: string | null) {
  const [events, setEvents] = useState<AgentEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);

  const startStream = useCallback(() => {
    if (!sessionId) return;
    setIsStreaming(true);
    setEvents([]);

    const source = new EventSource(`/api/sessions/${sessionId}/stream`);

    source.onmessage = (e) => {
      const event: AgentEvent = JSON.parse(e.data);
      setEvents(prev => [...prev, event]);

      if (event.type === 'done' || event.type === 'error') {
        source.close();
        setIsStreaming(false);
      }
    };

    source.onerror = () => {
      source.close();
      setIsStreaming(false);
    };
  }, [sessionId]);

  return { events, isStreaming, startStream };
}
```

### Styling Direction

- Dark mode by default, clean minimal aesthetic
- Similar feel to Claude/ChatGPT chat interfaces
- Agent step cards: compact one-liner (step # + action + URL), click to expand
- Screenshots: small thumbnails (~300px wide), click to expand full size in modal/overlay
- Tailwind utility classes throughout
- Auto-scroll to bottom as new events arrive
- Pulse animation while agent is working

---

## Environment Variables

```env
# Backend
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-haiku-4-5-20251001    # use claude-sonnet-4-0 for demo
HEADLESS=true                              # false to watch browser locally
CHROME_PROFILE_PATH=                       # Chrome user data dir (local only)
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/app
```

---

## Docker Compose Setup

### docker-compose.yml

```yaml
services:
  app:
    build: .
    ports:
      - "5173:5173"   # Vite frontend
      - "8000:8000"   # FastAPI backend
    env_file:
      - .env
    volumes:
      # Live code reload for AI coding agents
      - ./backend:/app/backend
      - ./frontend:/app/frontend
    depends_on:
      db:
        condition: service_healthy
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/app
      - HEADLESS=true

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

### Dockerfile

```dockerfile
FROM browseruse/browseruse:latest

WORKDIR /app

# Install Node.js for Vite frontend
RUN apt-get update && apt-get install -y curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Backend deps
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Frontend deps
COPY frontend/package*.json frontend/
RUN cd frontend && npm install

# Copy source
COPY backend/ backend/
COPY frontend/ frontend/

# Start script
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 5173 8000
CMD ["./start.sh"]
```

### start.sh

```bash
#!/bin/bash
set -e

# Start backend
cd /app/backend
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &

# Start frontend
cd /app/frontend
npx vite --host 0.0.0.0 --port 5173 &

# Wait for either to exit
wait -n
exit $?
```

### Vite Config

```typescript
// frontend/vite.config.ts
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
```

### Development Workflow

```bash
# Start everything
docker compose up --build

# App at http://localhost:5173
# Backend at http://localhost:8000
# Postgres at localhost:5432

# AI coding agents (Codex/Claude Code) edit files on host
# Volume mounts + --reload mean changes picked up live

# Rebuild after dependency changes
docker compose up --build
```

### Deploy to DigitalOcean Droplet

```bash
# On droplet:
git clone <repo-url> && cd better-perplexity

# Create .env
cat > .env << EOF
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-0
HEADLESS=true
EOF

# Run
docker compose up -d --build

# App at http://<droplet-ip>:5173
```

---

## Project File Structure

```
better-perplexity/
├── backend/
│   ├── main.py              # FastAPI app, endpoints, CORS, startup
│   ├── models.py            # SQLModel table + schema models
│   ├── database.py          # Engine, async session factory, init_db
│   ├── agent_runner.py      # browser-use agent setup + hooks
│   └── requirements.txt     # fastapi, uvicorn, sqlmodel, asyncpg, browser-use, langchain-anthropic
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ChatInput.tsx
│   │   │   ├── MessageFeed.tsx
│   │   │   ├── UserMessage.tsx
│   │   │   ├── AgentMessage.tsx
│   │   │   ├── AgentStep.tsx
│   │   │   └── StatusIndicator.tsx
│   │   ├── hooks/
│   │   │   └── useAgentStream.ts
│   │   ├── types.ts
│   │   └── main.tsx
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
├── docker-compose.yml
├── Dockerfile
├── start.sh
├── .env                     # not committed
├── .gitignore
└── README.md
```

---

## Implementation Order (for coding agent)

### Phase 0: Bare-bones agent test (DO THIS FIRST)
1. Minimal Python script — just run browser-use Agent with ChatAnthropic (Haiku) on a simple task like "go to google.com and search for weather"
2. Verify it works inside the Docker container
3. Confirm hooks fire and you can capture step data (print to console)
4. This validates the core dependency before building anything on top

### Phase 1: Backend skeleton
1. Set up FastAPI app with CORS, `/api` prefix
2. Database setup: SQLModel models, async engine with asyncpg, init_db on startup
3. Session CRUD endpoints (create, get with history)
4. Message endpoint that saves to DB and spawns agent via asyncio.create_task()
5. SSE streaming endpoint with asyncio.Queue
6. Wire agent hooks to push events to queue AND persist to DB
7. **Test with curl:** create session → send message → read SSE stream → verify events arrive and DB has data

### Phase 2: Frontend
1. Scaffold React + Vite + TypeScript + Tailwind
2. Set up Vite proxy to backend
3. Build ChatInput component
4. Build useAgentStream hook with EventSource
5. Build MessageFeed with UserMessage, AgentStep, AgentMessage components
6. Wire up: input → POST → open SSE → render events
7. On page load: fetch existing session history from API
8. Screenshot thumbnails with expand on click
9. Style: dark mode, clean, Claude-like

### Phase 3: Polish
1. Error handling (agent failures, SSE disconnects)
2. Loading/status indicators with pulse animation
3. Auto-scroll to bottom on new events
4. Cancel button wired to DELETE endpoint
5. Basic responsive design

### Phase 4: Deploy
1. Provision DO droplet ($12/mo, Ubuntu)
2. Install Docker + Docker Compose
3. Clone repo, create .env with Sonnet model
4. `docker compose up -d --build`
5. Verify from external browser

---

## Key Technical Decisions to Communicate in Video

1. **"Why a browser agent instead of just search?"** — "Perplexity was built for the retrieval era. The trajectory of search is toward agents that act, not just retrieve. This agent navigates, interacts, extracts — that's the next generation. Perplexity themselves validate this with Comet."

2. **"Why cooperative async instead of a worker queue?"** — "For this demo, asyncio.create_task in a single process is the right tradeoff. In production I'd isolate the agent in a separate worker with a task queue so crashes are contained and you can scale independently."

3. **"Why browser-use?"** — "50k+ GitHub stars, handles DOM extraction, element targeting, and screenshot capture. I focused on the architecture and UX rather than reimplementing browser automation primitives."

4. **"Why Claude?"** — "Best-in-class tool-use and instruction-following for agentic tasks. browser-use has first-class Anthropic integration."

5. **"Shared Chrome profile"** — "Locally I use a shared Chrome profile so the agent has access to authenticated sessions. In production you'd use a cloud browser service like Browserbase for session management."

6. **"SSE for real-time streaming"** — "The agent takes 30 seconds to minutes per task. Standard request-response would time out and give no feedback. SSE lets the user watch the agent work step by step."

---

## Out of Scope (mention as future work in video)

- User authentication
- Multi-user support
- Rate limiting / cost controls
- Agent memory across sessions
- Cloud browser service integration (Browserbase)
- Horizontal scaling (multiple agent workers)
- SSL / HTTPS
- Database migrations (Alembic) — tables auto-created on startup for demo