"""Starting sessions and reading a session's own data."""

from __future__ import annotations

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from relay_gateway.core.container import auth_service, session_service
from relay_gateway.core.http import client_ip, session_token
from relay_gateway.models import PUBLISHABLE_KEY, SECRET_KEY

router = APIRouter(tags=["sessions"])


class EndUser(BaseModel):
    id: str = Field(min_length=1, max_length=200, description="Your own id for the signed-in user")
    attributes: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Optional extra facts your tools need (e.g. role, org)"
    )


class SessionCreateRequest(BaseModel):
    agent_id: str = Field(min_length=1)
    user: EndUser | None = Field(default=None, description="Secret keys only: which of your users this is for")


class DevSessionCreateRequest(BaseModel):
    project_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)


class SessionCreateResponse(BaseModel):
    session_id: str
    token: str
    dev_token: str
    token_expires_at: str
    events: list[dict]


@router.post("/v1/sessions", response_model=SessionCreateResponse)
async def create_session(
    body: SessionCreateRequest,
    request: Request,
    authorization: str | None = Header(default=None),
    origin: str | None = Header(default=None),
) -> SessionCreateResponse:
    """Start a session with a project key: secret (server) or publishable (browser)."""
    ip = client_ip(request)
    principal = await auth_service.authenticate(authorization, kinds=(SECRET_KEY, PUBLISHABLE_KEY), ip=ip)
    created = await session_service.create_for_key(
        principal,
        agent_id=body.agent_id,
        origin=origin,
        ip=ip,
        user=body.user.model_dump(exclude_defaults=True) if body.user else None,
    )
    return SessionCreateResponse(**created)


@router.post("/dev/sessions", response_model=SessionCreateResponse)
async def create_dev_session(body: DevSessionCreateRequest) -> SessionCreateResponse:
    """Local development only (``RELAY_DEV_SESSIONS=1``): no key, caller names the project."""
    return SessionCreateResponse(**await session_service.create_dev(project_id=body.project_id, agent_id=body.agent_id))


@router.get("/dev/sessions/{session_id}")
async def get_dev_session(session_id: str, request: Request, token: str | None = None) -> dict:
    return session_service.describe(session_id, session_token(request, token) or "")


@router.get("/dev/sessions/{session_id}/timeline")
async def get_session_timeline(session_id: str, request: Request, token: str | None = None) -> dict:
    return await session_service.timeline(session_id, session_token(request, token) or "")
