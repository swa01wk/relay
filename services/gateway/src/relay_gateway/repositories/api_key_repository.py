"""API keys. Only a hash of each key is stored; the key itself is shown once, at creation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from uuid import uuid4

from relay_gateway.repositories.database import Database
from relay_gateway.models import ApiKey


class ApiKeyRepository(ABC):
    @abstractmethod
    async def create(
        self, *, account_id: str, project_id: str | None, kind: str, name: str, prefix: str, key_hash: str
    ) -> ApiKey: ...

    @abstractmethod
    async def active_by_hash(self, key_hash: str) -> ApiKey | None:
        """The key with this hash unless revoked; records the use."""

    @abstractmethod
    async def of_project(self, project_id: str) -> list[ApiKey]: ...

    @abstractmethod
    async def revoke(self, key_id: str, *, project_id: str) -> bool: ...

    @abstractmethod
    async def revoke_by_hash(self, key_hash: str) -> bool: ...


class MemoryApiKeyRepository(ApiKeyRepository):
    def __init__(self) -> None:
        self._keys: dict[str, tuple[str, ApiKey]] = {}  # id → (hash, key)

    async def create(self, *, account_id, project_id, kind, name, prefix, key_hash) -> ApiKey:
        key = ApiKey(str(uuid4()), account_id, project_id, kind, name, prefix, datetime.now(timezone.utc))
        self._keys[key.id] = (key_hash, key)
        return key

    async def active_by_hash(self, key_hash: str) -> ApiKey | None:
        for stored_hash, key in self._keys.values():
            if stored_hash == key_hash and key.revoked_at is None:
                key.last_used_at = datetime.now(timezone.utc)
                return key
        return None

    async def of_project(self, project_id: str) -> list[ApiKey]:
        return sorted((k for _h, k in self._keys.values() if k.project_id == project_id), key=lambda k: k.created_at)

    async def revoke(self, key_id: str, *, project_id: str) -> bool:
        entry = self._keys.get(key_id)
        if entry is None or entry[1].project_id != project_id or entry[1].revoked_at is not None:
            return False
        entry[1].revoked_at = datetime.now(timezone.utc)
        return True

    async def revoke_by_hash(self, key_hash: str) -> bool:
        key = await self.active_by_hash(key_hash)
        if key is None:
            return False
        key.revoked_at = datetime.now(timezone.utc)
        return True


def _key(row) -> ApiKey:
    return ApiKey(
        str(row["id"]), str(row["account_id"]), row["project_id"], row["kind"], row["name"], row["prefix"],
        row["created_at"], row["last_used_at"], row["revoked_at"],
    )  # fmt: skip


class PostgresApiKeyRepository(ApiKeyRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def create(self, *, account_id, project_id, kind, name, prefix, key_hash) -> ApiKey:
        row = await (await self._db.pool()).fetchrow(
            "INSERT INTO relay_api_keys (id, account_id, project_id, kind, name, prefix, key_hash) "
            "VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7) RETURNING *",
            str(uuid4()), account_id, project_id, kind, name, prefix, key_hash,
        )  # fmt: skip
        return _key(row)

    async def active_by_hash(self, key_hash: str) -> ApiKey | None:
        row = await (await self._db.pool()).fetchrow(
            "UPDATE relay_api_keys SET last_used_at = NOW() WHERE key_hash = $1 AND revoked_at IS NULL RETURNING *",
            key_hash,
        )
        return _key(row) if row else None

    async def of_project(self, project_id: str) -> list[ApiKey]:
        rows = await (await self._db.pool()).fetch(
            "SELECT * FROM relay_api_keys WHERE project_id = $1 ORDER BY created_at", project_id
        )
        return [_key(row) for row in rows]

    async def revoke(self, key_id: str, *, project_id: str) -> bool:
        status = await (await self._db.pool()).execute(
            "UPDATE relay_api_keys SET revoked_at = NOW() "
            "WHERE id::text = $1 AND project_id = $2 AND revoked_at IS NULL",
            key_id, project_id,
        )  # fmt: skip
        return status.endswith(" 1")

    async def revoke_by_hash(self, key_hash: str) -> bool:
        status = await (await self._db.pool()).execute(
            "UPDATE relay_api_keys SET revoked_at = NOW() WHERE key_hash = $1 AND revoked_at IS NULL", key_hash
        )
        return status.endswith(" 1")
