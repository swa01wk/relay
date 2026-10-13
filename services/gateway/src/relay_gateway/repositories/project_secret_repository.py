"""A project's secrets, already encrypted by the service that stores them."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from relay_gateway.models import ProjectSecret
from relay_gateway.repositories.database import Database


class ProjectSecretRepository(ABC):
    @abstractmethod
    async def save(self, project_id: str, name: str, *, ciphertext: str, hint: str) -> None: ...

    @abstractmethod
    async def get(self, project_id: str, name: str) -> ProjectSecret | None: ...

    @abstractmethod
    async def of_project(self, project_id: str) -> list[ProjectSecret]: ...

    @abstractmethod
    async def delete(self, project_id: str, name: str) -> bool: ...


class MemoryProjectSecretRepository(ProjectSecretRepository):
    def __init__(self) -> None:
        self._secrets: dict[tuple[str, str], ProjectSecret] = {}

    async def save(self, project_id: str, name: str, *, ciphertext: str, hint: str) -> None:
        self._secrets[(project_id, name)] = ProjectSecret(project_id, name, ciphertext, hint, datetime.now(timezone.utc))

    async def get(self, project_id: str, name: str) -> ProjectSecret | None:
        return self._secrets.get((project_id, name))

    async def of_project(self, project_id: str) -> list[ProjectSecret]:
        return sorted((s for s in self._secrets.values() if s.project_id == project_id), key=lambda s: s.name)

    async def delete(self, project_id: str, name: str) -> bool:
        return self._secrets.pop((project_id, name), None) is not None


def _secret(row) -> ProjectSecret:
    return ProjectSecret(row["project_id"], row["name"], row["ciphertext"], row["hint"], row["updated_at"])


class PostgresProjectSecretRepository(ProjectSecretRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def save(self, project_id: str, name: str, *, ciphertext: str, hint: str) -> None:
        await (await self._db.pool()).execute(
            """
            INSERT INTO relay_project_secrets (project_id, name, ciphertext, hint) VALUES ($1, $2, $3, $4)
            ON CONFLICT (project_id, name) DO UPDATE SET
                ciphertext = EXCLUDED.ciphertext, hint = EXCLUDED.hint, updated_at = NOW()
            """,
            project_id, name, ciphertext, hint,
        )  # fmt: skip

    async def get(self, project_id: str, name: str) -> ProjectSecret | None:
        row = await (await self._db.pool()).fetchrow(
            "SELECT * FROM relay_project_secrets WHERE project_id = $1 AND name = $2", project_id, name
        )
        return _secret(row) if row else None

    async def of_project(self, project_id: str) -> list[ProjectSecret]:
        rows = await (await self._db.pool()).fetch(
            "SELECT * FROM relay_project_secrets WHERE project_id = $1 ORDER BY name", project_id
        )
        return [_secret(row) for row in rows]

    async def delete(self, project_id: str, name: str) -> bool:
        status = await (await self._db.pool()).execute(
            "DELETE FROM relay_project_secrets WHERE project_id = $1 AND name = $2", project_id, name
        )
        return status.endswith(" 1")
