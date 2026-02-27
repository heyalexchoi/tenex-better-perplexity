from __future__ import annotations

import asyncio
import base64
import json
import os
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from langchain.chat_models import init_chat_model
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.interceptors import MCPToolCallRequest, MCPToolCallResult
from langchain_mcp_adapters.tools import load_mcp_tools

try:
    from langchain.agents import create_agent
except ImportError:  # pragma: no cover
    from langchain.agents import create_react_agent as create_agent

from server.database import async_session
from server.models import Message, Session
from server.runtime import AgentEvent, MessageStreamState, SessionRuntime, now_iso

HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
AGENT_MODEL = os.getenv("AGENT_MODEL", "anthropic:claude-haiku-4-5-20251001")
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "anthropic:claude-haiku-4-5-20251001")
AGENT_MODE = os.getenv("AGENT_MODE", "real").lower()
BROWSER_MCP_COMMAND = os.getenv("BROWSER_MCP_COMMAND", "browser-use")
BROWSER_MCP_ARGS = os.getenv("BROWSER_MCP_ARGS", "--mcp").split()
SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "/workspace/data/screenshots"))
SCREENSHOT_URL_PREFIX = os.getenv("SCREENSHOT_URL_PREFIX", "/api/files/screenshots")

_TOOLS_LOGGED = False


def _normalize_model(model_value: str) -> str:
    if ":" in model_value:
        return model_value
    return f"anthropic:{model_value}"


def _clip_text(value: Any, *, limit: int = 220) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


def _extract_content_blocks(content: Any) -> tuple[str, str]:
    text_parts: list[str] = []
    thinking_parts: list[str] = []
    if isinstance(content, str):
        return content, ""
    if not isinstance(content, list):
        return "", ""

    for block in content:
        if isinstance(block, str):
            text_parts.append(block)
            continue
        if not isinstance(block, dict):
            continue

        block_type = str(block.get("type", ""))
        if block_type == "text" and block.get("text"):
            text_parts.append(str(block["text"]))
        elif block_type in {"thinking", "redacted_thinking"} and block.get("thinking"):
            thinking_parts.append(str(block["thinking"]))
    return "".join(text_parts), "".join(thinking_parts)


def _extract_chunk_parts(chunk: Any) -> tuple[str, str]:
    if chunk is None:
        return "", ""
    content = getattr(chunk, "content", None)
    return _extract_content_blocks(content)


def _extract_final_text(output: Any) -> str:
    if not isinstance(output, dict):
        return ""
    messages = output.get("messages")
    if not isinstance(messages, list):
        return ""

    for msg in reversed(messages):
        msg_type = getattr(msg, "type", None)
        if msg_type != "ai":
            continue
        content = getattr(msg, "content", None)
        text, _ = _extract_content_blocks(content)
        text = text.strip()
        if text:
            return text
    return ""


