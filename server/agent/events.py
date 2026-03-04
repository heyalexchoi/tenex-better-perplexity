"""Helpers for emitting normalized agent stream events."""

from __future__ import annotations

from typing import Any

from server.runtime import AgentEvent, MessageStreamState, SessionRuntime, now_iso


async def emit(runtime: SessionRuntime, event: AgentEvent) -> None:
    if runtime.stream_state is None:
        runtime.stream_state = MessageStreamState()
    await runtime.stream_state.publish(event)


def tool_event_data(
    *,
    name: str,
    input_data: dict[str, Any] | None = None,
    output_preview: str | None = None,
    url: str | None = None,
    screenshot: str | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {"name": name}
    if input_data is not None:
        data["input"] = input_data
    if output_preview is not None:
        data["output_preview"] = output_preview
    if url:
        data["url"] = url
    if screenshot:
        data["screenshot"] = screenshot
    return data


async def emit_tool_start(runtime: SessionRuntime, *, name: str, input_data: dict[str, Any] | None = None) -> None:
    await emit(
        runtime,
        AgentEvent(
            type="tool_start",
            data=tool_event_data(name=name, input_data=input_data or {}),
            timestamp=now_iso(),
        ),
    )


async def emit_tool_progress(
    runtime: SessionRuntime,
    *,
    name: str,
    output_preview: str,
    url: str | None = None,
    screenshot: str | None = None,
) -> None:
    await emit(
        runtime,
        AgentEvent(
            type="tool_progress",
            data=tool_event_data(
                name=name,
                output_preview=output_preview,
                url=url,
                screenshot=screenshot,
            ),
            timestamp=now_iso(),
        ),
    )


async def emit_tool_end(runtime: SessionRuntime, *, name: str, output_preview: str) -> None:
    await emit(
        runtime,
        AgentEvent(
            type="tool_end",
            data=tool_event_data(name=name, output_preview=output_preview),
            timestamp=now_iso(),
        ),
    )


async def emit_thinking(runtime: SessionRuntime, text: str) -> None:
    await emit(runtime, AgentEvent(type="thinking", data={"text": text}, timestamp=now_iso()))


async def emit_token(runtime: SessionRuntime, text: str) -> None:
    await emit(runtime, AgentEvent(type="token", data={"text": text}, timestamp=now_iso()))


async def emit_done(runtime: SessionRuntime, result: str) -> None:
    await emit(runtime, AgentEvent(type="done", data={"result": result}, timestamp=now_iso()))


async def emit_error(runtime: SessionRuntime, error: str) -> None:
    await emit(runtime, AgentEvent(type="error", data={"error": error}, timestamp=now_iso()))
