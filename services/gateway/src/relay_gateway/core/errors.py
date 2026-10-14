"""Errors services raise; ``app.py`` turns them into HTTP responses (``{"detail": ...}``)."""

from __future__ import annotations


class GatewayError(Exception):
    status_code = 500

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class BadRequest(GatewayError):
    status_code = 400


class Unauthorized(GatewayError):
    status_code = 401


class NotFound(GatewayError):
    status_code = 404


class Disabled(NotFound):
    """The feature is switched off; indistinguishable from a missing route on purpose."""


class Unavailable(GatewayError):
    status_code = 503


class Forbidden(GatewayError):
    status_code = 403


class Conflict(GatewayError):
    status_code = 409


class TooManyRequests(GatewayError):
    status_code = 429

    def __init__(self, detail: str, *, retry_after: int) -> None:
        super().__init__(detail)
        self.retry_after = max(1, int(retry_after))


class ReauthRequired(GatewayError):
    """The account token is valid but too old for this change: the person must enter their
    password again (``POST /v1/auth/reauth``). Clients detect it by the ``X-Relay-Reauth`` header."""

    status_code = 403


class EmailNotVerified(Forbidden):
    """Right password, but the address was never confirmed."""

    def __init__(self, detail: str, *, account: object) -> None:
        super().__init__(detail)
        self.account = account

