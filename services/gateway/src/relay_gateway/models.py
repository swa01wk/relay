"""Domain records shared by every layer: accounts, projects, API keys, device logins."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

# API key kinds
ACCOUNT_TOKEN = "account"  # rat_…  issued by `relay login`; manages projects and keys
SECRET_KEY = "secret"  # rsk_…  a project's server-side key
PUBLISHABLE_KEY = "publishable"  # rpk_…  a project's browser key (can only start sessions)
KEY_PREFIXES = {ACCOUNT_TOKEN: "rat_", SECRET_KEY: "rsk_", PUBLISHABLE_KEY: "rpk_"}


@dataclass
class Account:
    id: str
    email: str
    password_hash: str
    created_at: datetime


@dataclass
class Project:
    id: str
    account_id: str
    name: str
    created_at: datetime
    allowed_origins: list[str] = field(default_factory=list)


@dataclass
class ApiKey:
    id: str
    account_id: str
    project_id: str | None
    kind: str
    name: str
    prefix: str  # first characters of the key, safe to display
    created_at: datetime
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None


@dataclass
class DeviceLogin:
    device_hash: str
    user_code: str
    status: str  # pending | approved
    expires_at: datetime
    account_id: str | None = None


@dataclass
class ProjectAgent:
    """An agent a project defined: where its tools live and how the model is instructed."""

    project_id: str
    agent_id: str
    tools_url: str
    system_prompt: str
    instructions: str
    tool_timeout_seconds: float
    model: str | None
    updated_at: datetime


@dataclass
class ProjectSecret:
    project_id: str
    name: str
    ciphertext: str  # encrypted with the gateway's secrets key; never returned by the API
    hint: str  # last characters, safe to display
    updated_at: datetime


# Secret names
OPENAI_API_KEY = "openai_api_key"
TOOLS_SIGNING_SECRET = "tools_signing_secret"
