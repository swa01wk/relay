"""Account management for the CLI: who am I, projects, and project keys.

All endpoints take the account token from `relay login` (``Authorization: Bearer rat_…``).
"""

from __future__ import annotations

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from relay_gateway.core.container import auth_service, project_service
from relay_gateway.models import ACCOUNT_TOKEN, SECRET_KEY
from relay_gateway.services.project_service import key_view, project_view

router = APIRouter(prefix="/v1", tags=["account"])


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class OriginsRequest(BaseModel):
    allowed_origins: list[str] = Field(max_length=50)


class KeyCreateRequest(BaseModel):
    kind: str = SECRET_KEY
    name: str = Field(default="", max_length=80)


async def _account_id(authorization: str | None) -> str:
    return (await auth_service.authenticate(authorization, kinds=(ACCOUNT_TOKEN,))).account_id


@router.get("/me")
async def me(authorization: str | None = Header(default=None)) -> dict:
    account_id = await _account_id(authorization)
    account = await auth_service.account(account_id)
    projects = await project_service.list(account_id)
    return {"email": account.email if account else None, "projects": [project_view(p) for p in projects]}


@router.post("/auth/logout")
async def logout(authorization: str | None = Header(default=None)) -> dict:
    await _account_id(authorization)
    await auth_service.revoke_presented_key(authorization)
    return {"status": "ok"}


@router.get("/projects")
async def list_projects(authorization: str | None = Header(default=None)) -> dict:
    return {"projects": [project_view(p) for p in await project_service.list(await _account_id(authorization))]}


@router.post("/projects", status_code=201)
async def create_project(body: ProjectCreateRequest, authorization: str | None = Header(default=None)) -> dict:
    return project_view(await project_service.create(await _account_id(authorization), body.name))


@router.put("/projects/{project_id}/origins")
async def set_origins(project_id: str, body: OriginsRequest, authorization: str | None = Header(default=None)) -> dict:
    account_id = await _account_id(authorization)
    return project_view(await project_service.set_allowed_origins(account_id, project_id, body.allowed_origins))


@router.get("/projects/{project_id}/keys")
async def list_keys(project_id: str, authorization: str | None = Header(default=None)) -> dict:
    keys = await project_service.keys(await _account_id(authorization), project_id)
    return {"keys": [key_view(k) for k in keys]}


@router.post("/projects/{project_id}/keys", status_code=201)
async def create_key(project_id: str, body: KeyCreateRequest, authorization: str | None = Header(default=None)) -> dict:
    account_id = await _account_id(authorization)
    key, plain = await project_service.create_key(account_id, project_id, kind=body.kind, name=body.name)
    # The only response that ever contains the key itself.
    return {**key_view(key), "key": plain}


@router.delete("/projects/{project_id}/keys/{key_id}")
async def revoke_key(project_id: str, key_id: str, authorization: str | None = Header(default=None)) -> dict:
    await project_service.revoke_key(await _account_id(authorization), project_id, key_id)
    return {"status": "revoked"}
