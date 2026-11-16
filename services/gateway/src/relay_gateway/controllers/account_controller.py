"""Account management for the CLI: who am I, signed-in devices, password, projects and keys.

All endpoints take the account token from `relay login` (``Authorization: Bearer rat_…``).
Changes that could hand a project to someone holding a copied token also need the password
from the last few minutes (``403`` with ``X-Relay-Reauth: required`` → ``POST /v1/auth/reauth``).
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, Field

from relay_gateway.core.container import auth_service, project_service
from relay_gateway.core.http import client_ip
from relay_gateway.models import SECRET_KEY
from relay_gateway.services.auth_service import Principal
from relay_gateway.services.project_service import key_view, project_view

router = APIRouter(prefix="/v1", tags=["account"])


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class OriginsRequest(BaseModel):
    allowed_origins: list[str] = Field(max_length=50)


class KeyCreateRequest(BaseModel):
    kind: str = SECRET_KEY
    name: str = Field(default="", max_length=80)


class PasswordRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class LogoutRequest(BaseModel):
    everywhere: bool = False


async def _caller(request: Request, authorization: str | None, *, sensitive: bool = False) -> Principal:
    return await auth_service.account_principal(authorization, ip=client_ip(request), sensitive=sensitive)


@router.get("/me")
async def me(request: Request, authorization: str | None = Header(default=None)) -> dict:
    principal = await _caller(request, authorization)
    account = await auth_service.account(principal.account_id)
    projects = await project_service.list(principal.account_id)
    return {"email": account.email if account else None, "projects": [project_view(p) for p in projects]}


# --- this device and the others ---------------------------------------------------------------


@router.post("/auth/reauth")
async def reauthenticate(
    body: PasswordRequest, request: Request, authorization: str | None = Header(default=None)
) -> dict:
    await auth_service.reauthenticate(await _caller(request, authorization), body.password)
    return {"status": "ok"}


@router.post("/auth/password")
async def change_password(
    body: PasswordChangeRequest, request: Request, authorization: str | None = Header(default=None)
) -> dict:
    signed_out = await auth_service.change_password(
        await _caller(request, authorization), body.current_password, body.new_password
    )
    return {"status": "ok", "other_devices_signed_out": signed_out}


@router.get("/auth/sessions")
async def list_devices(request: Request, authorization: str | None = Header(default=None)) -> dict:
    principal = await _caller(request, authorization)
    return {
        "sessions": [
            {
                "id": token.id,
                "name": token.name,
                "current": token.id == principal.key_id,
                "created_at": token.created_at.isoformat(),
                "last_used_at": token.last_used_at.isoformat() if token.last_used_at else None,
                "last_used_ip": token.last_used_ip,
                "expires_at": token.expires_at.isoformat() if token.expires_at else None,
            }
            for token in await auth_service.devices(principal)
        ]
    }


@router.delete("/auth/sessions/{session_id}")
async def sign_out_device(
    session_id: str, request: Request, authorization: str | None = Header(default=None)
) -> dict:
    # Signing a device out only ever removes access, so it needs no password.
    await auth_service.sign_out_device(await _caller(request, authorization), session_id)
    return {"status": "revoked"}


@router.post("/auth/logout")
async def logout(
    request: Request, body: LogoutRequest | None = None, authorization: str | None = Header(default=None)
) -> dict:
    signed_out = await auth_service.sign_out(
        await _caller(request, authorization), everywhere=bool(body and body.everywhere)
    )
    return {"status": "ok", "signed_out": signed_out}


# --- projects and keys ------------------------------------------------------------------------


@router.get("/projects")
async def list_projects(request: Request, authorization: str | None = Header(default=None)) -> dict:
    principal = await _caller(request, authorization)
    return {"projects": [project_view(p) for p in await project_service.list(principal.account_id)]}


@router.post("/projects", status_code=201)
async def create_project(
    body: ProjectCreateRequest, request: Request, authorization: str | None = Header(default=None)
) -> dict:
    principal = await _caller(request, authorization)
    return project_view(await project_service.create(principal.account_id, body.name))


@router.put("/projects/{project_id}/origins")
async def set_origins(
    project_id: str, body: OriginsRequest, request: Request, authorization: str | None = Header(default=None)
) -> dict:
    principal = await _caller(request, authorization, sensitive=True)
    return project_view(await project_service.set_allowed_origins(principal.account_id, project_id, body.allowed_origins))


@router.get("/projects/{project_id}/keys")
async def list_keys(project_id: str, request: Request, authorization: str | None = Header(default=None)) -> dict:
    principal = await _caller(request, authorization)
    return {"keys": [key_view(k) for k in await project_service.keys(principal.account_id, project_id)]}


@router.post("/projects/{project_id}/keys", status_code=201)
async def create_key(
    project_id: str, body: KeyCreateRequest, request: Request, authorization: str | None = Header(default=None)
) -> dict:
    principal = await _caller(request, authorization, sensitive=True)
    key, plain = await project_service.create_key(principal.account_id, project_id, kind=body.kind, name=body.name)
    # The only response that ever contains the key itself.
    return {**key_view(key), "key": plain}


@router.delete("/projects/{project_id}/keys/{key_id}")
async def revoke_key(
    project_id: str, key_id: str, request: Request, authorization: str | None = Header(default=None)
) -> dict:
    # Revoking only removes access, so a stolen token cannot use it to lock anyone in.
    principal = await _caller(request, authorization)
    await project_service.revoke_key(principal.account_id, project_id, key_id)
    return {"status": "revoked"}
