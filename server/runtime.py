from __future__ import annotations

from asyncio import Condition, Task
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class AgentEvent:
    type: str
    data: dict
    timestamp: str


@dataclass
class MessageStreamState:
    # Buffer for the current in-progress assistant message only.
    events: list[AgentEvent] = field(default_factory=list)
    assistant_text: str = ""
    current_tool: dict | None = None
    closed: bool = False
    _condition: Condition = field(default_factory=Condition, repr=False)

    async def publish(self, event: AgentEvent) -> None:
        async with self._condition:
            self.events.append(event)
            if event.type == "token":
                self.assistant_text += str(event.data.get("text", ""))
            elif event.type == "tool_start":
                self.current_tool = {
                    "name": event.data.get("name"),
                    "input": event.data.get("input"),
                }
            elif event.type == "tool_end":
                self.current_tool = None
            elif event.type in {"done", "error"}:
                self.closed = True
            self._condition.notify_all()

    async def next_event(self, cursor: int) -> tuple[AgentEvent | None, int]:
        async with self._condition:
            while cursor >= len(self.events) and not self.closed:
                await self._condition.wait()
            if cursor < len(self.events):
                event = self.events[cursor]
                return event, cursor + 1
            return None, cursor


@dataclass
class SessionRuntime:
    session_id: str
    current_task: Task | None = None
    stream_state: MessageStreamState | None = None


active_sessions: dict[str, SessionRuntime] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def event_to_dict(event: AgentEvent) -> dict:
    return asdict(event)
