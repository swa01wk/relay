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
