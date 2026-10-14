"""API keys. Only a hash of each key is stored; the key itself is shown once, at creation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from uuid import uuid4

from relay_gateway.models import ACCOUNT_TOKEN, ApiKey
from relay_gateway.repositories.database import Database


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ApiKeyRepository(ABC):
    @abstractmethod
    async def create(
        self,
        *,
        account_id: str,
        project_id: str | None,
        kind: str,
        name: str,
        prefix: str,
        key_hash: str,
        expires_at: datetime | None = None,
    ) -> ApiKey: ...

    @abstractmethod
    async def active_by_hash(
        self, key_hash: str, *, ip: str | None = None, idle_cutoff: datetime | None = None
    ) -> ApiKey | None:
        """The key with this hash if it is usable — not revoked, not expired, and (for account
        tokens) used since ``idle_cutoff`` — and records this use."""

    @abstractmethod
    async def of_project(self, project_id: str) -> list[ApiKey]: ...

    @abstractmethod
    async def account_tokens(self, account_id: str) -> list[ApiKey]:
        """The account's usable CLI tokens (one per signed-in device)."""

    @abstractmethod
    async def revoke(self, key_id: str, *, project_id: str) -> bool: ...

    @abstractmethod
    async def revoke_account_token(self, key_id: str, *, account_id: str) -> bool: ...

    @abstractmethod
    async def revoke_account_tokens(self, account_id: str, *, keep: str | None = None) -> int:
        """Revoke every CLI token of the account except ``keep``; returns how many."""

    @abstractmethod
    async def revoke_by_hash(self, key_hash: str) -> bool: ...

    @abstractmethod
    async def mark_reauthenticated(self, key_id: str) -> None: ...

    @abstractmethod
    async def note_address(self, key_id: str, ip: str) -> int | None:
        """Remember that the key was used from ``ip``. Returns how many addresses it has now
        been used from when ``ip`` is new for it, or ``None`` when it was seen before."""


MAX_SEEN_IPS = 20


def _usable(key: ApiKey, now: datetime, idle_cutoff: datetime | None) -> bool:
    if key.revoked_at is not None or (key.expires_at is not None and key.expires_at <= now):
        return False
    if idle_cutoff is not None and key.kind == ACCOUNT_TOKEN:
        return (key.last_used_at or key.created_at) > idle_cutoff
    return True


class MemoryApiKeyRepository(ApiKeyRepository):
    def __init__(self) -> None:
        self._keys: dict[str, tuple[str, ApiKey]] = {}  # id → (hash, key)

    async def create(self, *, account_id, project_id, kind, name, prefix, key_hash, expires_at=None) -> ApiKey:
        key = ApiKey(str(uuid4()), account_id, project_id, kind, name, prefix, _now(), expires_at=expires_at)
        if kind == ACCOUNT_TOKEN:
            key.reauthenticated_at = key.created_at  # signing in is proof of the password
        self._keys[key.id] = (key_hash, key)
        return key

    async def active_by_hash(self, key_hash, *, ip=None, idle_cutoff=None) -> ApiKey | None:
        now = _now()
        for stored_hash, key in self._keys.values():
            if stored_hash == key_hash and _usable(key, now, idle_cutoff):
                key.last_used_at, key.last_used_ip = now, ip or key.last_used_ip
                return key
        return None

    async def of_project(self, project_id: str) -> list[ApiKey]:
        return sorted((k for _h, k in self._keys.values() if k.project_id == project_id), key=lambda k: k.created_at)

    async def account_tokens(self, account_id: str) -> list[ApiKey]:
        now = _now()
        return sorted(
            (k for _h, k in self._keys.values()
             if k.account_id == account_id and k.kind == ACCOUNT_TOKEN and _usable(k, now, None)),
            key=lambda k: k.created_at,
        )  # fmt: skip

    async def revoke(self, key_id: str, *, project_id: str) -> bool:
        entry = self._keys.get(key_id)
        if entry is None or entry[1].project_id != project_id or entry[1].revoked_at is not None:
            return False
        entry[1].revoked_at = _now()
        return True

    async def revoke_account_token(self, key_id: str, *, account_id: str) -> bool:
        entry = self._keys.get(key_id)
        key = entry[1] if entry else None
        if key is None or key.account_id != account_id or key.kind != ACCOUNT_TOKEN or key.revoked_at is not None:
            return False
        key.revoked_at = _now()
        return True

    async def revoke_account_tokens(self, account_id: str, *, keep: str | None = None) -> int:
        revoked = 0
        for _h, key in self._keys.values():
            if key.account_id == account_id and key.kind == ACCOUNT_TOKEN and key.revoked_at is None and key.id != keep:
                key.revoked_at = _now()
                revoked += 1
        return revoked

    async def revoke_by_hash(self, key_hash: str) -> bool:
        for stored_hash, key in self._keys.values():
            if stored_hash == key_hash and key.revoked_at is None:
                key.revoked_at = _now()
                return True
        return False

    async def mark_reauthenticated(self, key_id: str) -> None:
        self._keys[key_id][1].reauthenticated_at = _now()

    async def note_address(self, key_id: str, ip: str) -> int | None:
        key = self._keys[key_id][1]
        if ip in key.seen_ips:
            return None
        key.seen_ips = [*key.seen_ips, ip][-MAX_SEEN_IPS:]
        return len(key.seen_ips)


