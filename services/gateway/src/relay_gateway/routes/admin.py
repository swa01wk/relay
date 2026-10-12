"""Operator endpoints: session inspector and the approvals/saves audit trail.

Off (404) unless ``RELAY_ADMIN_TOKEN`` is set. The API takes the token as
``Authorization: Bearer <token>`` — never in the URL — and the inspector page (``GET /admin``)
asks for it and keeps it in the browser tab only.
"""

from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import HTMLResponse

from relay_gateway.deps import event_gateway, event_store, session_manager
from relay_gateway.inspector_page import INSPECTOR_HTML
from relay_runtime.session_audit import AUDIT_EVENT_TYPES, build_audit_trail
from relay_runtime.session_timeline import build_session_timeline

router = APIRouter(prefix="/admin", tags=["admin"])


def _admin_token() -> str:
    token = os.environ.get("RELAY_ADMIN_TOKEN", "").strip()
    if not token:
        raise HTTPException(status_code=404, detail="admin endpoints are disabled")
    return token


def _authorize(authorization: str | None) -> None:
    token = _admin_token()
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        raise HTTPException(status_code=401, detail="invalid admin token")


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def inspector() -> HTMLResponse:
    _admin_token()
    return HTMLResponse(INSPECTOR_HTML, headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=500), authorization: str | None = Header(default=None)
) -> dict:
    _authorize(authorization)
    await event_gateway.flush()
    sessions = await event_store.list_sessions(limit=limit)
    for row in sessions:
        row["live"] = session_manager.get(row["session_id"]) is not None
    return {"sessions": sessions}


@router.get("/sessions/{session_id}")
async def session_timeline(session_id: str, authorization: str | None = Header(default=None)) -> dict:
    _authorize(authorization)
    await event_gateway.flush()
    events = await event_store.list_for_session(session_id)
    if not events:
        raise HTTPException(status_code=404, detail="session not found")
    timeline = build_session_timeline(events)
    timeline["audit"] = build_audit_trail(events)
    return timeline


@router.get("/audit")
async def audit_trail(
    limit: int = Query(default=100, ge=1, le=1000),
    session_id: str | None = None,
    authorization: str | None = Header(default=None),
) -> dict:
    """Approvals and saves across sessions, newest first."""
    _authorize(authorization)
    await event_gateway.flush()
    # An entry spans up to three events (request, decision, commit result).
    events = await event_store.list_by_types(AUDIT_EVENT_TYPES, limit=limit * 4, session_id=session_id)
    return {"entries": build_audit_trail(events, limit=limit)}
