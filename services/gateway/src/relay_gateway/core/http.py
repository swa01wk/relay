"""Request details controllers pass down to services."""

from __future__ import annotations

import os

from fastapi import Request, WebSocket


def client_ip(request: Request | WebSocket) -> str | None:
    """The caller's address. ``X-Forwarded-For`` is only believed behind a proxy you run
    (``RELAY_TRUST_PROXY_HEADERS=1``); otherwise any client could pick its own address and
    escape per-address rate limits."""
    if os.environ.get("RELAY_TRUST_PROXY_HEADERS", "").lower() in ("1", "true", "yes"):
        forwarded = request.headers.get("x-forwarded-for", "")
        # The proxy appends the address it saw last, so the last entry is the one it vouches for.
        hops = [hop.strip() for hop in forwarded.split(",") if hop.strip()]
        if hops:
            return hops[-1][:64]
    return request.client.host if request.client else None


SESSION_PROTOCOL = "relay.v1"
_TOKEN_PROTOCOL_PREFIX = "relay.token."


def session_token(request: Request | WebSocket, query_token: str | None = None) -> str | None:
    """A session token from ``Authorization: Bearer`` (HTTP) or the ``relay.token.<token>``
    WebSocket subprotocol (browsers cannot set WebSocket headers). ``?token=`` is still read
    for SDK versions that put it in the URL, where it can end up in proxy logs and history."""
    authorization = request.headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip() or None
    for protocol in request.headers.get("sec-websocket-protocol", "").split(","):
        protocol = protocol.strip()
        if protocol.startswith(_TOKEN_PROTOCOL_PREFIX):
            return protocol[len(_TOKEN_PROTOCOL_PREFIX):] or None
    return query_token or None


def offered_session_protocol(websocket: WebSocket) -> str | None:
    """The subprotocol to accept: a browser that offered protocols closes the socket unless
    the server picks one of them."""
    offered = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",")]
    return SESSION_PROTOCOL if SESSION_PROTOCOL in offered else None

