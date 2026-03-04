"""Utilities for extracting model output and tool-call metadata."""

from __future__ import annotations

import json
from typing import Any

from server.agent.history import clip_text


def extract_content_blocks(content: Any) -> tuple[str, str]:
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


def extract_chunk_parts(chunk: Any) -> tuple[str, str]:
    if chunk is None:
        return "", ""
    content = getattr(chunk, "content", None)
    return extract_content_blocks(content)


def extract_final_text(output: Any) -> str:
    if not isinstance(output, dict):
        return ""
    messages = output.get("messages")
    if not isinstance(messages, list):
        return ""

    for msg in reversed(messages):
        if getattr(msg, "type", None) != "ai":
            continue
        text, _ = extract_content_blocks(getattr(msg, "content", None))
        if text.strip():
            return text.strip()
    return ""


def extract_ai_message_payload(event_output: Any) -> tuple[str, list[dict[str, Any]], str | None]:
    content = getattr(event_output, "content", None)
    text, _ = extract_content_blocks(content)
    message_id = getattr(event_output, "id", None)
    raw_tool_calls = getattr(event_output, "tool_calls", None)
    tool_calls: list[dict[str, Any]] = []
    if isinstance(raw_tool_calls, list):
        for call in raw_tool_calls:
            if not isinstance(call, dict):
                continue
            name = call.get("name")
            if not name:
                continue
            tool_calls.append(
                {
                    "id": call.get("id"),
                    "type": "tool_call",
                    "name": name,
                    "args": call.get("args", {}),
                }
            )
    return text.strip(), tool_calls, str(message_id) if message_id else None


def render_tool_call_summary(tool_calls: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for call in tool_calls:
        name = str(call.get("name", "tool"))
        args = call.get("args", {})
        arg_text = clip_text(json.dumps(args, ensure_ascii=True), limit=260)
        lines.append(f"Calling {name} with {arg_text}")
    return "\n".join(lines)
