from __future__ import annotations

import asyncio
import json
import os

from browser_use import Agent, BrowserSession, ChatAnthropic

from server.database import async_session
from server.models import AgentEventRecord, Message, Session
from server.runtime import AgentEvent, SessionRuntime, now_iso

HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5-20251001")
AGENT_MODE = os.getenv("AGENT_MODE", "real").lower()

browser_session = BrowserSession(
    headless=HEADLESS,
    user_data_dir=os.getenv("CHROME_PROFILE_PATH") or None,
)


async def persist_event(session_id: str, event: AgentEvent) -> None:
    async with async_session() as db:
        db.add(
            AgentEventRecord(
                session_id=session_id,
                type=event.type,
                data=json.dumps(event.data),
            )
        )
        await db.commit()


async def persist_message(session_id: str, role: str, content: str) -> None:
    async with async_session() as db:
        db.add(Message(session_id=session_id, role=role, content=content))
        await db.commit()


async def update_session_status(session_id: str, status: str) -> None:
    async with async_session() as db:
        session = await db.get(Session, session_id)
        if session is None:
            return
        session.status = status
        db.add(session)
        await db.commit()


async def _emit_and_persist(runtime: SessionRuntime, event: AgentEvent) -> None:
    await runtime.events_queue.put(event)
    await persist_event(runtime.session_id, event)


async def _run_mock_task(runtime: SessionRuntime, user_message: str) -> None:
    await asyncio.sleep(0.2)
    step = AgentEvent(
        type="step",
        data={
            "step": 1,
            "action": f"mock_navigate: {user_message[:80]}",
            "url": "https://example.com",
            "screenshot": None,
        },
        timestamp=now_iso(),
    )
    await _emit_and_persist(runtime, step)
    await asyncio.sleep(0.2)
    done = AgentEvent(
        type="done",
        data={"result": f"Mock result for: {user_message}"},
        timestamp=now_iso(),
    )
    await _emit_and_persist(runtime, done)
    await persist_message(runtime.session_id, "assistant", done.data["result"])


async def run_agent_task(runtime: SessionRuntime, user_message: str) -> None:
    try:
        await update_session_status(runtime.session_id, "running")

        if AGENT_MODE == "mock":
            await _run_mock_task(runtime, user_message)
            await update_session_status(runtime.session_id, "idle")
            return

        llm = ChatAnthropic(model=MODEL)

        async def on_step(browser_state, agent_output, step_number: int) -> None:
            action = "thinking"
            if getattr(agent_output, "action", None):
                action = str(agent_output.action[-1])
            event = AgentEvent(
                type="step",
                data={
                    "step": step_number,
                    "action": action,
                    "url": getattr(browser_state, "url", ""),
                    "screenshot": getattr(browser_state, "screenshot", None),
                },
                timestamp=now_iso(),
            )
            await _emit_and_persist(runtime, event)

        agent = Agent(
            task=user_message,
            llm=llm,
            browser_session=browser_session,
            register_new_step_callback=on_step,
        )

        history = await agent.run(max_steps=25)
        final_text = history.final_result() if hasattr(history, "final_result") else str(history)
        done_event = AgentEvent(type="done", data={"result": str(final_text)}, timestamp=now_iso())
        await _emit_and_persist(runtime, done_event)
        await persist_message(runtime.session_id, "assistant", str(final_text))
        await update_session_status(runtime.session_id, "idle")

    except asyncio.CancelledError:
        err_event = AgentEvent(
            type="error",
            data={"error": "Task cancelled"},
            timestamp=now_iso(),
        )
        await _emit_and_persist(runtime, err_event)
        await update_session_status(runtime.session_id, "idle")
        raise

    except Exception as exc:
        err_event = AgentEvent(
            type="error",
            data={"error": str(exc)},
            timestamp=now_iso(),
        )
        await _emit_and_persist(runtime, err_event)
        await update_session_status(runtime.session_id, "error")
