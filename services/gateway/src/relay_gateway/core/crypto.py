"""Encryption for secrets customers hand us (model API keys, tools signing secrets).

Values are encrypted with a key derived from ``RELAY_SECRETS_KEY`` before they reach a
repository, so a database dump alone does not reveal them. Losing or changing that key makes
stored secrets unreadable (customers set them again).
"""

from __future__ import annotations

import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken

from relay_gateway.core.errors import Unavailable


class SecretBox:
    def __init__(self, passphrase: str | None = None) -> None:
        self._passphrase = passphrase

    def _fernet(self) -> Fernet:
        passphrase = self._passphrase or os.environ.get("RELAY_SECRETS_KEY", "").strip()
        if len(passphrase) < 24:
            raise Unavailable("storing secrets is not configured on this gateway (RELAY_SECRETS_KEY)")
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(passphrase.encode()).digest()))

    def encrypt(self, value: str) -> str:
        return self._fernet().encrypt(value.encode()).decode()

    def decrypt(self, ciphertext: str) -> str | None:
        """``None`` when the value was encrypted with a different key."""
        try:
            return self._fernet().decrypt(ciphertext.encode()).decode()
        except InvalidToken:
            return None
