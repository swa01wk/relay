"""HTTP-backed ToolExecutor — tool URLs configured per deployment (no domain in runtime)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from relay_runtime.failure_injection import inject_tool_timeout_seconds
from relay_runtime.ports.tools import ToolExecutor


def signature_headers(secret: str, body: bytes, *, now: float | None = None) -> dict[str, str]:
    """Headers proving a request came from Relay: HMAC-SHA256 over ``"<timestamp>.<body>"``.

    The tools service recomputes the signature with the shared secret and rejects stale
    timestamps (replay protection).
    """
    timestamp = str(int(now if now is not None else time.time()))
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    return {"X-Relay-Timestamp": timestamp, "X-Relay-Signature": f"sha256={digest}"}


def signed_headers(
    secret: str,
    body: bytes,
    *,
    operation: str,
    session_id: str = "",
    user: str = "",
    now: float | None = None,
) -> dict[str, str]:
    """Both signatures for one request.

    ``X-Relay-Signature`` (v1) covers the timestamp and body only and is kept for tools services
    that already check it. ``X-Relay-Signature-V2`` also covers what is being called, for which
    session and for which end user, so none of them can be swapped in a captured request::

        relay-v2\n<timestamp>\n<operation>\n<X-Relay-Session>\n<X-Relay-User>\n<body>

    ``operation`` is ``tools.list`` for discovery or ``tools.call:<name>`` for a tool call. Headers
    that are absent count as empty strings; ``X-Relay-User`` is signed exactly as sent.
    """
    headers = signature_headers(secret, body, now=now)
    signed = "\n".join(("relay-v2", headers["X-Relay-Timestamp"], operation, session_id, user)).encode()
    digest = hmac.new(secret.encode(), signed + b"\n" + body, hashlib.sha256).hexdigest()
    headers["X-Relay-Signature-V2"] = f"sha256={digest}"
    return headers


# (host, port) → the IP address to connect to; raise to refuse the destination.
AddressGuard = Callable[[str, int], Awaitable[str]]


async def pinned_target(url: str, guard: AddressGuard) -> tuple[str, dict[str, str], dict[str, Any]]:
    """Resolve and check the destination *now*, then connect to exactly that address.

    Returns the URL rewritten to the checked IP, the ``Host`` header for the real name, and
    the TLS ``sni_hostname`` so the certificate is still verified against the real name. A DNS
    answer that changes between check and connect (DNS rebinding) cannot redirect the call.

    Use one HTTP client per tools host: connection pools are keyed by address, so a client
    shared across hosts could reuse a connection that was verified for a different name.
    """
    parsed = httpx.URL(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    address = await guard(parsed.host, port)
    pinned = parsed.copy_with(host=address)
    extensions: dict[str, Any] = {"sni_hostname": parsed.host} if parsed.scheme == "https" else {}
    return str(pinned), {"Host": parsed.netloc.decode("ascii")}, extensions


def end_user_header(user: dict[str, Any] | None) -> str:
    """The ``X-Relay-User`` value: compact JSON, ASCII only, stable key order (or empty)."""
    if not user:
        return ""
    return json.dumps(user, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


class HttpToolExecutor(ToolExecutor):
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 30.0,
        signing_secret: str | None = None,
        headers_for_tool: Callable[[str], dict[str, str]] | None = None,
        user_for_session: Callable[[str], dict[str, Any] | None] | None = None,
        address_guard: AddressGuard | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        # When set, every call carries X-Relay-Timestamp / X-Relay-Signature.
        self._signing_secret = signing_secret
        # Extra headers a deployment adds for a tool (e.g. a commit token its tools service expects).
        self._headers_for_tool = headers_for_tool
        # The end user a session was started for (set by the app's server), sent on every call.
        self._user_for_session = user_for_session
        # When set, every call re-checks where the tools host points and connects only there.
        self._address_guard = address_guard
        self._transport = transport
        # Pooled keep-alive client; parallel tool calls share connections.
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            # Redirects are not followed: a tools URL must not bounce Relay to another host.
            self._client = httpx.AsyncClient(timeout=self._timeout, transport=self._transport)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def execute(
        self,
        session_id: str,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        headers: dict[str, str] = {"Content-Type": "application/json", "X-Relay-Session": session_id}
        user = end_user_header(self._user_for_session(session_id) if self._user_for_session else None)
        if user:
            headers["X-Relay-User"] = user
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if self._headers_for_tool is not None:
            headers.update(self._headers_for_tool(tool_name))
        timeout = inject_tool_timeout_seconds(self._timeout)
        body = json.dumps(arguments).encode()
        if self._signing_secret:
            headers.update(
                signed_headers(
                    self._signing_secret, body, operation=f"tools.call:{tool_name}", session_id=session_id, user=user
                )
            )
        url, extensions = f"{self._base_url}/tools/{tool_name}", {}
        if self._address_guard is not None:
            url, host_header, extensions = await pinned_target(url, self._address_guard)
            headers.update(host_header)
        response = await self._http().post(url, content=body, headers=headers, timeout=timeout, extensions=extensions)
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict):
            return body
        return {"result": body}
