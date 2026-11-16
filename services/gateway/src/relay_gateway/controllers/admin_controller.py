"""Operator endpoints: session inspector and the approvals/saves audit trail.

Off (404) unless ``RELAY_ADMIN_TOKEN`` is set. The API takes the token as
``Authorization: Bearer <token>`` — never in the URL — and the inspector page (``GET /admin``)
asks for it and keeps it in the browser tab only.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Query
from fastapi.responses import HTMLResponse

from relay_gateway.core.container import admin_service
from relay_gateway.views.inspector_page import INSPECTOR_HTML

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("", response_class=HTMLResponse, include_in_schema=False)
async def inspector() -> HTMLResponse:
    admin_service.require_enabled()
    return HTMLResponse(INSPECTOR_HTML, headers={"Cache-Control": "no-store", "X-Frame-Options": "DENY"})


@router.get("/sessions")
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=500), authorization: str | None = Header(default=None)
) -> dict:
    admin_service.authorize(authorization)
    return {"sessions": await admin_service.list_sessions(limit=limit)}


@router.get("/sessions/{session_id}")
async def session_timeline(session_id: str, authorization: str | None = Header(default=None)) -> dict:
    admin_service.authorize(authorization)
    return await admin_service.session_detail(session_id)


@router.get("/audit")
async def audit_trail(
    limit: int = Query(default=100, ge=1, le=1000),
    session_id: str | None = None,
    authorization: str | None = Header(default=None),
) -> dict:
    admin_service.authorize(authorization)
    return {"entries": await admin_service.audit_trail(limit=limit, session_id=session_id)}
