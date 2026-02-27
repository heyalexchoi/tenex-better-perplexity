from __future__ import annotations

from asyncio import Queue, Task
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone


@dataclass
class AgentEvent:
    type: str
    data: dict
    timestamp: str


@dataclass
class SessionRuntime:
    session_id: str
    events_queue: Queue[AgentEvent] = field(default_factory=Queue)
    current_task: Task | None = None


active_sessions: dict[str, SessionRuntime] = {}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def event_to_dict(event: AgentEvent) -> dict:
    return asdict(event)
