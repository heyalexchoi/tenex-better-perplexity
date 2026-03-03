from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from contextlib import suppress
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

from browser_use import Agent as BrowserUseAgent
from browser_use import BrowserSession, ChatAnthropic
from langchain.chat_models import init_chat_model
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, trim_messages
from langchain_core.tools import InjectedToolCallId, tool

try:
    from langchain.agents import create_agent
except ImportError:  # pragma: no cover
    from langchain.agents import create_react_agent as create_agent

from sqlmodel import select

from server.database import async_session
from server.models import Message, Session
from server.runtime import AgentEvent, MessageStreamState, SessionRuntime, now_iso

HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
AGENT_MODEL = os.getenv("AGENT_MODEL", "anthropic:claude-haiku-4-5-20251001")
BROWSER_AGENT_MODEL = os.getenv("BROWSER_AGENT_MODEL", "claude-haiku-4-5-20251001")
AGENT_MODE = os.getenv("AGENT_MODE", "real").lower()
BROWSER_MAX_STEPS = int(os.getenv("BROWSER_MAX_STEPS", "18"))
MAX_CHAT_HISTORY = int(os.getenv("MAX_CHAT_HISTORY", "16"))
MAX_HISTORY_TOKENS = int(os.getenv("MAX_HISTORY_TOKENS", "12000"))
SCREENSHOT_DIR = Path(os.getenv("SCREENSHOT_DIR", "/workspace/data/screenshots"))
SCREENSHOT_URL_PREFIX = os.getenv("SCREENSHOT_URL_PREFIX", "/api/files/screenshots")

logger = logging.getLogger(__name__)


def _normalize_model(model_value: str) -> str:
    if ":" in model_value:
        return model_value
    return f"anthropic:{model_value}"


def _browser_model_name(model_value: str) -> str:
    return model_value.split(":", 1)[1] if ":" in model_value else model_value


def _clip_text(value: Any, *, limit: int = 300) -> str:
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
        text, _ = _extract_content_blocks(getattr(msg, "content", None))
        if text.strip():
            return text.strip()
    return ""


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


def _extract_browser_action_text(agent_output: Any) -> str:
    with suppress(Exception):
        actions = getattr(agent_output, "action", None)
        if actions:
            return str(actions[-1])
    with suppress(Exception):
        return str(getattr(agent_output, "next_goal", ""))
    return "step completed"


def _compact_browser_report(task: str, browser_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": str(task),
        "final_result": str(browser_result.get("final_result", "") or ""),
        "errors": [str(err) for err in list(browser_result.get("errors", []))],
        "urls": [str(u) for u in list(browser_result.get("urls", []))],
        "steps": [
            {
                "step": s.get("step"),
                "action": str(s.get("action", "") or ""),
                "url": str(s.get("url", "") or ""),
                "screenshot": s.get("screenshot"),
            }
            for s in list(browser_result.get("steps", []))
        ],
    }


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


