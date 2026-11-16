"""One-time email links (verify an address, reset a password)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from relay_gateway.models import EmailToken
from relay_gateway.repositories.database import Database


class EmailTokenRepository(ABC):
    @abstractmethod
    async def replace(self, token: EmailToken) -> None:
        """Store a new link and cancel the account's earlier unused links for the same purpose."""

    @abstractmethod
    async def consume(self, token_hash: str, purpose: str) -> EmailToken | None:
        """Mark the link used and return it — once, and only while it is valid."""


class MemoryEmailTokenRepository(EmailTokenRepository):
    def __init__(self) -> None:
        self._tokens: dict[str, EmailToken] = {}

    async def replace(self, token: EmailToken) -> None:
        now = datetime.now(timezone.utc)
        for other in self._tokens.values():
            if other.account_id == token.account_id and other.purpose == token.purpose and other.used_at is None:
                other.used_at = now
        self._tokens[token.token_hash] = token

    async def consume(self, token_hash: str, purpose: str) -> EmailToken | None:
        token = self._tokens.get(token_hash)
        now = datetime.now(timezone.utc)
        if token is None or token.purpose != purpose or token.used_at is not None or token.expires_at <= now:
            return None
        token.used_at = now
        return token


def _token(row) -> EmailToken:
    return EmailToken(row["token_hash"], str(row["account_id"]), row["purpose"], row["expires_at"], row["used_at"])


class PostgresEmailTokenRepository(EmailTokenRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    async def replace(self, token: EmailToken) -> None:
        pool = await self._db.pool()
        async with pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "UPDATE relay_email_tokens SET used_at = NOW() "
                "WHERE account_id = $1::uuid AND purpose = $2 AND used_at IS NULL",
                token.account_id, token.purpose,
            )  # fmt: skip
            await conn.execute("DELETE FROM relay_email_tokens WHERE expires_at < NOW() - INTERVAL '7 days'")
            await conn.execute(
                "INSERT INTO relay_email_tokens (token_hash, account_id, purpose, expires_at) "
                "VALUES ($1, $2::uuid, $3, $4)",
                token.token_hash, token.account_id, token.purpose, token.expires_at,
            )  # fmt: skip

    async def consume(self, token_hash: str, purpose: str) -> EmailToken | None:
        row = await (await self._db.pool()).fetchrow(
            "UPDATE relay_email_tokens SET used_at = NOW() WHERE token_hash = $1 AND purpose = $2 "
            "AND used_at IS NULL AND expires_at > NOW() RETURNING *",
            token_hash, purpose,
        )  # fmt: skip
        return _token(row) if row else None
