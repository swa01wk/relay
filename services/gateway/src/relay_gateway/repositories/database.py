"""The gateway's own Postgres tables: accounts, projects, API keys, device logins, and each
project's agents and encrypted secrets."""

from __future__ import annotations

import os

import asyncpg

_SCHEMA = """
CREATE TABLE IF NOT EXISTS relay_accounts (
    id UUID PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS relay_projects (
    id TEXT PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES relay_accounts (id),
    name TEXT NOT NULL,
    allowed_origins TEXT[] NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE TABLE IF NOT EXISTS relay_api_keys (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES relay_accounts (id),
    project_id TEXT REFERENCES relay_projects (id),
    kind TEXT NOT NULL,
    name TEXT NOT NULL,
    prefix TEXT NOT NULL,
    key_hash TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_used_at TIMESTAMPTZ,
    revoked_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS relay_device_logins (
    device_hash TEXT PRIMARY KEY,
    user_code TEXT UNIQUE NOT NULL,
    account_id UUID REFERENCES relay_accounts (id),
    status TEXT NOT NULL DEFAULT 'pending',
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Accounts that existed before email verification count as verified (the DEFAULT fills them
-- once, when the column is added); new accounts start unverified.
ALTER TABLE relay_accounts ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE relay_accounts ALTER COLUMN email_verified_at DROP DEFAULT;
CREATE TABLE IF NOT EXISTS relay_email_tokens (
    token_hash TEXT PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES relay_accounts (id),
    purpose TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS relay_email_tokens_account ON relay_email_tokens (account_id, purpose);
ALTER TABLE relay_api_keys ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
ALTER TABLE relay_api_keys ADD COLUMN IF NOT EXISTS last_used_ip TEXT;
ALTER TABLE relay_api_keys ADD COLUMN IF NOT EXISTS reauthenticated_at TIMESTAMPTZ;
ALTER TABLE relay_api_keys ADD COLUMN IF NOT EXISTS seen_ips TEXT[] NOT NULL DEFAULT '{}';
CREATE INDEX IF NOT EXISTS relay_api_keys_account ON relay_api_keys (account_id, kind);
-- CLI tokens issued before expiry existed get the normal lifetime from their creation.
UPDATE relay_api_keys SET expires_at = created_at + INTERVAL '30 days' WHERE kind = 'account' AND expires_at IS NULL;
CREATE TABLE IF NOT EXISTS relay_project_agents (
    project_id TEXT NOT NULL REFERENCES relay_projects (id),
    agent_id TEXT NOT NULL,
    tools_url TEXT NOT NULL,
    system_prompt TEXT NOT NULL,
    instructions TEXT NOT NULL DEFAULT '',
    tool_timeout_seconds DOUBLE PRECISION NOT NULL DEFAULT 30,
    model TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (project_id, agent_id)
);
CREATE TABLE IF NOT EXISTS relay_project_secrets (
    project_id TEXT NOT NULL REFERENCES relay_projects (id),
    name TEXT NOT NULL,
    ciphertext TEXT NOT NULL,
    hint TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (project_id, name)
);
"""


class Database:
    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = dsn or os.environ["RELAY_DATABASE_URL"]
        self._pool: asyncpg.Pool | None = None

    async def pool(self) -> asyncpg.Pool:
        if self._pool is None:
            self._pool = await asyncpg.create_pool(self._dsn, min_size=1, max_size=5)
            async with self._pool.acquire() as conn:
                await conn.execute(_SCHEMA)
        return self._pool

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
