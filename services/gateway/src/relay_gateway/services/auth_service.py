"""Accounts, passwords and API keys: who is calling, and what they may do.

CLI sign-ins are per device: each `relay login` issues its own account token, which expires
(``TOKEN_LIFETIME``, or after ``TOKEN_IDLE`` unused) and can be revoked on its own. A copied
token is limited on top of that: changes that would let its holder take over a project — new
keys, the model key, agents, allowed origins, the tools signing secret, the password — need the
password again within ``REAUTH_WINDOW`` (``POST /v1/auth/reauth``). Changing the password signs
out every other device.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from relay_gateway.core.errors import (
    BadRequest,
    Conflict,
    EmailNotVerified,
    Forbidden,
    NotFound,
    ReauthRequired,
    Unauthorized,
)
from relay_gateway.models import ACCOUNT_TOKEN, KEY_PREFIXES, Account, ApiKey
from relay_gateway.repositories.account_repository import AccountRepository
from relay_gateway.repositories.api_key_repository import ApiKeyRepository
from relay_gateway.services.rate_limit_service import (
    ACCOUNT_CALLS_PER_TOKEN,
    FAILED_LOGINS_PER_EMAIL,
    FAILED_REAUTH_PER_ACCOUNT,
    LOGIN_ATTEMPTS_PER_IP,
    SIGNUPS_PER_IP,
    RateLimitService,
)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
MIN_PASSWORD_LENGTH = 10
MAX_PASSWORD_LENGTH = 256
TOKEN_LIFETIME = timedelta(days=30)
TOKEN_IDLE = timedelta(days=14)
REAUTH_WINDOW = timedelta(minutes=15)
SIGNUP_MODES = ("open", "allowlist", "closed")


@dataclass(frozen=True)
class Principal:
    """The authenticated caller behind an API key."""

    account_id: str
    kind: str
    project_id: str | None
    key_id: str
    reauthenticated_at: datetime | None = None


def hash_key(key: str) -> str:
    # Keys are 256 bits of randomness, so a plain digest is enough (no brute-force to slow down).
    return hashlib.sha256(key.encode()).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, **_SCRYPT)
    return f"scrypt${salt.hex()}${digest.hex()}"


def password_matches(password: str, stored: str) -> bool:
    try:
        _scheme, salt_hex, digest_hex = stored.split("$")
        digest = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex), **_SCRYPT)
    except ValueError:
        return False
    return hmac.compare_digest(digest.hex(), digest_hex)


_DUMMY_HASH = hash_password("placeholder-password")


def signup_mode() -> str:
    mode = os.environ.get("RELAY_SIGNUP", "open").strip().lower()
    return mode if mode in SIGNUP_MODES else "closed"  # a typo must not open sign-up


def signup_allowed(email: str) -> bool:
    mode = signup_mode()
    if mode == "open":
        return True
    if mode == "closed":
        return False
    entries = [e.strip().lower() for e in os.environ.get("RELAY_SIGNUP_ALLOWLIST", "").split(",") if e.strip()]
    domain = email.rsplit("@", 1)[-1]
    return any(entry == email or (entry.startswith("@") and entry[1:] == domain) for entry in entries)


def email_verification_required() -> bool:
    return os.environ.get("RELAY_EMAIL_VERIFICATION", "required").lower() not in ("off", "0", "false")


def validate_password(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise BadRequest(f"password must be {MIN_PASSWORD_LENGTH}–{MAX_PASSWORD_LENGTH} characters")


class AuthService:
    def __init__(self, accounts: AccountRepository, keys: ApiKeyRepository, limits: RateLimitService) -> None:
        self._accounts = accounts
        self._keys = keys
        self._limits = limits

    # --- sign-up and sign-in -----------------------------------------------------------------

    async def register(self, email: str, password: str, *, ip: str | None = None) -> Account:
        email = email.strip().lower()
        if not _EMAIL.match(email):
            raise BadRequest("enter a valid email address")
        if not signup_allowed(email):
            raise Forbidden("sign-up is restricted on this Relay service; ask the operator for access")
        validate_password(password)
        await self._limits.take(SIGNUPS_PER_IP, ip)
        password_hash = hash_password(password)
        account = await self._accounts.create_account(email, password_hash)
        if account is None and email_verification_required():
            # Nobody ever proved this address, so whoever proves it now wins: an attacker who
            # registered someone else's email first cannot keep them out.
            account = await self._accounts.replace_unverified(email, password_hash)
        if account is None:
            raise Conflict("an account with this email already exists")
        if not email_verification_required():
            await self._accounts.mark_email_verified(account.id)
        return account

    async def sign_in(self, email: str, password: str, *, ip: str | None = None) -> Account:
        email = email.strip().lower()
        await self._limits.take(LOGIN_ATTEMPTS_PER_IP, ip)
        # Locked accounts are refused before the password is checked, so guessing stops.
        await self._limits.ensure_below(FAILED_LOGINS_PER_EMAIL, email)
        account = await self._accounts.account_by_email(email)
        # Hash even when the account is unknown so both failures take the same time.
        if not password_matches(password, account.password_hash if account else _DUMMY_HASH) or account is None:
            await self._limits.record_failure(FAILED_LOGINS_PER_EMAIL, email)
            raise Unauthorized("wrong email or password")
        await self._limits.clear(FAILED_LOGINS_PER_EMAIL, email)
        if email_verification_required() and account.email_verified_at is None:
            raise EmailNotVerified(
                f"confirm your email first — we sent a link to {account.email}", account=account
            )
        return account

    async def set_password(self, account_id: str, new_password: str) -> int:
        """Set a password without the old one (after a reset link); signs out every device."""
        validate_password(new_password)
        await self._accounts.set_password_hash(account_id, hash_password(new_password))
        return await self._keys.revoke_account_tokens(account_id)

    # --- keys and tokens ---------------------------------------------------------------------

    async def issue_key(
        self, *, account_id: str, kind: str, name: str, project_id: str | None = None
    ) -> tuple[ApiKey, str]:
        """Create a key and return it with its plain text — the only time the text exists."""
        plain = KEY_PREFIXES[kind] + secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + TOKEN_LIFETIME if kind == ACCOUNT_TOKEN else None
        key = await self._keys.create(
            account_id=account_id, project_id=project_id, kind=kind, name=name[:80] or kind,
            prefix=plain[:12], key_hash=hash_key(plain), expires_at=expires_at,
        )  # fmt: skip
        return key, plain

    async def authenticate(
        self, authorization: str | None, *, kinds: tuple[str, ...], ip: str | None = None
    ) -> Principal:
        """Resolve ``Authorization: Bearer <key>``; the key must be one of ``kinds``."""
        plain = (authorization or "").removeprefix("Bearer ").strip()
        if not plain:
            raise Unauthorized("missing API key (Authorization: Bearer <key>)")
        idle_cutoff = datetime.now(timezone.utc) - TOKEN_IDLE
        key = await self._keys.active_by_hash(hash_key(plain), ip=ip, idle_cutoff=idle_cutoff)
        if key is None:
            raise Unauthorized("invalid, expired or revoked API key")
        if key.kind not in kinds:
            raise Unauthorized(f"this endpoint needs a {' or '.join(kinds)} key")
        return Principal(key.account_id, key.kind, key.project_id, key.id, key.reauthenticated_at)

    async def account_principal(
        self, authorization: str | None, *, ip: str | None = None, sensitive: bool = False
    ) -> Principal:
        """The CLI caller. ``sensitive`` changes also need the password from the last few minutes."""
        principal = await self.authenticate(authorization, kinds=(ACCOUNT_TOKEN,), ip=ip)
        await self._limits.take(ACCOUNT_CALLS_PER_TOKEN, principal.key_id)
        if sensitive:
            proven = principal.reauthenticated_at
            if proven is None or datetime.now(timezone.utc) - proven > REAUTH_WINDOW:
                raise ReauthRequired("enter your password to confirm this change")
        return principal

    async def reauthenticate(self, principal: Principal, password: str) -> None:
        """Prove the password again for this device's token."""
        await self._limits.ensure_below(FAILED_REAUTH_PER_ACCOUNT, principal.account_id)
        account = await self._accounts.account(principal.account_id)
        if account is None or not password_matches(password, account.password_hash):
            await self._limits.record_failure(FAILED_REAUTH_PER_ACCOUNT, principal.account_id)
            raise Unauthorized("wrong password")
        await self._limits.clear(FAILED_REAUTH_PER_ACCOUNT, principal.account_id)
        await self._keys.mark_reauthenticated(principal.key_id)

    async def change_password(self, principal: Principal, current: str, new: str) -> int:
        """Set a new password; every other signed-in device is signed out. Returns how many."""
        await self.reauthenticate(principal, current)
        validate_password(new)
        if hmac.compare_digest(current, new):
            raise BadRequest("the new password must be different")
        await self._accounts.set_password_hash(principal.account_id, hash_password(new))
        return await self._keys.revoke_account_tokens(principal.account_id, keep=principal.key_id)

    # --- signed-in devices -------------------------------------------------------------------

    async def devices(self, principal: Principal) -> list[ApiKey]:
        return await self._keys.account_tokens(principal.account_id)

    async def sign_out_device(self, principal: Principal, key_id: str) -> None:
        if not await self._keys.revoke_account_token(key_id, account_id=principal.account_id):
            raise NotFound("no such signed-in device")

    async def sign_out(self, principal: Principal, *, everywhere: bool = False) -> int:
        if everywhere:
            return await self._keys.revoke_account_tokens(principal.account_id)
        return int(await self._keys.revoke_account_token(principal.key_id, account_id=principal.account_id))

    async def account(self, account_id: str) -> Account | None:
        return await self._accounts.account(account_id)
