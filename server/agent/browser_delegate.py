"""Browser-use delegation helpers."""

from __future__ import annotations

import asyncio
import base64
import os
from contextlib import suppress
from typing import Any
from uuid import uuid4

from browser_use import Agent as BrowserUseAgent
from browser_use import BrowserSession, ChatAnthropic
from langchain_core.tools import ToolException

from server.agent.events import emit_tool_progress
from server.agent.settings import AgentSettings, browser_model_name
from server.runtime import SessionRuntime, browser_semaphore


def save_screenshot_file(raw: Any, settings: AgentSettings) -> str | None:
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

    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.png"
    path = settings.screenshot_dir / filename
    path.write_bytes(binary)
    return f"{settings.screenshot_url_prefix}/{filename}"


def extract_browser_action_text(agent_output: Any) -> str:
    with suppress(Exception):
        actions = getattr(agent_output, "action", None)
        if actions:
            return str(actions[-1])
    return "step completed"


def compact_browser_report(task: str, browser_result: dict[str, Any]) -> dict[str, Any]:
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
                "thinking": s.get("thinking"),
                "next_goal": s.get("next_goal"),
                "evaluation_previous_goal": s.get("evaluation_previous_goal"),
            }
            for s in list(browser_result.get("steps", []))
        ],
    }


async def run_browser_delegate(
    runtime: SessionRuntime,
    task: str,
    settings: AgentSettings,
) -> dict[str, Any]:
    if browser_semaphore._value == 0:
        raise ToolException("Browser is busy — only one browser task can run at a time. Wait for the current task to finish.")

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is missing")

    async with browser_semaphore:
        llm = ChatAnthropic(model=browser_model_name(settings.browser_agent_model), api_key=api_key)

        chrome_user_data_dir = "data/chrome/user_data_dir"
        browser_kwargs: dict[str, Any] = {"headless": settings.headless}
        if os.path.isdir(chrome_user_data_dir):
            browser_kwargs["user_data_dir"] = chrome_user_data_dir
        browser = BrowserSession(**browser_kwargs)

        steps: list[dict[str, Any]] = []

        async def on_step(browser_state, agent_output, step_number: int) -> None:
            url = getattr(browser_state, "url", None)
            screenshot_url = save_screenshot_file(getattr(browser_state, "screenshot", None), settings)
            action_text = extract_browser_action_text(agent_output)
            thinking = str(getattr(agent_output, "thinking", "") or "")
            next_goal = str(getattr(agent_output, "next_goal", "") or "")
            evaluation = str(getattr(agent_output, "evaluation_previous_goal", "") or "")
            await emit_tool_progress(
                runtime,
                name="browser_use_step",
                output_preview=f"Step {step_number}: {action_text}",
                url=str(url) if url else None,
                screenshot=screenshot_url,
                thinking=thinking or None,
                next_goal=next_goal or None,
                evaluation_previous_goal=evaluation or None,
            )

            steps.append(
                {
                    "step": step_number,
                    "action": action_text,
                    "url": url,
                    "screenshot": screenshot_url,
                    "thinking": thinking or None,
                    "next_goal": next_goal or None,
                    "evaluation_previous_goal": evaluation or None,
                }
            )

        agent = BrowserUseAgent(
            task=task,
            llm=llm,
            browser_session=browser,
            register_new_step_callback=on_step,
            extend_system_message="google is unavailable in your environment. do not navigate to google. use your search tool for searches."
        )

        try:
            history = await asyncio.wait_for(agent.run(max_steps=settings.browser_max_steps), timeout=600)
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
