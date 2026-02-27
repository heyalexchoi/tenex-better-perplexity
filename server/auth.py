from __future__ import annotations

import os

from fastapi import HTTPException, Request

APP_PASSWORD = os.getenv("APP_PASSWORD", "").strip()


def require_auth(request: Request) -> None:
    if request.method == "OPTIONS":
        return
    if not APP_PASSWORD:
        return

    token = request.headers.get("x-auth") or request.query_params.get("auth")
    if token != APP_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
