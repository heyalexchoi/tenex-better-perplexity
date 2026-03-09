"""Persistence and chat-history reconstruction utilities for agent runs."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage, trim_messages
from sqlmodel import select

from server.agent.settings import AgentSettings
from server.database import async_session
from server.models import Message, Session

logger = logging.getLogger(__name__)


def clip_text(value: Any, *, limit: int = 300) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[:limit] + "..."


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


def sanitize_tool_pairs(messages: list[BaseMessage]) -> list[BaseMessage]:
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


async def _load_message_records(session_id: str, *, limit: int) -> list[Message]:
    fetch_limit = min(limit * 6, 400)
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
    return records


def _safe_parse_meta(meta_json: str | None) -> dict[str, Any]:
    if not meta_json:
        return {}
    try:
        parsed = json.loads(meta_json)
    except json.JSONDecodeError:
        logger.warning("Skipping invalid message meta_json payload.")
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_langchain_message(record: Message) -> BaseMessage | None:
    if record.role == "tool":
        meta = _safe_parse_meta(record.meta_json)
        tool_call_id = meta.get("tool_call_id")
        tool_name = meta.get("tool_name")
        if not tool_call_id or not tool_name:
            logger.warning("Skipping tool message without tool metadata (message_id=%s).", record.id)
            return None
        return ToolMessage(
            content=clip_text(record.content, limit=4000),
            tool_call_id=str(tool_call_id),
            name=str(tool_name),
        )

    if record.role == "assistant":
        tool_calls: list[dict[str, Any]] = []
        meta = _safe_parse_meta(record.meta_json)
        maybe_calls = meta.get("tool_calls")
        if isinstance(maybe_calls, list):
            for call in maybe_calls:
                if not isinstance(call, dict) or not call.get("name"):
                    continue
                tool_calls.append(
                    {
                        "id": call.get("id"),
                        "type": "tool_call",
                        "name": call.get("name"),
                        "args": call.get("args", {}),
                    }
                )
        return AIMessage(content=clip_text(record.content, limit=4000), tool_calls=tool_calls)

    if record.role == "user":
        return HumanMessage(content=clip_text(record.content, limit=4000))

    return None


def _trim_and_repair_history(messages: list[BaseMessage], *, max_tokens: int) -> list[BaseMessage]:
    trimmed = trim_messages(
        messages,
        max_tokens=max_tokens,
        token_counter="approximate",
        strategy="last",
        start_on="human",
        include_system=False,
        allow_partial=False,
    )
    return sanitize_tool_pairs(trimmed)


async def load_recent_chat_messages(session_id: str, settings: AgentSettings) -> list[BaseMessage]:
    records = await _load_message_records(session_id, limit=settings.max_chat_history)

    raw_messages: list[BaseMessage] = []
    for record in records:
        parsed = _to_langchain_message(record)
        if parsed is not None:
            raw_messages.append(parsed)

    return _trim_and_repair_history(raw_messages, max_tokens=settings.max_history_tokens)