def _sanitize_tool_pairs(messages: list[BaseMessage]) -> list[BaseMessage]:
    ai_ids: set[str] = set()
    tool_ids: set[str] = set()
    for msg in messages:
        if isinstance(msg, AIMessage):
            for tc in msg.tool_calls:
                tc_id = tc.get("id")
                if tc_id:
                    ai_ids.add(str(tc_id))
        elif isinstance(msg, ToolMessage) and msg.tool_call_id:
            tool_ids.add(str(msg.tool_call_id))

    valid_ids = ai_ids.intersection(tool_ids)
    sanitized: list[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            if msg.tool_call_id and str(msg.tool_call_id) in valid_ids:
                sanitized.append(msg)
            continue
        if isinstance(msg, AIMessage) and msg.tool_calls:
            kept_calls = [tc for tc in msg.tool_calls if tc.get("id") and str(tc["id"]) in valid_ids]
            if len(kept_calls) != len(msg.tool_calls):
                msg = msg.model_copy(update={"tool_calls": kept_calls})
            sanitized.append(msg)
            continue
        sanitized.append(msg)
    return sanitized


async def _load_recent_chat_messages(session_id: str, limit: int = MAX_CHAT_HISTORY) -> list[BaseMessage]:
    fetch_limit = min(max(limit * 6, limit), 400)
    async with async_session() as db:
        stmt = (
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.role.in_(["user", "assistant", "tool"]),
            )
            .order_by(Message.timestamp.desc())
            .limit(fetch_limit)
        )
        records = list((await db.exec(stmt)).all())

    records.reverse()
    raw_messages: list[BaseMessage] = []
    for record in records:
        if record.role == "tool":
            tool_call_id = None
            tool_name = None
            with suppress(Exception):
                meta = json.loads(record.meta_json or "{}")
                tool_call_id = meta.get("tool_call_id")
                tool_name = meta.get("tool_name")

            if not tool_call_id or not tool_name:
                continue
            raw_messages.append(
                ToolMessage(
                    content=_clip_text(record.content, limit=4000),
                    tool_call_id=str(tool_call_id),
                    name=str(tool_name),
                )
            )
            continue

        if record.role == "assistant":
            tool_calls: list[dict[str, Any]] = []
            with suppress(Exception):
                meta = json.loads(record.meta_json or "{}")
                maybe_calls = meta.get("tool_calls")
                if isinstance(maybe_calls, list):
                    for call in maybe_calls:
                        if not isinstance(call, dict):
                            continue
                        if not call.get("name"):
                            continue
                        tool_calls.append(
                            {
                                "id": call.get("id"),
                                "type": "tool_call",
                                "name": call.get("name"),
                                "args": call.get("args", {}),
                            }
                        )
            raw_messages.append(AIMessage(content=_clip_text(record.content, limit=4000), tool_calls=tool_calls))
            continue

        raw_messages.append(HumanMessage(content=_clip_text(record.content, limit=4000)))

    trimmed = trim_messages(
        raw_messages,
        max_tokens=MAX_HISTORY_TOKENS,
        token_counter="approximate",
        strategy="last",
        start_on="human",
        include_system=False,
        allow_partial=False,
    )
    result = _sanitize_tool_pairs(trimmed)
    return result


def _extract_ai_message_payload(event_output: Any) -> tuple[str, list[dict[str, Any]], str | None]:
    content = getattr(event_output, "content", None)
    text, _ = _extract_content_blocks(content)
    message_id = getattr(event_output, "id", None)
    raw_tool_calls = getattr(event_output, "tool_calls", None)
    tool_calls: list[dict[str, Any]] = []
    if isinstance(raw_tool_calls, list):
        for call in raw_tool_calls:
            if not isinstance(call, dict):
                continue
            name = call.get("name")
            call_id = call.get("id")
            if not name:
                continue
            tool_calls.append(
                {
                    "id": call_id,
                    "type": "tool_call",
                    "name": name,
                    "args": call.get("args", {}),
                }
            )
    return text.strip(), tool_calls, str(message_id) if message_id else None


