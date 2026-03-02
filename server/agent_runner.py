from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from browser_use import Agent as BrowserUseAgent
from browser_use import BrowserSession, ChatAnthropic
from langchain.chat_models import init_chat_model
from langchain_core.tools import tool

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
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "anthropic:claude-haiku-4-5-20251001")
AGENT_MODE = os.getenv("AGENT_MODE", "real").lower()
BROWSER_MAX_STEPS = int(os.getenv("BROWSER_MAX_STEPS", "18"))
MAX_CHAT_HISTORY = int(os.getenv("MAX_CHAT_HISTORY", "16"))
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
            return _clip_text(actions[-1])
    with suppress(Exception):
        return _clip_text(getattr(agent_output, "next_goal", ""))
    return "step completed"


def _compact_browser_report(task: str, browser_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "task": _clip_text(task, limit=600),
        "final_result": _clip_text(browser_result.get("final_result", ""), limit=2400),
        "errors": [_clip_text(err, limit=280) for err in list(browser_result.get("errors", []))[-3:]],
        "urls": [str(u) for u in list(browser_result.get("urls", []))[-6:]],
        "steps": [
            {
                "step": s.get("step"),
                "action": _clip_text(s.get("action", ""), limit=260),
                "url": _clip_text(s.get("url", ""), limit=220),
            }
            for s in list(browser_result.get("steps", []))[-10:]
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


async def _load_recent_chat_messages(session_id: str, limit: int = MAX_CHAT_HISTORY) -> list[dict[str, str]]:
    async with async_session() as db:
        stmt = (
            select(Message)
            .where(
                Message.session_id == session_id,
                Message.role.in_(["user", "assistant"]),
            )
            .order_by(Message.timestamp.desc())
            .limit(limit)
        )
        records = list((await db.exec(stmt)).all())

    records.reverse()
    result: list[dict[str, str]] = []
    for record in records:
        role = "assistant" if record.role == "assistant" else "user"
        result.append({"role": role, "content": _clip_text(record.content, limit=4000)})
    return result


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

        meta = {
            "tool_name": "browser_use_step",
            "tool_call_id": f"step-{step_number}",
            "step": step_number,
            "input": {"task": _clip_text(task, limit=180)},
            "output_preview": event_data["output_preview"],
            "url": url,
            "screenshot": screenshot_url,
        }
        await persist_message(
            runtime.session_id,
            "tool",
            content=event_data["output_preview"],
            meta_json=json.dumps(meta),
        )

        steps.append(
            {
                "step": step_number,
                "action": action_text,
                "url": url,
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
        _ = SUMMARY_MODEL

        @tool
        async def run_browser_task(task: str) -> str:
            """Run a web browsing task in a real browser and return a compact JSON report."""
            browser_result = await _run_browser_delegate(runtime, task)
            report = _compact_browser_report(task, browser_result)
            await persist_message(
                runtime.session_id,
                "tool",
                content=_clip_text(report.get("final_result", "") or "Browser task completed.", limit=350),
                meta_json=json.dumps(
                    {
                        "tool_name": "run_browser_task",
                        "tool_call_id": None,
                        "input": {"task": _clip_text(task, limit=220)},
                        "output_preview": _clip_text(report.get("final_result", "") or "Browser task completed.", limit=350),
                        "url": (report.get("urls") or [None])[-1],
                        "screenshot": None,
                        "report": report,
                    }
                ),
            )
            return json.dumps(report, ensure_ascii=True)

        agent = create_agent(model=model, tools=[run_browser_task])

        chat_history = await _load_recent_chat_messages(runtime.session_id)
        system_prompt = (
            "You are the user-facing assistant. "
            "Use normal chat replies for requests that do not require fresh web interaction. "
            "Call run_browser_task only when web browsing/search is needed to answer accurately. "
            "If run_browser_task is used, incorporate its result into a direct final answer."
        )

        final_text = ""
        async for raw_event in agent.astream_events(
            {
                "messages": [
                    {"role": "system", "content": system_prompt},
                    *chat_history,
                ]
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
        logger.exception("Agent run failed for session_id=%s", runtime.session_id)
        err_event = AgentEvent(
            type="error",
            data={"error": str(exc)},
            timestamp=now_iso(),
        )
        await _emit(runtime, err_event)
        await update_session_status(runtime.session_id, "error")
