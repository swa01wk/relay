"""ICE servers for browsers: STUN always, TURN with short-lived credentials when configured."""

from __future__ import annotations

import base64
import hashlib
import hmac

import pytest
from httpx import ASGITransport, AsyncClient

from relay_gateway.app import create_app
from relay_gateway.core import container as deps
from relay_gateway.services.realtime_service import IceConfig


def test_ice_config_reads_env_and_signs_turn_credentials():
    config = IceConfig.from_env(
        {
            "RELAY_ICE_STUN_URL": "stun:stun.example:3478",
            "RELAY_TURN_URLS": "turn:turn.example:3478?transport=udp, turn:turn.example:3478?transport=tcp",
            "RELAY_TURN_SECRET": "s3cret",
            "RELAY_TURN_TTL_SECONDS": "600",
        }
    )
    stun, turn = config.servers("sess-1", now=1_000)
    assert stun == {"urls": ["stun:stun.example:3478"]}
    assert turn["urls"] == ["turn:turn.example:3478?transport=udp", "turn:turn.example:3478?transport=tcp"]
    assert turn["username"] == "1600:sess-1"
    expected = base64.b64encode(hmac.new(b"s3cret", b"1600:sess-1", hashlib.sha1).digest()).decode()
    assert turn["credential"] == expected


def test_ice_config_without_turn_secret_offers_stun_only():
    config = IceConfig.from_env({"RELAY_TURN_URLS": "turn:turn.example:3478"})
    assert config.servers("sess-1") == [{"urls": ["stun:stun.l.google.com:19302"]}]
    assert IceConfig.from_env({"RELAY_ICE_STUN_URL": ""}).servers("sess-1") == []


@pytest.mark.asyncio
async def test_ice_servers_endpoint_needs_the_session_token(monkeypatch):
    monkeypatch.setattr(
        deps.realtime_service,
        "_ice",
        IceConfig(stun_urls=("stun:stun.example:3478",), turn_urls=("turn:turn.example:3478",), turn_secret="k"),
    )
    transport = ASGITransport(app=create_app())
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        created = (await client.post("/dev/sessions", json={"project_id": "p", "agent_id": "agent-ref"})).json()
        session_id, token = created["session_id"], created["dev_token"]
        url = f"/sessions/{session_id}/webrtc/ice-servers"

        assert (await client.get(url)).status_code == 401
        assert (await client.get(url, headers={"Authorization": "Bearer wrong"})).status_code == 401
        # The token is not accepted from the URL on this new endpoint.
        assert (await client.get(url, params={"token": token})).status_code == 401

        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ttl_seconds"] == 3600
        stun, turn = body["ice_servers"]
        assert stun == {"urls": ["stun:stun.example:3478"]}
        assert turn["username"].endswith(f":{session_id}")
        assert turn["credential"]
