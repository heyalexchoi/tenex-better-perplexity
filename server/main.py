from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from server.agent import run_agent_task
from server.auth import require_auth
from server.database import check_db_ready, get_session
from server.models import Message, MessageCreate, Session, SessionResponse
from server.runtime import MessageStreamState, SessionRuntime, active_sessions, event_to_dict, run_streams

def _cleanup_screenshots(directory: Path, max_count: int = 100) -> None:
    files = sorted(directory.glob("*.png"), key=lambda f: f.stat().st_mtime)
    for f in files[:-max_count] if len(files) > max_count else []:
        f.unlink(missing_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    await check_db_ready()
    _cleanup_screenshots(SCREENSHOT_ROOT)
    yield


app = FastAPI(title="Better Perplexity API", version="0.1.0", lifespan=lifespan)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])
SCREENSHOT_ROOT = Path(os.getenv("SCREENSHOT_DIR", "/workspace/data/screenshots"))
SCREENSHOT_ROOT.mkdir(parents=True, exist_ok=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/api/files/screenshots", StaticFiles(directory=str(SCREENSHOT_ROOT)), name="screenshots")


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@router.post("/auth/check")
async def auth_check() -> dict:
    return {"ok": True}


@router.post("/sessions", response_model=SessionResponse)
async def create_session(db: AsyncSession = Depends(get_session)) -> SessionResponse:
    session = Session()
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionResponse(
        id=session.id,
        created_at=session.created_at,
        status=session.status,
        active_run_id=None,
        messages=[],
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session_data(session_id: str, db: AsyncSession = Depends(get_session)) -> SessionResponse:
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    messages = (
        (await db.exec(select(Message).where(Message.session_id == session_id).order_by(Message.timestamp.asc())))
        .all()
    )
    runtime = active_sessions.get(session_id)
    active_run_id = runtime.active_run_id if runtime else None
    return SessionResponse(
        id=session.id,
        created_at=session.created_at,
        status=session.status,
        active_run_id=active_run_id,
        messages=messages,
    )


@router.post("/sessions/{session_id}/messages")
async def create_message(
    session_id: str,
    payload: MessageCreate,
    db: AsyncSession = Depends(get_session),
) -> dict:
    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    runtime = active_sessions.get(session_id)
    if runtime is None:
        runtime = SessionRuntime(session_id=session_id)
        active_sessions[session_id] = runtime

    if runtime.current_task and not runtime.current_task.done():
        raise HTTPException(status_code=409, detail="Agent is already running")

    user_message = Message(session_id=session_id, role="user", content=payload.content)
    db.add(user_message)
    await db.commit()
    await db.refresh(user_message)

    run_id = uuid4().hex
    previous_run_id = runtime.active_run_id
    if previous_run_id:
        run_streams.pop(previous_run_id, None)

    runtime.active_run_id = run_id
    run_streams[run_id] = (session_id, MessageStreamState(
        run_id=run_id,
    ))
    session.status = "running"
    db.add(session)
    await db.commit()

    runtime.current_task = asyncio.create_task(run_agent_task(runtime))
    return {
        "user_message": user_message.model_dump(mode="json"),
        "run_id": run_id,
    }


@router.get("/sessions/{session_id}/stream")
async def stream_session(session_id: str, run_id: str):
    stream_entry = run_streams.get(run_id)
    if stream_entry is None:
        raise HTTPException(status_code=404, detail="Run stream not found")
    stream_session_id, state = stream_entry
    if stream_session_id != session_id:
        raise HTTPException(status_code=404, detail="Run stream not found for this session")

    async def event_generator():
        cursor = 0
        while True:
            event, cursor = await state.next_event(cursor)
            if event is None:
                break
            yield f"data: {json.dumps(event_to_dict(event))}\n\n"
            if event.type in ("done", "error"):
                break

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.delete("/sessions/{session_id}")
async def cancel_session(session_id: str, db: AsyncSession = Depends(get_session)) -> dict:
    runtime = active_sessions.get(session_id)
    if runtime and runtime.current_task and not runtime.current_task.done():
        runtime.current_task.cancel()
        try:
            await runtime.current_task
        except asyncio.CancelledError:
            pass

    session = await db.get(Session, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"ok": True, "session_id": session_id}


app.include_router(router)
