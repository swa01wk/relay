"""Pending `relay login` requests (OAuth-style device codes)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from relay_gateway.repositories.database import Database
from relay_gateway.models import DeviceLogin


class DeviceLoginRepository(ABC):
    @abstractmethod
    async def create(self, *, device_hash: str, user_code: str, expires_at: datetime) -> None: ...

    @abstractmethod
    async def approve(self, user_code: str, account_id: str) -> bool:
        """Approve a pending, unexpired request; ``False`` when there is none with this code."""

    @abstractmethod
    async def by_device_hash(self, device_hash: str) -> DeviceLogin | None: ...

    @abstractmethod
    async def consume(self, device_hash: str) -> DeviceLogin | None:
        """Remove and return an approved request, exactly once."""


class MemoryDeviceLoginRepository(DeviceLoginRepository):
    def __init__(self) -> None:
        self._logins: dict[str, DeviceLogin] = {}

    async def create(self, *, device_hash: str, user_code: str, expires_at: datetime) -> None:
        self._logins[device_hash] = DeviceLogin(device_hash, user_code, "pending", expires_at)

    async def approve(self, user_code: str, account_id: str) -> bool:
        now = datetime.now(timezone.utc)
        for login in self._logins.values():
            if login.user_code == user_code and login.status == "pending" and login.expires_at > now:
                login.status, login.account_id = "approved", account_id
                return True
        return False

    async def by_device_hash(self, device_hash: str) -> DeviceLogin | None:
        return self._logins.get(device_hash)

    async def consume(self, device_hash: str) -> DeviceLogin | None:
        login = self._logins.get(device_hash)
        if login is None or login.status != "approved":
            return None
        return self._logins.pop(device_hash)


def _login(row) -> DeviceLogin:
    account_id = str(row["account_id"]) if row["account_id"] else None
    return DeviceLogin(row["device_hash"], row["user_code"], row["status"], row["expires_at"], account_id)


class PostgresDeviceLoginRepository(DeviceLoginRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def create(self, *, device_hash: str, user_code: str, expires_at: datetime) -> None:
        pool = await self._db.pool()
        await pool.execute("DELETE FROM relay_device_logins WHERE expires_at < NOW()")
        await pool.execute(
            "INSERT INTO relay_device_logins (device_hash, user_code, expires_at) VALUES ($1, $2, $3)",
            device_hash, user_code, expires_at,
        )  # fmt: skip

    async def approve(self, user_code: str, account_id: str) -> bool:
        status = await (await self._db.pool()).execute(
            "UPDATE relay_device_logins SET status = 'approved', account_id = $2::uuid "
            "WHERE user_code = $1 AND status = 'pending' AND expires_at > NOW()",
            user_code, account_id,
        )  # fmt: skip
        return status.endswith(" 1")

    async def by_device_hash(self, device_hash: str) -> DeviceLogin | None:
        row = await (await self._db.pool()).fetchrow(
            "SELECT * FROM relay_device_logins WHERE device_hash = $1", device_hash
        )
        return _login(row) if row else None

    async def consume(self, device_hash: str) -> DeviceLogin | None:
        row = await (await self._db.pool()).fetchrow(
            "DELETE FROM relay_device_logins WHERE device_hash = $1 AND status = 'approved' RETURNING *", device_hash
        )
        return _login(row) if row else None
