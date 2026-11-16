"""Emails that prove who owns an address: confirming it after sign-up, and resetting a
forgotten password. Each link is single-use, expires, and is stored only as a hash.

Links point at ``RELAY_PUBLIC_URL``. Without it the request's own address is used only for a
local gateway — otherwise someone could make the gateway email a victim a link to their own
server (Host header injection) and collect the reset token.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

from relay_gateway.core.errors import BadRequest, Unavailable
from relay_gateway.integrations.email import Email, EmailSender
from relay_gateway.models import RESET_PASSWORD, VERIFY_EMAIL, Account, EmailToken
from relay_gateway.repositories.account_repository import AccountRepository
from relay_gateway.repositories.email_token_repository import EmailTokenRepository
from relay_gateway.services.auth_service import AuthService, hash_key, validate_password
from relay_gateway.services.rate_limit_service import (
    EMAILS_PER_RECIPIENT,
    FAILED_LOGINS_PER_EMAIL,
    RESET_REQUESTS_PER_IP,
    RESET_SUBMITS_PER_IP,
    RateLimitService,
)

VERIFY_LINK_LIFETIME = timedelta(hours=24)
RESET_LINK_LIFETIME = timedelta(hours=1)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "testserver"}


def link_base(request_base_url: str) -> str:
    public = os.environ.get("RELAY_PUBLIC_URL", "").strip().rstrip("/")
    if public:
        return public
    host = urlsplit(request_base_url).hostname or ""
    dev = os.environ.get("RELAY_DEV_SESSIONS", "").lower() in ("1", "true", "yes")
    if host in _LOCAL_HOSTS or dev:
        return request_base_url.rstrip("/")
    raise Unavailable("email links are not configured on this gateway (RELAY_PUBLIC_URL)")


class AccountEmailService:
    def __init__(
        self,
        accounts: AccountRepository,
        tokens: EmailTokenRepository,
        auth: AuthService,
        sender: EmailSender,
        limits: RateLimitService,
    ) -> None:
        self._accounts = accounts
        self._tokens = tokens
        self._auth = auth
        self._sender = sender
        self._limits = limits

    async def _new_link(self, account: Account, purpose: str, lifetime: timedelta) -> str:
        plain = secrets.token_urlsafe(32)
        await self._tokens.replace(
            EmailToken(hash_key(plain), account.id, purpose, datetime.now(timezone.utc) + lifetime)
        )
        return plain

    async def send_verification(self, account: Account, *, base_url: str) -> None:
        base = link_base(base_url)
        await self._limits.take(EMAILS_PER_RECIPIENT, account.email)
        token = await self._new_link(account, VERIFY_EMAIL, VERIFY_LINK_LIFETIME)
        await self._sender.send(
            Email(
                to=account.email,
                subject="Confirm your email for Relay",
                text=(
                    "Confirm this address to finish creating your Relay account:\n\n"
                    f"{base}/v1/auth/verify-email?token={token}\n\n"
                    "The link works once and expires in 24 hours. If you did not sign up, ignore this email."
                ),
            )
        )

    async def verify_email(self, token: str) -> str:
        """Confirm an address from its link; returns the email."""
        used = await self._tokens.consume(hash_key(token), VERIFY_EMAIL)
        account = await self._accounts.account(used.account_id) if used else None
        if account is None:
            raise BadRequest("this confirmation link is invalid, used or expired — sign in again to get a new one")
        await self._accounts.mark_email_verified(account.id)
        return account.email

    async def request_password_reset(self, email: str, *, base_url: str, ip: str | None) -> None:
        """Email a reset link if the account exists. The answer is the same either way."""
        base = link_base(base_url)
        email = email.strip().lower()
        await self._limits.take(RESET_REQUESTS_PER_IP, ip)
        account = await self._accounts.account_by_email(email)
        if account is None:
            return
        await self._limits.take(EMAILS_PER_RECIPIENT, account.email)
        token = await self._new_link(account, RESET_PASSWORD, RESET_LINK_LIFETIME)
        await self._sender.send(
            Email(
                to=account.email,
                subject="Reset your Relay password",
                text=(
                    "Someone (hopefully you) asked to reset the password of this Relay account.\n\n"
                    f"{base}/v1/auth/reset-password?token={token}\n\n"
                    "The link works once and expires in 1 hour. Resetting signs out every device. "
                    "If you did not ask for this, ignore this email; your password stays the same."
                ),
            )
        )

    async def reset_password(self, token: str, new_password: str, *, ip: str | None) -> str:
        """Set a new password from a reset link; returns the email."""
        await self._limits.take(RESET_SUBMITS_PER_IP, ip)
        validate_password(new_password)  # before using the link, so a weak password can be retried
        used = await self._tokens.consume(hash_key(token), RESET_PASSWORD)
        account = await self._accounts.account(used.account_id) if used else None
        if account is None:
            raise BadRequest("this reset link is invalid, used or expired — ask for a new one")
        await self._auth.set_password(account.id, new_password)
        await self._accounts.mark_email_verified(account.id)  # the link proved the inbox
        await self._limits.clear(FAILED_LOGINS_PER_EMAIL, account.email)
        return account.email
