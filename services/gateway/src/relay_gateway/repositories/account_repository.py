"""Accounts and the projects they own."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from uuid import uuid4

from relay_gateway.repositories.database import Database
from relay_gateway.models import Account, Project


class AccountRepository(ABC):
    @abstractmethod
    async def create_account(self, email: str, password_hash: str) -> Account | None:
        """``None`` when the email is already registered."""

    @abstractmethod
    async def account_by_email(self, email: str) -> Account | None: ...

    @abstractmethod
    async def account(self, account_id: str) -> Account | None: ...

    @abstractmethod
    async def create_project(self, project_id: str, account_id: str, name: str) -> Project: ...

    @abstractmethod
    async def project(self, project_id: str) -> Project | None: ...

    @abstractmethod
    async def projects_of(self, account_id: str) -> list[Project]: ...

    @abstractmethod
    async def set_allowed_origins(self, project_id: str, origins: list[str]) -> None: ...


class MemoryAccountRepository(AccountRepository):
    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}
        self._projects: dict[str, Project] = {}

    async def create_account(self, email: str, password_hash: str) -> Account | None:
        if await self.account_by_email(email) is not None:
            return None
        account = Account(str(uuid4()), email, password_hash, datetime.now(timezone.utc))
        self._accounts[account.id] = account
        return account

    async def account_by_email(self, email: str) -> Account | None:
        return next((a for a in self._accounts.values() if a.email == email), None)

    async def account(self, account_id: str) -> Account | None:
        return self._accounts.get(account_id)

    async def create_project(self, project_id: str, account_id: str, name: str) -> Project:
        project = Project(project_id, account_id, name, datetime.now(timezone.utc))
        self._projects[project.id] = project
        return project

    async def project(self, project_id: str) -> Project | None:
        return self._projects.get(project_id)

    async def projects_of(self, account_id: str) -> list[Project]:
        return sorted((p for p in self._projects.values() if p.account_id == account_id), key=lambda p: p.created_at)

    async def set_allowed_origins(self, project_id: str, origins: list[str]) -> None:
        self._projects[project_id].allowed_origins = list(origins)


def _account(row) -> Account:
    return Account(str(row["id"]), row["email"], row["password_hash"], row["created_at"])


def _project(row) -> Project:
    return Project(row["id"], str(row["account_id"]), row["name"], row["created_at"], list(row["allowed_origins"]))


class PostgresAccountRepository(AccountRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def create_account(self, email: str, password_hash: str) -> Account | None:
        pool = await self._db.pool()
        row = await pool.fetchrow(
            "INSERT INTO relay_accounts (id, email, password_hash) VALUES ($1::uuid, $2, $3) "
            "ON CONFLICT (email) DO NOTHING RETURNING *",
            str(uuid4()), email, password_hash,
        )  # fmt: skip
        return _account(row) if row else None

    async def account_by_email(self, email: str) -> Account | None:
        row = await (await self._db.pool()).fetchrow("SELECT * FROM relay_accounts WHERE email = $1", email)
        return _account(row) if row else None

    async def account(self, account_id: str) -> Account | None:
        row = await (await self._db.pool()).fetchrow("SELECT * FROM relay_accounts WHERE id = $1::uuid", account_id)
        return _account(row) if row else None

    async def create_project(self, project_id: str, account_id: str, name: str) -> Project:
        row = await (await self._db.pool()).fetchrow(
            "INSERT INTO relay_projects (id, account_id, name) VALUES ($1, $2::uuid, $3) RETURNING *",
            project_id, account_id, name,
        )  # fmt: skip
        return _project(row)

    async def project(self, project_id: str) -> Project | None:
        row = await (await self._db.pool()).fetchrow("SELECT * FROM relay_projects WHERE id = $1", project_id)
        return _project(row) if row else None

    async def projects_of(self, account_id: str) -> list[Project]:
        rows = await (await self._db.pool()).fetch(
            "SELECT * FROM relay_projects WHERE account_id = $1::uuid ORDER BY created_at", account_id
        )
        return [_project(row) for row in rows]

    async def set_allowed_origins(self, project_id: str, origins: list[str]) -> None:
        await (await self._db.pool()).execute(
            "UPDATE relay_projects SET allowed_origins = $2 WHERE id = $1", project_id, list(origins)
        )
