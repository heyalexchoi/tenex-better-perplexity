"""Top-level orchestration for a single agent run."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Annotated

from langchain.chat_models import init_chat_model
from langchain_core.tools import InjectedToolCallId, tool

from langchain.agents import create_agent

from server.agent.browser_delegate import compact_browser_report, run_browser_delegate
from server.agent.events import (
    emit_done,
    emit_error,
    emit_thinking,
    emit_token,
    emit_tool_end,
    emit_tool_start,
)
from server.agent.history import clip_text, load_recent_chat_messages, persist_message, update_session_status
from server.agent.llm_output import (
    extract_ai_message_payload,
    extract_chunk_parts,
    extract_final_text,
)
from server.agent.settings import get_settings, normalize_model
from server.runtime import SessionRuntime, run_streams

logger = logging.getLogger(__name__)


async def _cleanup_run_stream(run_id: str, delay: int = 300) -> None:
    try:
        await asyncio.sleep(delay)
    except asyncio.CancelledError:
        return
    run_streams.pop(run_id, None)


async def run_agent_task(runtime: SessionRuntime) -> None:
    try:
        settings = get_settings()
        await update_session_status(runtime.session_id, "running")

        model = init_chat_model(normalize_model(settings.agent_model))

        @tool
        async def run_browser_task(
            task: str,
            tool_call_id: Annotated[str, InjectedToolCallId],
        ) -> str:
            """Run a web browsing task in a real browser and return a compact JSON report."""
            browser_result = await run_browser_delegate(runtime, task, settings)
            report = compact_browser_report(task, browser_result)
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
            "Call run_browser_task ONLY when web browsing/search is needed to answer accurately. "
            "Never call run_browser_task more than once per turn — only one browser task can run at a time. "
            "If you have enough information from previous web browsing / search calls to answer questions accurately, then do not make more tool calls. "
            "If run_browser_task is used, incorporate its result into a direct final answer."
        )
        agent = create_agent(model=model, tools=[run_browser_task], system_prompt=system_prompt)
        chat_history = await load_recent_chat_messages(runtime.session_id, settings)

        final_text = ""
        seen_assistant_messages: set[str] = set()

        async for raw_event in agent.astream_events({"messages": chat_history}, version="v2"):
            kind = raw_event.get("event")
            data = raw_event.get("data", {})

            if kind == "on_chat_model_stream":
                text, thinking = extract_chunk_parts(data.get("chunk"))
                if thinking:
                    await emit_thinking(runtime, thinking)
                if text:
                    final_text += text
                    await emit_token(runtime, text)
                continue

            if kind == "on_tool_start":
                tool_name = str(raw_event.get("name", "tool"))
                tool_input = data.get("input", {})
                logger.info("tool_call session_id=%s tool=%s input=%s", runtime.session_id, tool_name, tool_input)
                await emit_tool_start(
                    runtime,
                    name=tool_name,
                    input_data=tool_input,
                )
                continue

            if kind == "on_tool_end":
                await emit_tool_end(
                    runtime,
                    name=str(raw_event.get("name", "tool")),
                    output_preview=clip_text(data.get("output", "completed"), limit=260),
                )
                continue

            if kind == "on_chain_end" and raw_event.get("name") == "LangGraph":
                extracted = extract_final_text(data.get("output"))
                if extracted:
                    final_text = extracted
                continue

            if kind != "on_chat_model_end":
                continue

            text, tool_calls, message_id = extract_ai_message_payload(data.get("output"))
            identity = message_id or f"anon:{hash((text, json.dumps(tool_calls, sort_keys=True, default=str)))}"
            if identity in seen_assistant_messages:
                continue
            seen_assistant_messages.add(identity)

            if tool_calls:
                await persist_message(
                    runtime.session_id,
                    "assistant",
                    content=text,
                    meta_json=json.dumps({"message_id": message_id, "tool_calls": tool_calls}),
                )
            elif text:
                final_text = text

        final_text = final_text.strip() or "Task completed."
        await persist_message(runtime.session_id, "assistant", final_text)
        await update_session_status(runtime.session_id, "idle")
        await emit_done(runtime, final_text)
        if runtime.active_run_id:
            asyncio.create_task(_cleanup_run_stream(runtime.active_run_id))

    except asyncio.CancelledError:
        await persist_message(runtime.session_id, "assistant", "Task cancelled.")
        await emit_error(runtime, "Task cancelled")
        await update_session_status(runtime.session_id, "idle")
        if runtime.active_run_id:
            asyncio.create_task(_cleanup_run_stream(runtime.active_run_id))
        raise

    except Exception as exc:
        await persist_message(runtime.session_id, "assistant", f"Task failed: {exc}")
        logger.exception("Agent run failed for session_id=%s", runtime.session_id)
        await emit_error(runtime, str(exc))
        await update_session_status(runtime.session_id, "error")
        if runtime.active_run_id:
            asyncio.create_task(_cleanup_run_stream(runtime.active_run_id))
