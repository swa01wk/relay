"""HTTP-backed ToolExecutor — tool URLs configured per deployment (no domain in runtime)."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Callable
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


class HttpToolExecutor(ToolExecutor):
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 30.0,
        signing_secret: str | None = None,
        headers_for_tool: Callable[[str], dict[str, str]] | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        # When set, every call carries X-Relay-Timestamp / X-Relay-Signature.
        self._signing_secret = signing_secret
        # Extra headers a deployment adds for a tool (e.g. a commit token its tools service expects).
        self._headers_for_tool = headers_for_tool
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
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        if self._headers_for_tool is not None:
            headers.update(self._headers_for_tool(tool_name))
        timeout = inject_tool_timeout_seconds(self._timeout)
        body = json.dumps(arguments).encode()
        if self._signing_secret:
            headers.update(signature_headers(self._signing_secret, body))
        response = await self._http().post(
            f"{self._base_url}/tools/{tool_name}",
            content=body,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        body = response.json()
        if isinstance(body, dict):
            return body
        return {"result": body}
