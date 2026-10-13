"""A project's agents and secrets, managed from the CLI with an account token."""

from __future__ import annotations

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from relay_gateway.core.container import auth_service, project_agent_service, project_service, secret_service
from relay_gateway.models import ACCOUNT_TOKEN
from relay_gateway.services.project_agent_service import agent_view

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["agents"])


class AgentPushRequest(BaseModel):
    manifest: str = Field(min_length=1, max_length=100_000, description="The agent manifest (YAML text)")
    system_prompt: str | None = Field(default=None, max_length=100_000)


class SecretSetRequest(BaseModel):
    value: str = Field(min_length=1, max_length=500)


async def _owned_project(project_id: str, authorization: str | None) -> str:
    principal = await auth_service.authenticate(authorization, kinds=(ACCOUNT_TOKEN,))
    return (await project_service.owned(principal.account_id, project_id)).id


@router.get("/agents")
async def list_agents(project_id: str, authorization: str | None = Header(default=None)) -> dict:
    agents = await project_agent_service.list(await _owned_project(project_id, authorization))
    return {"agents": [agent_view(a) for a in agents]}


@router.post("/agents")
async def push_agent(project_id: str, body: AgentPushRequest, authorization: str | None = Header(default=None)) -> dict:
    owned = await _owned_project(project_id, authorization)
    return await project_agent_service.push(owned, body.manifest, system_prompt=body.system_prompt)


@router.delete("/agents/{agent_id}")
async def delete_agent(project_id: str, agent_id: str, authorization: str | None = Header(default=None)) -> dict:
    await project_agent_service.delete(await _owned_project(project_id, authorization), agent_id)
    return {"status": "deleted"}


@router.get("/secrets")
async def list_secrets(project_id: str, authorization: str | None = Header(default=None)) -> dict:
    return {"secrets": await secret_service.list(await _owned_project(project_id, authorization))}


@router.put("/secrets/{name}")
async def set_secret(
    project_id: str, name: str, body: SecretSetRequest, authorization: str | None = Header(default=None)
) -> dict:
    return await secret_service.set(await _owned_project(project_id, authorization), name, body.value)


@router.delete("/secrets/{name}")
async def unset_secret(project_id: str, name: str, authorization: str | None = Header(default=None)) -> dict:
    await secret_service.unset(await _owned_project(project_id, authorization), name)
    return {"status": "removed"}


@router.post("/tools-signing-secret")
async def tools_signing_secret(
    project_id: str, rotate: bool = False, authorization: str | None = Header(default=None)
) -> dict:
    """The secret Relay signs this project's tool calls with — copy it into the tools service."""
    owned = await _owned_project(project_id, authorization)
    return {"signing_secret": await secret_service.tools_signing_secret(owned, rotate=rotate)}
