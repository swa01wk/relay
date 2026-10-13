"""Accounts, passwords and API keys: who is calling, and what they may do."""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

from relay_gateway.core.errors import BadRequest, Conflict, Unauthorized
from relay_gateway.repositories.account_repository import AccountRepository
from relay_gateway.repositories.api_key_repository import ApiKeyRepository
from relay_gateway.models import KEY_PREFIXES, Account, ApiKey

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1, "dklen": 32}
MIN_PASSWORD_LENGTH = 10


@dataclass(frozen=True)
class Principal:
    """The authenticated caller behind an API key."""

    account_id: str
    kind: str
    project_id: str | None
    key_id: str


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


class AuthService:
    def __init__(self, accounts: AccountRepository, keys: ApiKeyRepository) -> None:
        self._accounts = accounts
        self._keys = keys

    async def register(self, email: str, password: str) -> Account:
        email = email.strip().lower()
        if not _EMAIL.match(email):
            raise BadRequest("enter a valid email address")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise BadRequest(f"password must be at least {MIN_PASSWORD_LENGTH} characters")
        account = await self._accounts.create_account(email, hash_password(password))
        if account is None:
            raise Conflict("an account with this email already exists")
        return account

    async def sign_in(self, email: str, password: str) -> Account:
        account = await self._accounts.account_by_email(email.strip().lower())
        # Hash even when the account is unknown so both failures take the same time.
        stored = account.password_hash if account else hash_password("placeholder-password")
        if not password_matches(password, stored) or account is None:
            raise Unauthorized("wrong email or password")
        return account

    async def issue_key(self, *, account_id: str, kind: str, name: str, project_id: str | None = None) -> tuple[ApiKey, str]:
        """Create a key and return it with its plain text — the only time the text exists."""
        plain = KEY_PREFIXES[kind] + secrets.token_urlsafe(32)
        key = await self._keys.create(
            account_id=account_id, project_id=project_id, kind=kind, name=name[:80] or kind,
            prefix=plain[:12], key_hash=hash_key(plain),
        )  # fmt: skip
        return key, plain

    async def authenticate(self, authorization: str | None, *, kinds: tuple[str, ...]) -> Principal:
        """Resolve ``Authorization: Bearer <key>``; the key must be one of ``kinds``."""
        plain = (authorization or "").removeprefix("Bearer ").strip()
        if not plain:
            raise Unauthorized("missing API key (Authorization: Bearer <key>)")
        key = await self._keys.active_by_hash(hash_key(plain))
        if key is None:
            raise Unauthorized("invalid or revoked API key")
        if key.kind not in kinds:
            raise Unauthorized(f"this endpoint needs a {' or '.join(kinds)} key")
        return Principal(key.account_id, key.kind, key.project_id, key.id)

    async def revoke_presented_key(self, authorization: str | None) -> None:
        plain = (authorization or "").removeprefix("Bearer ").strip()
        if plain:
            await self._keys.revoke_by_hash(hash_key(plain))

    async def account(self, account_id: str) -> Account | None:
        return await self._accounts.account(account_id)
