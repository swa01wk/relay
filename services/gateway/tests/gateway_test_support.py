"""Helpers shared by gateway tests: fakes for customers' tools services and the model API,
and a one-turn WebSocket driver. (A uniquely named module, so it cannot clash with another
test folder's ``conftest``.)"""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from relay_runtime.ports.model import ModelProvider


class FakeTenantWorld:
    """Stands in for customers' tools services and for the model API.

    ``requests`` records every call a tools service received; ``model_keys`` every API key a
    model provider was built with.
    """

    TOOLS = [
        {"name": "list_orders", "description": "List orders", "classification": "read_only",
         "input_schema": {"type": "object", "properties": {}}},
    ]

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.model_keys: list[str] = []
        self.down_hosts: set[str] = set()

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.host in self.down_hosts:
            return httpx.Response(503)
        if request.url.path.endswith("/tools") and request.method == "GET":
            return httpx.Response(200, json={"tools": self.TOOLS})
        return httpx.Response(200, json={"orders": [{"id": "ORD-1"}], "served_by": request.url.host})

    def tool_calls(self, host: str) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.host == host and r.method == "POST"]

    @staticmethod
    def signature_is_valid(request: httpx.Request, secret: str) -> bool:
        timestamp = request.headers.get("X-Relay-Timestamp", "")
        expected = hmac.new(secret.encode(), timestamp.encode() + b"." + request.content, hashlib.sha256).hexdigest()
        return hmac.compare_digest(request.headers.get("X-Relay-Signature", ""), f"sha256={expected}")

    @staticmethod
    def signature_v2_is_valid(request: httpx.Request, secret: str, *, operation: str | None = None) -> bool:
        """How a tools service checks X-Relay-Signature-V2 (operation from its own route)."""
        if operation is None:
            name = request.url.path.rsplit("/", 1)[-1]
            operation = "tools.list" if request.method == "GET" else f"tools.call:{name}"
        signed = "\n".join(
            (
                "relay-v2",
                request.headers.get("X-Relay-Timestamp", ""),
                operation,
                request.headers.get("X-Relay-Session", ""),
                request.headers.get("X-Relay-User", ""),
            )
        ).encode()
        expected = hmac.new(secret.encode(), signed + b"\n" + request.content, hashlib.sha256).hexdigest()
        return hmac.compare_digest(request.headers.get("X-Relay-Signature-V2", ""), f"sha256={expected}")

    def provider(self, api_key: str, model: str | None) -> ModelProvider:
        self.model_keys.append(api_key)

        class Scripted(ModelProvider):
            async def stream_completion(self, session_id, *, messages, tools=None) -> AsyncIterator[dict[str, Any]]:
                del session_id, tools
                if not [m for m in messages if m.get("role") == "tool"]:
                    yield {"type": "tool_calls", "calls": [{"id": "c1", "name": "list_orders", "arguments": "{}"}]}
                else:
                    yield {"type": "token", "text": "You have one order."}

            async def cancel(self, session_id: str) -> None:
                del session_id

            async def aclose(self) -> None:
                pass

        return Scripted()



def run_turn(client, session: dict, text: str) -> list[dict]:
    """Send one user message over the session WebSocket and collect events until the turn ends."""
    events: list[dict] = []
    with client.websocket_connect(f"/ws/sessions/{session['session_id']}?token={session['token']}") as ws:
        ws.send_text(json.dumps({"type": "USER_TEXT", "text": text}))
        for _ in range(200):
            event = json.loads(ws.receive_text())
            events.append(event)
            if event.get("type") == "TURN_COMPLETED":
                break
    return events