def _render_tool_call_summary(tool_calls: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for call in tool_calls:
        name = str(call.get("name", "tool"))
        args = call.get("args", {})
        arg_text = _clip_text(json.dumps(args, ensure_ascii=True), limit=260)
        lines.append(f"Calling {name} with {arg_text}")
    return "\n".join(lines)


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


async def _run_browser_delegate(runtime: SessionRuntime, task: str) -> dict[str, Any]:
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing")

    browser_model = _browser_model_name(BROWSER_AGENT_MODEL)
    llm = ChatAnthropic(model=browser_model, api_key=api_key)
    browser = BrowserSession(headless=HEADLESS)

    steps: list[dict[str, Any]] = []

    async def on_step(browser_state, agent_output, step_number: int) -> None:
        url = getattr(browser_state, "url", None)
        screenshot_url = _save_screenshot_file(getattr(browser_state, "screenshot", None))
        action_text = _extract_browser_action_text(agent_output)

        event_data = {
            "name": "browser_use_step",
            "output_preview": f"Step {step_number}: {action_text}",
            "url": url,
            "screenshot": screenshot_url,
        }
        await _emit(
            runtime,
            AgentEvent(
                type="tool_end",
                data=event_data,
                timestamp=now_iso(),
            ),
        )

        steps.append(
            {
                "step": step_number,
                "action": action_text,
                "url": url,
                "screenshot": screenshot_url,
            }
        )

    agent = BrowserUseAgent(
        task=task,
        llm=llm,
        browser_session=browser,
        register_new_step_callback=on_step,
    )

    try:
        history = await agent.run(max_steps=BROWSER_MAX_STEPS)
    finally:
        await browser.stop()

    final_result = ""
    with suppress(Exception):
        final_result = str(history.final_result() or "")
    errors: list[str] = []
    with suppress(Exception):
        errors = [str(e) for e in (history.errors() or []) if e]
    urls: list[str] = []
    with suppress(Exception):
        urls = [str(u) for u in (history.urls() or []) if u]

    return {
        "final_result": final_result,
        "errors": errors,
        "urls": urls,
        "steps": steps,
    }


async def run_agent_task(runtime: SessionRuntime, user_message: str) -> None:
    try:
        await update_session_status(runtime.session_id, "running")
        if runtime.stream_state is None:
            runtime.stream_state = MessageStreamState()

        if AGENT_MODE == "mock":
            await _run_mock_task(runtime, user_message)
            await update_session_status(runtime.session_id, "idle")
            return

        model = init_chat_model(_normalize_model(AGENT_MODEL))

        @tool
        async def run_browser_task(
            task: str,
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> str:
            """Run a web browsing task in a real browser and return a compact JSON report."""
            browser_result = await _run_browser_delegate(runtime, task)
            report = _compact_browser_report(task, browser_result)
            final_result = str(report.get("final_result", "") or "").strip() or "Browser task completed."
            persist_report = {k: v for k, v in report.items() if k != "final_result"}
            await persist_message(
                runtime.session_id,
                "tool",
                content=final_result,
                meta_json=json.dumps(
                    {
                        "tool_name": "run_browser_task",
                        "tool_call_id": tool_call_id,
                        "input": {"task": str(task)},
                        "url": (persist_report.get("urls") or [None])[-1],
                        "screenshot": None,
                        "report": persist_report,
                    }
                ),
            )
            return json.dumps(report, ensure_ascii=True)

        system_prompt = (
            "You are the user-facing web research chat assistant. "
            "Use normal chat replies for requests that do not require fresh web interaction. "
            "Call run_browser_task only when web browsing/search is needed to answer accurately. "
            "If run_browser_task is used, incorporate its result into a direct final answer."
        )
        agent = create_agent(model=model, tools=[run_browser_task], system_prompt=system_prompt)
        chat_history = await _load_recent_chat_messages(runtime.session_id)

        final_text = ""
        seen_assistant_messages: set[str] = set()
        final_persisted = False
        async for raw_event in agent.astream_events(
            {
                "messages": chat_history
            },
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
                await _emit(
                    runtime,
                    AgentEvent(
                        type="tool_start",
                        data={"name": tool_name, "input": data.get("input", {})},
                        timestamp=now_iso(),
                    ),
                )
            elif kind == "on_tool_end":
                tool_name = str(raw_event.get("name", "tool"))
                await _emit(
                    runtime,
                    AgentEvent(
                        type="tool_end",
                        data={
                            "name": tool_name,
                            "output_preview": _clip_text(data.get("output", "completed"), limit=260),
                        },
                        timestamp=now_iso(),
                    ),
                )
            elif kind == "on_chain_end" and raw_event.get("name") == "LangGraph":
                extracted = _extract_final_text(data.get("output"))
                if extracted:
                    final_text = extracted
            elif kind == "on_chat_model_end":
                output = data.get("output")
                text, tool_calls, message_id = _extract_ai_message_payload(output)
                identity = message_id or f"anon:{hash((text, json.dumps(tool_calls, sort_keys=True, default=str)))}"
                if identity in seen_assistant_messages:
                    continue
                seen_assistant_messages.add(identity)

                if tool_calls:
                    await persist_message(
                        runtime.session_id,
                        "assistant",
                        content=_render_tool_call_summary(tool_calls),
                        meta_json=json.dumps(
                            {
                                "message_id": message_id,
                                "tool_calls": tool_calls,
                            }
                        ),
                    )
                elif text:
                    await persist_message(
                        runtime.session_id,
                        "assistant",
                        content=text,
                        meta_json=json.dumps({"message_id": message_id}),
                    )
                    final_persisted = True
                    final_text = text

        final_text = final_text.strip() or "Task completed."
        done_event = AgentEvent(type="done", data={"result": final_text}, timestamp=now_iso())
        await _emit(runtime, done_event)
        if not final_persisted:
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
        logger.exception("Agent run failed for session_id=%s", runtime.session_id)
        err_event = AgentEvent(
            type="error",
            data={"error": str(exc)},
            timestamp=now_iso(),
        )
        await _emit(runtime, err_event)
        await update_session_status(runtime.session_id, "error")
