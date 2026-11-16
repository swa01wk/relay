"""A project's activity for its developers: recent sessions, one session's timeline, and usage.

Read with the account token from `relay login` (``relay logs``, ``relay usage``). Another
account's project, or a session of another project, answers ``404``.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Query, Request

from relay_gateway.core.container import auth_service, project_activity_service, project_service
from relay_gateway.core.http import client_ip

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["activity"])


async def _owned_project(project_id: str, request: Request, authorization: str | None) -> str:
    principal = await auth_service.account_principal(authorization, ip=client_ip(request))
    return (await project_service.owned(principal.account_id, project_id)).id


@router.get("/sessions")
async def list_sessions(
    project_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
    authorization: str | None = Header(default=None),
) -> dict:
    project = await _owned_project(project_id, request, authorization)
    return {"sessions": await project_activity_service.list_sessions(project, limit=limit)}


@router.get("/sessions/{session_id}")
async def session_detail(
    project_id: str, session_id: str, request: Request, authorization: str | None = Header(default=None)
) -> dict:
    project = await _owned_project(project_id, request, authorization)
    return await project_activity_service.session_detail(project, session_id)


@router.get("/usage")
async def usage(
    project_id: str,
    request: Request,
    days: int = Query(default=7, ge=1, le=90),
    authorization: str | None = Header(default=None),
) -> dict:
    project = await _owned_project(project_id, request, authorization)
    return await project_activity_service.usage(project, days=days)