def _find_in_nested(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        if key in value and value[key] is not None:
            return value[key]
        for nested in value.values():
            found = _find_in_nested(nested, key)
            if found is not None:
                return found
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        for nested in value:
            found = _find_in_nested(nested, key)
            if found is not None:
                return found
    return None


def _extract_tool_context(output: Any) -> dict[str, Any]:
    data: dict[str, Any] = {"output_preview": _clip_text(output)}
    screenshot = _find_in_nested(output, "screenshot")
    url = _find_in_nested(output, "url")
    if screenshot is None:
        # MCP tool output is often a text block containing JSON.
        text_blob = _find_in_nested(output, "text")
        if isinstance(text_blob, str):
            with suppress(Exception):
                parsed = json.loads(text_blob)
                screenshot = _find_in_nested(parsed, "screenshot")
                url = url or _find_in_nested(parsed, "url")
                parsed_preview = dict(parsed)
                if "screenshot" in parsed_preview:
                    parsed_preview["screenshot"] = "[omitted]"
                data["output_preview"] = _clip_text(parsed_preview)
    if screenshot is not None:
        data["screenshot"] = screenshot
    if url is not None:
        data["url"] = url
    return data


def _sanitize_tool_input(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, nested in value.items():
            if key in {"runtime", "state", "messages"}:
                continue
            cleaned[key] = _sanitize_tool_input(nested)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_tool_input(item) for item in value][:20]
    if isinstance(value, str):
        return _clip_text(value, limit=180)
    return value


def _save_screenshot_file(raw: Any) -> str | None:
    if not isinstance(raw, str) or not raw.strip():
        return None

    payload = raw
    if payload.startswith("data:image"):
        payload = payload.split(",", 1)[1] if "," in payload else ""
    if not payload:
        return None

    try:
        binary = base64.b64decode(payload, validate=True)
    except Exception:
        return None

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.png"
    path = SCREENSHOT_DIR / filename
    path.write_bytes(binary)
    return f"{SCREENSHOT_URL_PREFIX}/{filename}"


def _patch_tool_schema_for_anthropic(tool: Any) -> None:
    schema = getattr(tool, "args_schema", None)
    if not isinstance(schema, dict):
        return
    for key in ("oneOf", "anyOf", "allOf"):
        schema.pop(key, None)


async def _anthropic_click_validator(
    request: MCPToolCallRequest,
    handler,
) -> MCPToolCallResult:
    if request["name"] != "browser_click":
        return await handler(request)

    args = request.get("args") or {}
    has_index = args.get("index") is not None
    has_x = args.get("coordinate_x") is not None
    has_y = args.get("coordinate_y") is not None
    has_coords = has_x and has_y
    if has_index == has_coords:
        raise ValueError(
            "browser_click requires either {index} OR {coordinate_x, coordinate_y}."
        )
    return await handler(request)


async def persist_message(
    session_id: str,
    role: Literal["user", "assistant", "tool"],
    content: str,
    *,
    meta_json: str | None = None,
) -> None:
    async with async_session() as db:
        db.add(
            Message(
                session_id=session_id,
                role=role,
                content=content,
                meta_json=meta_json,
            )
        )
        await db.commit()


async def update_session_status(session_id: str, status: str) -> None:
    async with async_session() as db:
        session = await db.get(Session, session_id)
        if session is None:
            return
        session.status = status
        db.add(session)
        await db.commit()


async def _emit(runtime: SessionRuntime, event: AgentEvent) -> None:
    if runtime.stream_state is None:
        runtime.stream_state = MessageStreamState()
    await runtime.stream_state.publish(event)


async def _run_mock_task(runtime: SessionRuntime, user_message: str) -> None:
    await asyncio.sleep(0.2)
    await _emit(
        runtime,
        AgentEvent(
            type="token",
            data={"text": f"Mock response for: {user_message}"},
            timestamp=now_iso(),
        ),
    )
    await asyncio.sleep(0.2)
    done = AgentEvent(
        type="done",
        data={"result": f"Mock response for: {user_message}"},
        timestamp=now_iso(),
    )
    await _emit(runtime, done)
    await persist_message(runtime.session_id, "assistant", done.data["result"])


async def run_agent_task(runtime: SessionRuntime, user_message: str) -> None:
    global _TOOLS_LOGGED
    try:
        await update_session_status(runtime.session_id, "running")
        if runtime.stream_state is None:
            runtime.stream_state = MessageStreamState()

        if AGENT_MODE == "mock":
            await _run_mock_task(runtime, user_message)
            await update_session_status(runtime.session_id, "idle")
            return

        model = init_chat_model(_normalize_model(AGENT_MODEL))
        # Placeholder for future summarization middleware wiring.
        _ = SUMMARY_MODEL

        tool_interceptors = []
        if _normalize_model(AGENT_MODEL).startswith("anthropic:"):
            tool_interceptors.append(_anthropic_click_validator)

        mcp_client = MultiServerMCPClient(
            {
                "browser": {
                    "transport": "stdio",
                    "command": BROWSER_MCP_COMMAND,
                    "args": BROWSER_MCP_ARGS,
                    "env": {
                        "BROWSER_USE_HEADLESS": "true" if HEADLESS else "false",
                    },
                }
            },
            tool_interceptors=tool_interceptors,
        )

        final_text = ""
        tool_inputs: dict[str, dict[str, Any]] = {}
        async with mcp_client.session("browser") as mcp_session:
            tools = await load_mcp_tools(mcp_session, server_name="browser")
            if _normalize_model(AGENT_MODEL).startswith("anthropic:"):
                for tool in tools:
                    _patch_tool_schema_for_anthropic(tool)
            if not _TOOLS_LOGGED:
                print(f"[agent] MCP tools loaded ({len(tools)}): {[tool.name for tool in tools]}")
                _TOOLS_LOGGED = True

            agent = create_agent(model=model, tools=tools)

            async for raw_event in agent.astream_events(
                {"messages": [{"role": "user", "content": user_message}]},
                version="v2",
            ):
                kind = raw_event.get("event")
                data = raw_event.get("data", {})

                if kind == "on_chat_model_stream":
                    text, thinking = _extract_chunk_parts(data.get("chunk"))
                    if thinking:
                        await _emit(
                            runtime,
                            AgentEvent(
                                type="thinking",
                                data={"text": thinking},
                                timestamp=now_iso(),
                            ),
                        )
                    if text:
                        final_text += text
                        await _emit(
                            runtime,
                            AgentEvent(
                                type="token",
                                data={"text": text},
                                timestamp=now_iso(),
                            ),
                        )
                elif kind == "on_tool_start":
                    tool_name = str(raw_event.get("name", "tool"))
                    raw_input = data.get("input", {})
                    clean_input = _sanitize_tool_input(raw_input)
                    run_id = str(raw_event.get("run_id", ""))
                    if run_id:
                        tool_inputs[run_id] = {
                            "name": tool_name,
                            "input": clean_input,
                        }
                    await _emit(
                        runtime,
                        AgentEvent(
                            type="tool_start",
                            data={
                                "name": tool_name,
                                "input": clean_input,
                            },
                            timestamp=now_iso(),
                        ),
                    )
                elif kind == "on_tool_end":
                    run_id = str(raw_event.get("run_id", ""))
                    tool_payload = _extract_tool_context(data.get("output"))
                    screenshot_url = _save_screenshot_file(tool_payload.get("screenshot"))
                    if screenshot_url:
                        tool_payload["screenshot"] = screenshot_url

                    tool_name = str(raw_event.get("name", "tool"))
                    input_meta = tool_inputs.pop(run_id, {})
                    raw_output = data.get("output")
                    tool_call_id = getattr(raw_output, "tool_call_id", None)
                    meta = {
                        "tool_name": tool_name,
                        "tool_call_id": str(tool_call_id) if tool_call_id else None,
                        "input": input_meta.get("input"),
                        "output_preview": tool_payload.get("output_preview"),
                        "url": tool_payload.get("url"),
                        "screenshot": tool_payload.get("screenshot"),
                    }
                    await persist_message(
                        runtime.session_id,
                        "tool",
                        content=str(tool_payload.get("output_preview", "")),
                        meta_json=json.dumps(meta),
                    )

                    await _emit(
                        runtime,
                        AgentEvent(
                            type="tool_end",
                            data={
                                "name": tool_name,
                                **tool_payload,
                            },
                            timestamp=now_iso(),
                        ),
                    )
                elif kind == "on_chain_end" and raw_event.get("name") == "LangGraph":
                    extracted = _extract_final_text(data.get("output"))
                    if extracted:
                        final_text = extracted

        final_text = final_text.strip() or "Task completed."
        done_event = AgentEvent(type="done", data={"result": final_text}, timestamp=now_iso())
        await _emit(runtime, done_event)
        await persist_message(runtime.session_id, "assistant", final_text)
        await update_session_status(runtime.session_id, "idle")

    except asyncio.CancelledError:
        err_event = AgentEvent(
            type="error",
            data={"error": "Task cancelled"},
            timestamp=now_iso(),
        )
        await _emit(runtime, err_event)
        await update_session_status(runtime.session_id, "idle")
        raise

    except Exception as exc:
        err_event = AgentEvent(
            type="error",
            data={"error": str(exc)},
            timestamp=now_iso(),
        )
        await _emit(runtime, err_event)
        await update_session_status(runtime.session_id, "error")
    finally:
        with suppress(Exception):
            runtime.current_task = None
