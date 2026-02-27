# Agent Scaffold: LangGraph + browser-use MCP

## Guidance for Migrating to a Model-Agnostic Streaming Agent with Browser Tools

**Context:** The project currently uses browser-use's `Agent` class directly. We're migrating to a LangGraph-based agent scaffold that's model-agnostic, streaming-capable, and uses MCP for browser tool integration. The web UI already exists — this covers only the agent scaffold + tool layer.

**Why this architecture:**
- Model-agnostic: `init_chat_model` lets you swap Claude/GPT/Gemini with an env var
- Standard tool protocol: MCP for browser tools instead of proprietary integration
- Enterprise middleware: summarization, model fallback, HITL, cost controls — declarative
- Composable: `create_agent` returns a LangGraph graph you can embed in larger workflows

---

## Architecture Overview

```
┌──────────────────────────────────────────────┐
│  LangGraph Agent (create_agent)              │
│  - init_chat_model (any provider)            │
│  - Middleware stack (summarization, etc.)     │
│  - Streaming via .astream_events()           │
└──────────┬───────────────────────────────────┘
           │ MCP tool calls
           ▼
┌──────────────────────────────────────────────┐
│  langchain-mcp-adapters                      │
│  - MultiServerMCPClient                      │
│  - Converts MCP tools → LangChain tools      │
└──────────┬───────────────────────────────────┘
           │ stdio transport (subprocess)
           ▼
┌──────────────────────────────────────────────┐
│  browser-use MCP Server (official)           │
│  uvx --from 'browser-use[cli]' browser-use   │
│  --mcp                                       │
│  - Playwright-based (same stack as current)  │
│  - Low-level tools + agent fallback          │
└──────────────────────────────────────────────┘
```

---

## Authoritative References

These are the primary sources. The coding agent should consult these directly for implementation details:

| Component | Docs | Notes |
|-----------|------|-------|
| **browser-use MCP** | https://docs.browser-use.com/customize/integrations/mcp-server | Official MCP server docs. Shows tools, config, example client code |
| **langchain-mcp-adapters** | https://github.com/langchain-ai/langchain-mcp-adapters | `MultiServerMCPClient`, stdio/HTTP transport, stateful sessions |
| **LangChain create_agent** | https://docs.langchain.com/oss/python/langchain/agents | `create_agent`, system_prompt, middleware |
| **LangChain middleware** | https://docs.langchain.com/oss/python/langchain/middleware/built-in | Full list: Summarization, ModelFallback, HITL, CallLimits, PII, etc. |
| **LangChain MCP integration** | https://docs.langchain.com/oss/python/langchain/mcp | How MCP tools work with create_agent, session lifecycle |
| **init_chat_model** | https://docs.langchain.com/oss/python/langchain/models | Provider-agnostic model init, provider strings |
| **LangChain v1 migration** | https://docs.langchain.com/oss/python/migrate/langchain-v1 | create_react_agent → create_agent migration notes |
| **LangGraph streaming** | https://docs.langchain.com/oss/python/langgraph/overview | astream_events, event types |

---

## Dependencies

```bash
pip install langchain langchain-mcp-adapters langgraph
pip install langchain-anthropic langchain-openai langchain-google-genai  # providers
pip install 'browser-use[cli]'  # official MCP server
```

### Known Issues

