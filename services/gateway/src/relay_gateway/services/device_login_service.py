"""`relay login`: the CLI shows a short code, the person approves it in a browser, the CLI
receives an account token. The CLI never sees the password; the browser never sees the token."""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from relay_gateway.core.errors import BadRequest, EmailNotVerified, NotFound
from relay_gateway.repositories.device_login_repository import DeviceLoginRepository
from relay_gateway.models import ACCOUNT_TOKEN
from relay_gateway.services.account_email_service import AccountEmailService
from relay_gateway.services.auth_service import AuthService, email_verification_required, hash_key
from relay_gateway.services.project_service import ProjectService, project_view
from relay_gateway.services.rate_limit_service import DEVICE_POLLS, DEVICE_STARTS_PER_IP, RateLimitService

_CODE_ALPHABET = "BCDFGHJKLMNPQRSTVWXZ23456789"  # no vowels or look-alikes
EXPIRES_IN_SECONDS = 600
POLL_INTERVAL_SECONDS = 2


def normalize_user_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


class DeviceLoginService:
    def __init__(
        self,
        logins: DeviceLoginRepository,
        auth: AuthService,
        projects: ProjectService,
        limits: RateLimitService,
        emails: AccountEmailService,
    ) -> None:
        self._emails = emails
        self._logins = logins
        self._auth = auth
        self._projects = projects
        self._limits = limits

    async def start(self, *, base_url: str, ip: str | None = None) -> dict[str, Any]:
        await self._limits.take(DEVICE_STARTS_PER_IP, ip)
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

    async def approve(
        self,
        *,
        user_code: str,
        email: str,
        password: str,
        create_account: bool,
        ip: str | None = None,
        base_url: str = "",
    ) -> tuple[str, str]:
        """Sign in (or sign up) and approve the CLI's request.

        Returns ``("approved", email)``, or ``("verify", email)`` after a sign-up that must first
        be confirmed from the inbox — the terminal stays pending until the person signs in again.
        """
        code = normalize_user_code(user_code)
        if len(code) != 8:
            raise BadRequest("enter the 8-character code shown in your terminal")
        if create_account:
            account = await self._auth.register(email, password, ip=ip)
            if email_verification_required():
                await self._emails.send_verification(account, base_url=base_url)
                return "verify", account.email
        else:
            try:
                account = await self._auth.sign_in(email, password, ip=ip)
            except EmailNotVerified as unverified:
                await self._emails.send_verification(unverified.account, base_url=base_url)  # type: ignore[arg-type]
                raise
        if not await self._logins.approve(code, account.id):
            raise NotFound("that code is not valid or has expired — run `relay login` again")
        return "approved", account.email

    async def poll(self, device_code: str, *, client_name: str = "") -> dict[str, Any]:
        """``{"status": "pending"}`` until approved, then the account token — exactly once.
        ``client_name`` (e.g. the machine's hostname) labels the device in `relay sessions`."""
        device_hash = hash_key(device_code)
        await self._limits.take(DEVICE_POLLS, device_hash)
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
        label = "".join(ch for ch in client_name if ch.isprintable())[:60].strip()
        _key, token = await self._auth.issue_key(
            account_id=login.account_id, kind=ACCOUNT_TOKEN, name=f"relay CLI on {label}" if label else "relay CLI"
        )
        return {
            "status": "approved",
            "token": token,
            "email": account.email if account else None,
            "project": project_view(project),
        }
