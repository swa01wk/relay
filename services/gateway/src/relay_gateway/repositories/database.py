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