**create_agent import regression:** LangChain v1.1.0 had a bug where `create_agent` disappeared from `langchain.agents` (see https://forum.langchain.com/t/create-agent-no-longer-exists-in-langchain-agents-v1-1-0/2350). Fallback:
```python
try:
    from langchain.agents import create_agent
except ImportError:
    from langchain.agents import create_react_agent as create_agent
```

**browser-use CLI install:** `uvx browser-use --mcp` frequently fails with "CLI addon not installed" across multiple versions (see https://github.com/browser-use/browser-use/issues/3023, https://github.com/browser-use/browser-use/issues/3447). Always use:
```bash
uvx --from 'browser-use[cli]' browser-use --mcp
```

---

## Step 1: Model Configuration (Provider-Agnostic)

**Source:** https://docs.langchain.com/oss/python/langchain/models

```python
from langchain.chat_models import init_chat_model

# Format: "provider:model_name"
model = init_chat_model(
    model=os.getenv("AGENT_MODEL", "anthropic:claude-sonnet-4-5-20250514"),
)
```

Supported provider strings (from docs):
- `"anthropic:claude-sonnet-4-5-20250514"` → requires `ANTHROPIC_API_KEY`
- `"openai:gpt-4o"` → requires `OPENAI_API_KEY`
- `"google_genai:gemini-2.0-flash"` → requires `GOOGLE_API_KEY`

One env var change, zero code changes.

---

## Step 2: browser-use MCP Server

**Source:** https://docs.browser-use.com/customize/integrations/mcp-server

### What we know from docs:

The official browser-use MCP server runs via CLI with **stdio transport**. The docs show this client example:

```python
# From the official browser-use docs
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

server_params = StdioServerParameters(
    command="uvx",
    args=["--from", "browser-use[cli]", "browser-use", "--mcp"]
)

async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        
        result = await session.call_tool(
            "browser_navigate",
            arguments={"url": "https://example.com"}
        )
        
        result = await session.call_tool(
            "browser_get_state",
            arguments={"include_screenshot": True}
        )
```

### Available Tools (from docs)

The docs confirm these tools: `browser_navigate`, `browser_get_state` (with `include_screenshot` param), and `retry_with_browser_use_agent` (fallback to full autonomous agent). The docs also reference profiles via `list_browser_profiles`.

> **⚠️ CODING AGENT: Verify the full tool list.** Run the MCP server and call `session.list_tools()` to get the exact set. The tool table below is partially inferred from the example code and community usage — not all confirmed in official docs.

| Tool | Confidence | Source |
|------|-----------|--------|
| `browser_navigate` | ✅ Confirmed | Official docs example |
| `browser_get_state` | ✅ Confirmed | Official docs example (with `include_screenshot`) |
| `retry_with_browser_use_agent` | ✅ Confirmed | Official docs |
| `list_browser_profiles` | ✅ Confirmed | Official docs |
| `browser_click` | ⚠️ Likely | Community example code (GitHub issue #2531) |
| `browser_type` | ⚠️ Likely | Community example code |
| `browser_scroll` | ⚠️ Likely | Consistent with browser-use Controller actions |
| `browser_go_back` | ⚠️ Likely | Consistent with browser-use Controller actions |
| `browser_tab_*` | ⚠️ Likely | Community listings mention these |
| `browser_extract_text` | ⚠️ Likely | Community listings |
| `browser_wait` | ⚠️ Likely | Community listings |

### Connecting via langchain-mcp-adapters

**Source:** https://github.com/langchain-ai/langchain-mcp-adapters

```python
from langchain_mcp_adapters.client import MultiServerMCPClient

mcp_client = MultiServerMCPClient({
    "browser": {
        "transport": "stdio",
        "command": "uvx",
        "args": ["--from", "browser-use[cli]", "browser-use", "--mcp"],
    }
})

tools = await mcp_client.get_tools()
```

### Session Lifecycle

**Source:** https://github.com/langchain-ai/langchain-mcp-adapters (README, "Stateful sessions" section)

The langchain-mcp-adapters README states: "By default, MultiServerMCPClient is stateless—each tool invocation creates a fresh MCP session, executes the tool, and then cleans up." For stateful usage:

```python
async with mcp_client.session("browser") as session:
    tools = await load_mcp_tools(session)
    # tools share the same session — browser state persists
```

> **⚠️ CODING AGENT: Verify session behavior with browser-use MCP specifically.** The langchain-mcp-adapters docs describe stateless vs stateful sessions generically. Whether the browser-use MCP server maintains browser state across tool calls within a *single* stdio subprocess (even without explicit `session()`) needs testing. It's a subprocess that stays alive for the stdio connection — so it *might* keep state by default. Test both `get_tools()` (default stateless) and `session()` (explicit stateful) to confirm which is needed.

### Alternative MCP Servers

If the official browser-use MCP doesn't work well for this use case, these are the alternatives:

| Package | Transport | Stack | Key Difference |
|---------|-----------|-------|----------------|
| `browser-use[cli]` (official) | stdio | Python/Playwright | Low-level tools + agent fallback |
| `https://api.browser-use.com/mcp` (official cloud) | HTTP | Hosted | Requires API key, higher-level `browser_task` |
| `@agent-infra/mcp-server-browser` (ByteDance) | HTTP with `--port` | Node/Puppeteer | Good for Docker container separation |
| `mcp-server-browser-use` (Saik0s/community) | HTTP | Python/browser-use wrapper | `run_browser_agent` high-level tool |

---

## Step 3: Agent with Middleware

**Source:** https://docs.langchain.com/oss/python/langchain/middleware/built-in

```python
from langchain.agents import create_agent
from langchain.agents.middleware import (
    SummarizationMiddleware,
    ModelFallbackMiddleware,
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
)

SYSTEM_PROMPT = """You are a browser automation assistant.
You can navigate websites, click elements, fill forms, and extract information.
When the user asks you to do something on the web, use the browser tools.
When chatting, respond conversationally.
Call browser_get_state to see what's on the page before interacting."""

agent = create_agent(
    model=model,
    tools=tools,
    system_prompt=SYSTEM_PROMPT,
    middleware=[
        SummarizationMiddleware(
            model="openai:gpt-4o-mini",
            trigger=("tokens", 8000),
            keep=("messages", 10),
        ),
        ModelFallbackMiddleware(
            "openai:gpt-4o",
            "google_genai:gemini-2.0-flash",
        ),
        ModelCallLimitMiddleware(
            run_limit=25,
            exit_behavior="end",
        ),
        ToolCallLimitMiddleware(
            tool_name="retry_with_browser_use_agent",
            run_limit=3,
        ),
    ],
)
```

### Middleware Selection Rationale

**Recommended for demo (all from official docs):**

| Middleware | Why | Docs Section |
|-----------|-----|-------------|
| `SummarizationMiddleware` | Browser DOM/screenshots blow up context fast | Confirmed: docs show trigger/keep config |
| `ModelFallbackMiddleware` | Resilience across providers | Confirmed: takes model strings as args |
| `ModelCallLimitMiddleware` | Prevent runaway agent loops | Confirmed: run_limit, thread_limit, exit_behavior |
| `ToolCallLimitMiddleware` | Limit expensive `retry_with_browser_use_agent` calls | Confirmed: tool_name + run_limit |

**If time allows:**

| Middleware | Why |
|-----------|-----|
| `HumanInTheLoopMiddleware` | Pause before destructive browser actions. Requires `checkpointer`. |
| `TodoListMiddleware` | Agent plans multi-step browser tasks |

> **⚠️ CODING AGENT: Verify middleware execution order semantics.** I stated "middleware executes in order" and recommended specific ordering. This is a reasonable assumption but I haven't confirmed it in the LangChain docs. Check https://docs.langchain.com/oss/python/langchain/middleware/overview for ordering guarantees.

---

## Step 4: Streaming

**Source:** LangGraph streaming docs (the `create_agent` return value is a compiled LangGraph graph)

```python
async for event in agent.astream_events(
    {"messages": [{"role": "user", "content": user_input}]},
    config=config,
    version="v2",
):
    kind = event["event"]
    
    if kind == "on_chat_model_stream":
        token = event["data"]["chunk"].content
        if token:
            yield token
    
    elif kind == "on_tool_start":
        tool_name = event["name"]
        tool_input = event["data"].get("input", {})
        yield f"\n🔧 {tool_name}({tool_input})\n"
    
    elif kind == "on_tool_end":
        pass
```

> **⚠️ CODING AGENT: Verify exact event types and data shapes.** The `astream_events` API with `version="v2"` is documented in LangGraph, but the exact event names (`on_chat_model_stream`, `on_tool_start`) and data shapes (`event["data"]["chunk"].content`) should be verified against https://docs.langchain.com/oss/python/langgraph/overview or the LangGraph streaming reference.

---

## Step 5: Full Assembly

```python
import os
import asyncio
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langchain.agents.middleware import (
    SummarizationMiddleware,
    ModelFallbackMiddleware,
    ModelCallLimitMiddleware,
)
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from langgraph.checkpoint.memory import InMemorySaver

SYSTEM_PROMPT = """You are a browser automation assistant.
You can navigate websites, click elements, fill forms, and extract information.
When the user asks you to do something on the web, use the browser tools.
When chatting, respond conversationally.
Call browser_get_state to see what's on the page before interacting."""


async def create_browser_agent():
    """Initialize the agent with MCP browser tools."""
    
    # 1. Model (swap via env var)
    model = init_chat_model(
        os.getenv("AGENT_MODEL", "anthropic:claude-sonnet-4-5-20250514"),
    )
    
    # 2. MCP browser tools (official browser-use MCP server)
    mcp_client = MultiServerMCPClient({
        "browser": {
            "transport": "stdio",
            "command": "uvx",
            "args": ["--from", "browser-use[cli]", "browser-use", "--mcp"],
        }
    })
    
    # 3. Load tools — see ⚠️ note on session lifecycle above
    # Try stateful session first; fall back to get_tools() if not needed
    session = await mcp_client.session("browser").__aenter__()
    tools = await load_mcp_tools(session)
    
    # 4. Agent with middleware
    agent = create_agent(
        model=model,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=InMemorySaver(),
        middleware=[
            SummarizationMiddleware(
                model="openai:gpt-4o-mini",
                trigger=("tokens", 8000),
                keep=("messages", 10),
            ),
            ModelFallbackMiddleware(
                "openai:gpt-4o",
                "google_genai:gemini-2.0-flash",
            ),
            ModelCallLimitMiddleware(
                run_limit=25,
                exit_behavior="end",
            ),
        ],
    )
    
    return agent, mcp_client, session


async def handle_message(agent, user_input: str, thread_id: str):
    """Handle a user message with streaming."""
    config = {"configurable": {"thread_id": thread_id}}
    
    async for event in agent.astream_events(
        {"messages": [{"role": "user", "content": user_input}]},
        config=config,
        version="v2",
    ):
        kind = event["event"]
        if kind == "on_chat_model_stream":
            token = event["data"]["chunk"].content
            if token:
                print(token, end="", flush=True)
        elif kind == "on_tool_start":
            print(f"\n🔧 {event['name']}...")
    print()
```

---

## Migration Checklist

### Remove:
- [ ] `browser_use.Agent` — replaced by `create_agent` (LangGraph)
- [ ] `browser_use.Controller` — replaced by MCP tools (auto-discovered)
- [ ] `browser_use.Browser` / `BrowserConfig` — browser-use MCP server manages its own browser
- [ ] Custom tool wrappers / schema conversion — MCP handles this
- [ ] Direct LangChain ChatModel instantiation — replaced by `init_chat_model`

### Add:
- [ ] `browser-use[cli]` as dependency (already have browser-use, just add extras)
- [ ] `langchain-mcp-adapters` + `MultiServerMCPClient` with stdio config
- [ ] `create_agent` with middleware stack
- [ ] `init_chat_model` with env var for model selection
- [ ] Streaming handler (`astream_events`)
- [ ] Thread management (`InMemorySaver` + thread_id)

### Keep:
- [ ] Web UI (unchanged — wire to new streaming endpoint)
- [ ] Any custom non-browser tools (add to `create_agent` tools list alongside MCP tools)
- [ ] System prompt logic (adapt tool names for MCP naming convention)

---

## Things the Coding Agent Must Verify

These are areas where this guidance is based on reasonable inference but not confirmed in authoritative docs:

1. **Full MCP tool list:** Run `session.list_tools()` on the browser-use MCP server to get exact tool names, descriptions, and parameter schemas
2. **Session statefulness:** Does the browser-use MCP server keep browser state across tool calls within a single stdio subprocess? Or is explicit `mcp_client.session()` required? Test both paths
3. **Middleware execution order:** Does the order of the middleware list matter? Check LangChain middleware docs
4. **Streaming event shapes:** Verify `astream_events` v2 event names and data structures against LangGraph docs
5. **Docker/Playwright:** The MCP server spawns Playwright as a subprocess. Ensure Playwright + Chromium are installed in the Docker image (`playwright install --with-deps chromium`)
6. **`retry_with_browser_use_agent` env vars:** The docs mention this tool needs its own LLM API key. Verify which env vars the MCP server reads (OPENAI_API_KEY? ANTHROPIC_API_KEY? MCP_MODEL_PROVIDER?)

---

## Interview Talking Points

1. **Model agnosticism** — Swap providers with one env var. F500 clients run different stacks (Azure OpenAI, Bedrock, Vertex).
2. **Standard protocols** — MCP for tools, not proprietary integrations. Tool servers are replaceable without touching agent code.
3. **Enterprise middleware** — Cost control, resilience, context management, human oversight. Declarative composition, not hand-rolled plumbing.
4. **Layered autonomy** — Low-level browser tools for precise control, `retry_with_browser_use_agent` for complex tasks. The LLM decides when to escalate.
5. **Ecosystem fluency** — LangChain v1.0 idioms, LangGraph under the hood, official browser-use MCP (not a random community fork).
6. **Pragmatic choices** — Composed the right abstractions instead of building a framework. Middleware over custom StateGraph because cross-cutting concerns (cost, resilience, context) are what F500 cares about.