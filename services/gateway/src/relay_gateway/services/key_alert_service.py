"""Warn a project's owner when its secret key is used from a new address.

Secret keys belong on the business's own servers, which use the same few addresses; a request
from somewhere new is how a leaked key usually shows up. The first address ever seen is not
reported, and at most a few alerts per key per hour are sent. Publishable keys are used from
every visitor's browser, so they are not tracked.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from relay_gateway.core.errors import TooManyRequests
from relay_gateway.integrations.email import Email, EmailSender
from relay_gateway.models import SECRET_KEY
from relay_gateway.repositories.account_repository import AccountRepository
from relay_gateway.repositories.api_key_repository import ApiKeyRepository
from relay_gateway.services.auth_service import Principal
from relay_gateway.services.rate_limit_service import KEY_ALERTS_PER_KEY, RateLimitService

logger = logging.getLogger(__name__)


class KeyAlertService:
    def __init__(
        self, keys: ApiKeyRepository, accounts: AccountRepository, sender: EmailSender, limits: RateLimitService
    ) -> None:
        self._keys = keys
        self._accounts = accounts
        self._sender = sender
        self._limits = limits

    async def key_used(self, principal: Principal, ip: str | None) -> None:
        if principal.kind != SECRET_KEY or not ip:
            return
        seen = await self._keys.note_address(principal.key_id, ip)
        if seen is None or seen == 1:  # known address, or the very first one
            return
        logger.warning("secret key used from a new address key_id=%s seen=%d", principal.key_id, seen)
        try:
            await self._limits.take(KEY_ALERTS_PER_KEY, principal.key_id)
        except TooManyRequests:
            return
        account = await self._accounts.account(principal.account_id)
        if account is None:
            return
        when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        await self._sender.send(
            Email(
                to=account.email,
                subject="A Relay secret key was used from a new address",
                text=(
                    f"Your secret key {principal.key_id} started a session from {ip} at {when}, "
                    "an address it had not been used from before.\n\n"
                    "If that was your server (a new deployment, a new region), nothing needs doing.\n"
                    "If not, the key may have leaked. Revoke it and create a new one:\n\n"
                    f"  relay keys revoke {principal.key_id}\n  relay keys create --kind secret\n"
                ),
            )
        )
