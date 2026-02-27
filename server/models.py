from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import DateTime, Column, Text
from sqlmodel import Field, SQLModel



def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Session(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    created_at: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    status: str = Field(default="idle")


class Message(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    role: str
    content: str
    meta_json: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    timestamp: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class AgentEventRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(foreign_key="session.id", index=True)
    type: str
    data: str
    timestamp: datetime = Field(
        default_factory=utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class MessageCreate(SQLModel):
    content: str


class SessionResponse(SQLModel):
    id: str
    created_at: datetime
    status: str
    messages: list[Message] = Field(default_factory=list)
    events: list[AgentEventRecord] = Field(default_factory=list)
