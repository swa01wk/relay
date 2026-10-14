"""Rate limits and login lockout.

Every limit has a name, a maximum and a window; a request over the limit gets ``429`` with
``Retry-After``. Failed logins are counted per email and per client IP, so guessing one
account's password and spraying many accounts from one address are both slowed down.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

from relay_gateway.core.errors import TooManyRequests
from relay_gateway.repositories.rate_limit_repository import RateLimitRepository


@dataclass(frozen=True)
class Limit:
    name: str
    maximum: int
    window_seconds: int
    message: str


# What a single client may do. Generous for people, tight for scripts.
LOGIN_ATTEMPTS_PER_IP = Limit("login-ip", 30, 15 * 60, "too many sign-in attempts from this address")
FAILED_LOGINS_PER_EMAIL = Limit("login-fail", 5, 15 * 60, "too many failed sign-ins for this account")
SIGNUPS_PER_IP = Limit("signup-ip", 5, 60 * 60, "too many sign-ups from this address")
DEVICE_STARTS_PER_IP = Limit("device-start", 10, 10 * 60, "too many `relay login` attempts from this address")
DEVICE_POLLS = Limit("device-poll", 60, 60, "polling too fast")
FAILED_REAUTH_PER_ACCOUNT = Limit("reauth-fail", 5, 15 * 60, "too many wrong passwords")
SESSIONS_PER_KEY = Limit("session-key", 120, 60, "too many sessions started with this key")
SESSIONS_PER_IP = Limit("session-ip", 30, 60, "too many sessions started from this address")
SESSIONS_PER_END_USER = Limit("session-user", 30, 60, "too many sessions started for this user")
ACCOUNT_CALLS_PER_TOKEN = Limit("account-api", 300, 60, "too many requests")
EMAILS_PER_RECIPIENT = Limit("email-to", 5, 60 * 60, "too many emails sent to this address")
RESET_REQUESTS_PER_IP = Limit("reset-ip", 10, 60 * 60, "too many password reset requests from this address")
RESET_SUBMITS_PER_IP = Limit("reset-submit", 20, 15 * 60, "too many password reset attempts")
KEY_ALERTS_PER_KEY = Limit("key-alert", 3, 60 * 60, "too many key alerts")


def _subject(value: str) -> str:
    # Emails and keys are never stored as limiter keys in clear text.
    return hashlib.sha256(value.strip().lower().encode()).hexdigest()[:32]


class RateLimitService:
    def __init__(self, counters: RateLimitRepository) -> None:
        self._counters = counters

    @staticmethod
    def enabled() -> bool:
        return os.environ.get("RELAY_RATE_LIMITS", "on").lower() not in ("0", "off", "false")

    async def take(self, limit: Limit, subject: str | None) -> None:
        """Count one request against ``limit`` for ``subject``; ``429`` once it is used up."""
        if not subject or not self.enabled():
            return
        count, retry_after = await self._counters.hit(f"{limit.name}:{_subject(subject)}", window_seconds=limit.window_seconds)
        if count > limit.maximum:
            raise TooManyRequests(f"{limit.message}; try again in {retry_after} s", retry_after=retry_after)

    async def ensure_below(self, limit: Limit, subject: str | None) -> None:
        """``429`` if ``limit`` is already used up, without counting this request."""
        if not subject or not self.enabled():
            return
        count, retry_after = await self._counters.count(f"{limit.name}:{_subject(subject)}")
        if count >= limit.maximum:
            raise TooManyRequests(f"{limit.message}; try again in {retry_after} s", retry_after=retry_after)

    async def record_failure(self, limit: Limit, subject: str | None) -> None:
        if subject and self.enabled():
            await self._counters.hit(f"{limit.name}:{_subject(subject)}", window_seconds=limit.window_seconds)

    async def clear(self, limit: Limit, subject: str | None) -> None:
        if subject:
            await self._counters.reset(f"{limit.name}:{_subject(subject)}")
