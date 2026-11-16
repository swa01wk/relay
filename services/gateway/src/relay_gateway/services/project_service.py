"""Projects and their keys. A project is the unit of isolation: its own keys and sessions."""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlsplit

from relay_gateway.core.errors import BadRequest, NotFound
from relay_gateway.repositories.account_repository import AccountRepository
from relay_gateway.repositories.api_key_repository import ApiKeyRepository
from relay_gateway.models import PUBLISHABLE_KEY, SECRET_KEY, ApiKey, Project
from relay_gateway.services.auth_service import AuthService

PROJECT_KEY_KINDS = (SECRET_KEY, PUBLISHABLE_KEY)


def project_view(project: Project) -> dict[str, Any]:
    return {
        "id": project.id,
        "name": project.name,
        "allowed_origins": project.allowed_origins,
        "created_at": project.created_at.isoformat(),
    }


def key_view(key: ApiKey) -> dict[str, Any]:
    return {
        "id": key.id,
        "kind": key.kind,
        "name": key.name,
        "prefix": key.prefix,
        "created_at": key.created_at.isoformat(),
        "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
        "last_used_ip": key.last_used_ip,
        "addresses_seen": len(key.seen_ips),
        "revoked": key.revoked_at is not None,
    }


def _normalize_origin(origin: str) -> str:
    parts = urlsplit(origin.strip())
    if parts.scheme not in ("http", "https") or not parts.netloc or parts.path not in ("", "/"):
        raise BadRequest(f"not an origin (expected e.g. https://app.example.com): {origin}")
    return f"{parts.scheme}://{parts.netloc}".lower()


class ProjectService:
    def __init__(self, accounts: AccountRepository, keys: ApiKeyRepository, auth: AuthService) -> None:
        self._accounts = accounts
        self._keys = keys
        self._auth = auth

    async def list(self, account_id: str) -> list[Project]:
        return await self._accounts.projects_of(account_id)

    async def create(self, account_id: str, name: str) -> Project:
        name = name.strip()
        if not name:
            raise BadRequest("project name is required")
        return await self._accounts.create_project(f"proj_{secrets.token_hex(8)}", account_id, name[:80])

    async def default_for(self, account_id: str) -> Project:
        """The account's first project, created on first login."""
        projects = await self._accounts.projects_of(account_id)
        return projects[0] if projects else await self.create(account_id, "My first project")

    async def owned(self, account_id: str, project_id: str) -> Project:
        project = await self._accounts.project(project_id)
        # Someone else's project looks exactly like a missing one.
        if project is None or project.account_id != account_id:
            raise NotFound("project not found")
        return project

    async def get(self, project_id: str) -> Project | None:
        return await self._accounts.project(project_id)

    async def set_allowed_origins(self, account_id: str, project_id: str, origins: list[str]) -> Project:
        project = await self.owned(account_id, project_id)
        normalized = sorted({_normalize_origin(o) for o in origins})
        await self._accounts.set_allowed_origins(project.id, normalized)
        project.allowed_origins = normalized
        return project

    async def keys(self, account_id: str, project_id: str) -> list[ApiKey]:
        await self.owned(account_id, project_id)
        return await self._keys.of_project(project_id)

    async def create_key(self, account_id: str, project_id: str, *, kind: str, name: str) -> tuple[ApiKey, str]:
        if kind not in PROJECT_KEY_KINDS:
            raise BadRequest(f"kind must be one of: {', '.join(PROJECT_KEY_KINDS)}")
        await self.owned(account_id, project_id)
        return await self._auth.issue_key(account_id=account_id, kind=kind, name=name, project_id=project_id)

    async def revoke_key(self, account_id: str, project_id: str, key_id: str) -> None:
        await self.owned(account_id, project_id)
        if not await self._keys.revoke(key_id, project_id=project_id):
            raise NotFound("key not found")
