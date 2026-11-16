"""Check that a request really came from Relay, and read which user it is for (copy this file
into your own tools service).

Relay signs every call with your project's signing secret (``relay tools secret``). Prefer
``X-Relay-Signature-V2``: it covers the timestamp, which tool is called, the session, the end
user and the body, so none of them can be swapped in a captured request::

    relay-v2\\n<X-Relay-Timestamp>\\n<operation>\\n<X-Relay-Session>\\n<X-Relay-User>\\n<body>

``operation`` is ``tools.list`` for ``GET /tools`` and ``tools.call:<name>`` for
``POST /tools/<name>`` — derive it from your own route, never from a header. ``X-Relay-User`` is
the user your server started the session for (JSON ``{"id", "attributes"?}``), absent otherwise.
The older ``X-Relay-Signature`` (timestamp + body only) is still sent.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any

from fastapi import HTTPException, Request

MAX_AGE_SECONDS = 300


def _fresh(timestamp: str, now: float | None) -> bool:
    try:
        return abs((now if now is not None else time.time()) - int(timestamp)) <= MAX_AGE_SECONDS
    except ValueError:
        return False


def signature_is_valid(secret: str, *, timestamp: str, signature: str, body: bytes, now: float | None = None) -> bool:
    """v1: timestamp + body."""
    if not _fresh(timestamp, now):
        return False
    expected = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"sha256={expected}")


def signature_v2_is_valid(
    secret: str,
    *,
    timestamp: str,
    operation: str,
    session: str,
    user: str,
    signature: str,
    body: bytes,
    now: float | None = None,
) -> bool:
    """v2: timestamp + operation + session + user + body."""
    if not _fresh(timestamp, now):
        return False
    signed = "\n".join(("relay-v2", timestamp, operation, session, user)).encode() + b"\n" + body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"sha256={expected}")


def _operation(request: Request) -> str:
    name = request.path_params.get("name")
    return f"tools.call:{name}" if name else "tools.list"


async def require_relay_signature(request: Request) -> None:
    """FastAPI dependency. Enforced when ``RELAY_TOOLS_SIGNING_SECRET`` is set; a tools service
    on a private network next to the gateway may leave it unset."""
    secret = os.environ.get("RELAY_TOOLS_SIGNING_SECRET", "").strip()
    if not secret:
        return
    headers, body = request.headers, await request.body()
    valid = signature_v2_is_valid(
        secret,
        timestamp=headers.get("X-Relay-Timestamp", ""),
        operation=_operation(request),
        session=headers.get("X-Relay-Session", ""),
        user=headers.get("X-Relay-User", ""),
        signature=headers.get("X-Relay-Signature-V2", ""),
        body=body,
    )
    if not valid:
        raise HTTPException(status_code=401, detail="missing or invalid Relay signature")


def relay_user(request: Request) -> dict[str, Any] | None:
    """The end user a verified call is for (``{"id", "attributes"?}``), or ``None``. Only
    meaningful after ``require_relay_signature`` passed — then it cannot have been changed."""
    raw = request.headers.get("X-Relay-User", "")
    if not raw:
        return None
    try:
        user = json.loads(raw)
    except ValueError:
        return None
    return user if isinstance(user, dict) and user.get("id") else None
