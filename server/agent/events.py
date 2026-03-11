"""Helpers for emitting normalized agent stream events."""

from __future__ import annotations

from typing import Any

from server.runtime import AgentEvent, SessionRuntime, now_iso, run_streams


async def emit(runtime: SessionRuntime, event: AgentEvent) -> None:
    run_id = runtime.active_run_id
    if not run_id:
        return
    stream_entry = run_streams.get(run_id)
    if stream_entry is None:
        return
    _, stream_state = stream_entry
    if "run_id" not in event.data:
        event.data["run_id"] = run_id
    await stream_state.publish(event)


def tool_event_data(
    *,
    name: str,
    input_data: dict[str, Any] | None = None,
    output_preview: str | None = None,
    url: str | None = None,
    screenshot: str | None = None,
    thinking: str | None = None,
    next_goal: str | None = None,
    evaluation_previous_goal: str | None = None,
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
    if thinking:
        data["thinking"] = thinking
    if next_goal:
        data["next_goal"] = next_goal
    if evaluation_previous_goal:
        data["evaluation_previous_goal"] = evaluation_previous_goal
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
    thinking: str | None = None,
    next_goal: str | None = None,
    evaluation_previous_goal: str | None = None,
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
                thinking=thinking,
                next_goal=next_goal,
                evaluation_previous_goal=evaluation_previous_goal,
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
