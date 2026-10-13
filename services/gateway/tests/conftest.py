"""Gateway test defaults: no agent manifests, and a throwaway CRM database."""

from __future__ import annotations

import os
import tempfile

# Startup must not reach real tools services.
os.environ.setdefault("RELAY_AGENTS_DIR", "/nonexistent-relay-agents")
# Tests start sessions without an API key.
os.environ.setdefault("RELAY_DEV_SESSIONS", "1")
# The integration tests exercise the mortgage example as the gateway's default agent.
os.environ.setdefault("RELAY_EXAMPLE_MORTGAGE", "1")
os.environ.setdefault("RELAY_SECRETS_KEY", "test-only-secrets-key-0123456789")
# CRM tools write to SQLite; tests must never touch a real database file.
os.environ["CRM_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="relay-crm-test-"), "crm.db")

import hashlib  # noqa: E402
import hmac  # noqa: E402
import json  # noqa: E402
from collections.abc import AsyncIterator  # noqa: E402
from typing import Any  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402

from relay_runtime.ports.model import ModelProvider  # noqa: E402


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


@pytest.fixture
def tenant_world(monkeypatch):
    """Route project agents' tool calls and model calls to in-process fakes."""
    from relay_gateway.core import container

    world = FakeTenantWorld()
    service = container.project_agent_service
    monkeypatch.setattr(service, "http_transport", httpx.MockTransport(world.handle))
    monkeypatch.setattr(service, "_model_provider_factory", world.provider)
    monkeypatch.setenv("RELAY_ALLOW_PRIVATE_TOOLS_URLS", "1")  # *.test hosts do not resolve
    return world


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
