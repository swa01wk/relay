"""A project's secrets: the customer's own model API key and the tools signing secret.

Values are encrypted before storage and never returned by the API — only a short hint. The one
exception is the tools signing secret, which the customer must copy into their tools service.
"""

from __future__ import annotations

import secrets
from collections.abc import Awaitable, Callable
from typing import Any

from relay_gateway.core.crypto import SecretBox
from relay_gateway.core.errors import BadRequest, NotFound
from relay_gateway.models import OPENAI_API_KEY, TOOLS_SIGNING_SECRET
from relay_gateway.repositories.project_secret_repository import ProjectSecretRepository

# CLI name → stored name, for the secrets a customer may set.
SETTABLE = {"openai": OPENAI_API_KEY}


def _hint(value: str) -> str:
    return f"…{value[-4:]}" if len(value) >= 12 else "…"


class SecretService:
    def __init__(self, secrets_repository: ProjectSecretRepository, box: SecretBox) -> None:
        self._secrets = secrets_repository
        self._box = box
        # Called with the project id after a secret changes (cached runtimes hold the old value).
        self.on_change: Callable[[str], Awaitable[None]] | None = None

    async def _changed(self, project_id: str) -> None:
        if self.on_change is not None:
            await self.on_change(project_id)

    @staticmethod
    def _stored_name(name: str) -> str:
        try:
            return SETTABLE[name.strip().lower()]
        except KeyError:
            raise BadRequest(f"unknown secret {name!r}; available: {', '.join(SETTABLE)}") from None

    async def set(self, project_id: str, name: str, value: str) -> dict[str, Any]:
        stored = self._stored_name(name)
        value = value.strip()
        if not 8 <= len(value) <= 500 or any(ch.isspace() for ch in value):
            raise BadRequest("that does not look like an API key")
        await self._secrets.save(project_id, stored, ciphertext=self._box.encrypt(value), hint=_hint(value))
        await self._changed(project_id)
        return {"name": name.strip().lower(), "hint": _hint(value)}

    async def unset(self, project_id: str, name: str) -> None:
        if not await self._secrets.delete(project_id, self._stored_name(name)):
            raise NotFound("secret not set")
        await self._changed(project_id)

    async def list(self, project_id: str) -> list[dict[str, Any]]:
        by_stored = {s.name: s for s in await self._secrets.of_project(project_id)}
        return [
            {
                "name": name,
                "set": stored in by_stored,
                "hint": by_stored[stored].hint if stored in by_stored else None,
                "updated_at": by_stored[stored].updated_at.isoformat() if stored in by_stored else None,
            }
            for name, stored in SETTABLE.items()
        ]

    async def reveal(self, project_id: str, stored_name: str) -> str | None:
        """Decrypted value for the gateway's own use (never for an API response)."""
        secret = await self._secrets.get(project_id, stored_name)
        return self._box.decrypt(secret.ciphertext) if secret else None

    async def tools_signing_secret(self, project_id: str, *, rotate: bool = False) -> str:
        """The secret Relay signs this project's tool calls with; created on first use."""
        current = None if rotate else await self.reveal(project_id, TOOLS_SIGNING_SECRET)
        if current:
            return current
        value = "rts_" + secrets.token_urlsafe(32)
        await self._secrets.save(project_id, TOOLS_SIGNING_SECRET, ciphertext=self._box.encrypt(value), hint=_hint(value))
        await self._changed(project_id)
        return value
