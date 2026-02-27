import asyncio
import os
import sys
from datetime import datetime, timezone

from dotenv import load_dotenv
from browser_use import Agent, BrowserSession, ChatAnthropic


load_dotenv()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def on_step(browser_state, agent_output, step_number: int) -> None:
    action_text = ""
    try:
        actions = getattr(agent_output, "action", None)
        if actions:
            action_text = str(actions[-1])
    except Exception:
        action_text = ""

    if not action_text:
        action_text = "thinking"

    print(
        f"[{_now()}] step={step_number} "
        f"url={getattr(browser_state, 'url', '')} "
        f"screenshot={'yes' if getattr(browser_state, 'screenshot', None) else 'no'} "
        f"action={action_text}",
        flush=True,
    )


async def main() -> int:
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ANTHROPIC_API_KEY is missing; cannot run Milestone 0 smoke test.", file=sys.stderr)
        return 2

    raw_model = os.getenv("AGENT_MODEL", "anthropic:claude-haiku-4-5-20251001")
    model = raw_model.split(":", 1)[1] if ":" in raw_model else raw_model
    headless = os.getenv("HEADLESS", "true").lower() == "true"

    llm = ChatAnthropic(model=model, api_key=api_key)
    browser = BrowserSession(headless=headless)

    task = (
        "Open https://example.com, verify the page loaded, and return the page title in one short sentence."
    )

    agent = Agent(
        task=task,
        llm=llm,
        browser_session=browser,
        register_new_step_callback=on_step,
    )

    print(f"[{_now()}] starting milestone-0 smoke task with model={model}", flush=True)
    try:
        history = await agent.run(max_steps=8)
        final = history.final_result() if hasattr(history, "final_result") else str(history)
        print(f"[{_now()}] done result={final}", flush=True)
        return 0
    finally:
        await browser.stop()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