def _key(row) -> ApiKey:
    return ApiKey(
        str(row["id"]), str(row["account_id"]), row["project_id"], row["kind"], row["name"], row["prefix"],
        row["created_at"], row["last_used_at"], row["revoked_at"], row["expires_at"], row["last_used_ip"],
        row["reauthenticated_at"], list(row["seen_ips"] or []),
    )  # fmt: skip


class PostgresApiKeyRepository(ApiKeyRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def create(self, *, account_id, project_id, kind, name, prefix, key_hash, expires_at=None) -> ApiKey:
        row = await (await self._db.pool()).fetchrow(
            "INSERT INTO relay_api_keys (id, account_id, project_id, kind, name, prefix, key_hash, expires_at, "
            "reauthenticated_at) VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, "
            "CASE WHEN $4 = 'account' THEN NOW() END) RETURNING *",
            str(uuid4()), account_id, project_id, kind, name, prefix, key_hash, expires_at,
        )  # fmt: skip
        return _key(row)

    async def active_by_hash(self, key_hash, *, ip=None, idle_cutoff=None) -> ApiKey | None:
        row = await (await self._db.pool()).fetchrow(
            """
            UPDATE relay_api_keys SET last_used_at = NOW(), last_used_ip = COALESCE($2, last_used_ip)
            WHERE key_hash = $1 AND revoked_at IS NULL
              AND (expires_at IS NULL OR expires_at > NOW())
              AND ($3::timestamptz IS NULL OR kind <> 'account' OR COALESCE(last_used_at, created_at) > $3)
            RETURNING *
            """,
            key_hash, ip, idle_cutoff,
        )  # fmt: skip
        return _key(row) if row else None

    async def of_project(self, project_id: str) -> list[ApiKey]:
        rows = await (await self._db.pool()).fetch(
            "SELECT * FROM relay_api_keys WHERE project_id = $1 ORDER BY created_at", project_id
        )
        return [_key(row) for row in rows]

    async def account_tokens(self, account_id: str) -> list[ApiKey]:
        rows = await (await self._db.pool()).fetch(
            "SELECT * FROM relay_api_keys WHERE account_id = $1::uuid AND kind = 'account' AND revoked_at IS NULL "
            "AND (expires_at IS NULL OR expires_at > NOW()) ORDER BY created_at",
            account_id,
        )
        return [_key(row) for row in rows]

    async def revoke(self, key_id: str, *, project_id: str) -> bool:
        status = await (await self._db.pool()).execute(
            "UPDATE relay_api_keys SET revoked_at = NOW() "
            "WHERE id::text = $1 AND project_id = $2 AND revoked_at IS NULL",
            key_id, project_id,
        )  # fmt: skip
        return status.endswith(" 1")

    async def revoke_account_token(self, key_id: str, *, account_id: str) -> bool:
        status = await (await self._db.pool()).execute(
            "UPDATE relay_api_keys SET revoked_at = NOW() WHERE id::text = $1 AND account_id = $2::uuid "
            "AND kind = 'account' AND revoked_at IS NULL",
            key_id, account_id,
        )  # fmt: skip
        return status.endswith(" 1")

    async def revoke_account_tokens(self, account_id: str, *, keep: str | None = None) -> int:
        status = await (await self._db.pool()).execute(
            "UPDATE relay_api_keys SET revoked_at = NOW() WHERE account_id = $1::uuid AND kind = 'account' "
            "AND revoked_at IS NULL AND ($2::text IS NULL OR id::text <> $2)",
            account_id, keep,
        )  # fmt: skip
        return int(status.rsplit(" ", 1)[-1])

    async def revoke_by_hash(self, key_hash: str) -> bool:
        status = await (await self._db.pool()).execute(
            "UPDATE relay_api_keys SET revoked_at = NOW() WHERE key_hash = $1 AND revoked_at IS NULL", key_hash
        )
        return status.endswith(" 1")

    async def mark_reauthenticated(self, key_id: str) -> None:
        await (await self._db.pool()).execute(
            "UPDATE relay_api_keys SET reauthenticated_at = NOW() WHERE id::text = $1", key_id
        )

    async def note_address(self, key_id: str, ip: str) -> int | None:
        row = await (await self._db.pool()).fetchrow(
            "UPDATE relay_api_keys SET seen_ips = (seen_ips || $2::text)[GREATEST(1, cardinality(seen_ips) - $3 + 2):] "
            "WHERE id::text = $1 AND NOT ($2 = ANY(seen_ips)) RETURNING cardinality(seen_ips) AS seen",
            key_id, ip, MAX_SEEN_IPS,
        )  # fmt: skip
        return int(row["seen"]) if row else None

