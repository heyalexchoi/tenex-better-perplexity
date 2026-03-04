"""Agent runtime configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class AgentSettings:
    headless: bool
    agent_model: str
    browser_agent_model: str
    browser_max_steps: int
    max_chat_history: int
    max_history_tokens: int
    screenshot_dir: Path
    screenshot_url_prefix: str


@lru_cache(maxsize=1)
def get_settings() -> AgentSettings:
    return AgentSettings(
        headless=os.getenv("HEADLESS", "true").lower() == "true",
        agent_model=os.getenv("AGENT_MODEL", "anthropic:claude-haiku-4-5-20251001"),
        browser_agent_model=os.getenv("BROWSER_AGENT_MODEL", "claude-haiku-4-5-20251001"),
        browser_max_steps=int(os.getenv("BROWSER_MAX_STEPS", "18")),
        max_chat_history=int(os.getenv("MAX_CHAT_HISTORY", "16")),
        max_history_tokens=int(os.getenv("MAX_HISTORY_TOKENS", "12000")),
        screenshot_dir=Path(os.getenv("SCREENSHOT_DIR", "/workspace/data/screenshots")),
        screenshot_url_prefix=os.getenv("SCREENSHOT_URL_PREFIX", "/api/files/screenshots"),
    )


def normalize_model(model_value: str) -> str:
    if ":" in model_value:
        return model_value
    return f"anthropic:{model_value}"


def browser_model_name(model_value: str) -> str:
    return model_value.split(":", 1)[1] if ":" in model_value else model_value
