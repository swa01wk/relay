"""`relay login`: the CLI shows a short code, the person approves it in a browser, the CLI
receives an account token. The CLI never sees the password; the browser never sees the token."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from relay_gateway.core.errors import BadRequest, NotFound
from relay_gateway.repositories.device_login_repository import DeviceLoginRepository
from relay_gateway.models import ACCOUNT_TOKEN
from relay_gateway.services.auth_service import AuthService, hash_key
from relay_gateway.services.project_service import ProjectService, project_view

_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ23456789"  # no vowels or look-alikes
EXPIRES_IN_SECONDS = 600
POLL_INTERVAL_SECONDS = 2


def normalize_user_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


class DeviceLoginService:
    def __init__(self, logins: DeviceLoginRepository, auth: AuthService, projects: ProjectService) -> None:
        self._logins = logins
        self._auth = auth
        self._projects = projects

    async def start(self, *, base_url: str) -> dict[str, Any]:
        device_code = secrets.token_urlsafe(32)
        user_code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(8))
        await self._logins.create(
            device_hash=hash_key(device_code),
            user_code=user_code,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=EXPIRES_IN_SECONDS),
        )
        base = os.environ.get("RELAY_PUBLIC_URL", "").strip().rstrip("/") or base_url.rstrip("/")
        shown = f"{user_code[:4]}-{user_code[4:]}"
        return {
            "device_code": device_code,
            "user_code": shown,
            "verification_uri": f"{base}/v1/auth/device/verify",
            "verification_uri_complete": f"{base}/v1/auth/device/verify?code={shown}",
            "expires_in": EXPIRES_IN_SECONDS,
            "interval": POLL_INTERVAL_SECONDS,
        }

    async def approve(self, *, user_code: str, email: str, password: str, create_account: bool) -> str:
        """Sign in (or sign up) and approve the CLI's request. Returns the account's email."""
        code = normalize_user_code(user_code)
        if len(code) != 8:
            raise BadRequest("enter the 8-character code shown in your terminal")
        account = await (self._auth.register(email, password) if create_account else self._auth.sign_in(email, password))
        if not await self._logins.approve(code, account.id):
            raise NotFound("that code is not valid or has expired — run `relay login` again")
        return account.email

    async def poll(self, device_code: str) -> dict[str, Any]:
        """``{"status": "pending"}`` until approved, then the account token — exactly once."""
        device_hash = hash_key(device_code)
        login = await self._logins.by_device_hash(device_hash)
        if login is None or login.expires_at <= datetime.now(timezone.utc):
            raise NotFound("login request expired — run `relay login` again")
        if login.status != "approved":
            return {"status": "pending"}
        login = await self._logins.consume(device_hash)
        if login is None or login.account_id is None:
            return {"status": "pending"}
        account = await self._auth.account(login.account_id)
        project = await self._projects.default_for(login.account_id)
        _key, token = await self._auth.issue_key(account_id=login.account_id, kind=ACCOUNT_TOKEN, name="relay CLI")
        return {
            "status": "approved",
            "token": token,
            "email": account.email if account else None,
            "project": project_view(project),
        }
