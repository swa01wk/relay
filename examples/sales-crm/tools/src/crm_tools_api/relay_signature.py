"""Check that a request really came from Relay (copy this file into your own tools service).

Relay signs every call to a project's tools service with that project's signing secret
(``relay tools secret``): ``X-Relay-Signature: sha256=HMAC(secret, "<X-Relay-Timestamp>.<body>")``.
Verifying it means nobody else on the internet can call your tools, and an old request cannot
be replayed.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time

from fastapi import HTTPException, Request

MAX_AGE_SECONDS = 300


def signature_is_valid(secret: str, *, timestamp: str, signature: str, body: bytes, now: float | None = None) -> bool:
    try:
        age = abs((now if now is not None else time.time()) - int(timestamp))
    except ValueError:
        return False
    if age > MAX_AGE_SECONDS:
        return False
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"sha256={expected}")


async def require_relay_signature(request: Request) -> None:
    """FastAPI dependency. Enforced when ``RELAY_TOOLS_SIGNING_SECRET`` is set; a tools service
    on a private network next to the gateway may leave it unset."""
    secret = os.environ.get("RELAY_TOOLS_SIGNING_SECRET", "").strip()
    if not secret:
        return
    if not signature_is_valid(
        secret,
        timestamp=request.headers.get("X-Relay-Timestamp", ""),
        signature=request.headers.get("X-Relay-Signature", ""),
        body=await request.body(),
    ):
        raise HTTPException(status_code=401, detail="missing or invalid Relay signature")
