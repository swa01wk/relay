"""Operator-token checks shared by the metrics and admin services."""

from __future__ import annotations

import hmac

from relay_gateway.core.errors import Unauthorized


def require_bearer(authorization: str | None, expected: str, *, detail: str) -> None:
    """Compare an ``Authorization: Bearer <token>`` header with ``expected`` in constant time."""
    supplied = (authorization or "").removeprefix("Bearer ").strip()
    if not hmac.compare_digest(supplied.encode(), expected.encode()):
        raise Unauthorized(detail)
