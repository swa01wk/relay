"""SmallWebRTC deferred track binding."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from relay_adapter_realtime_pipecat import webrtc_fixup


@pytest.mark.asyncio
async def test_bind_after_setup_when_peer_up_before_params(monkeypatch):
    client = MagicMock()
    client._audio_input_track = None
    client._params = object()
    client._webrtc_connection = MagicMock()
    client._webrtc_connection.audio_input_track.return_value = object()
    client._webrtc_connection.is_connected.return_value = False
    client._webrtc_connection.pc_id = "pc-test"
    client._handle_client_connected = AsyncMock()

    async def fake_setup(_self, _params, setup):
        client._params = _params

    monkeypatch.setattr(webrtc_fixup, "_original_setup", fake_setup)

    await webrtc_fixup._relay_small_webrtc_setup(client, object(), object())

    client._handle_client_connected.assert_awaited_once()


@pytest.mark.asyncio
async def test_bind_after_connect_when_already_connected(monkeypatch):
    client = MagicMock()
    client._audio_input_track = None
    client._params = object()
    client._webrtc_connection = MagicMock()
    client._webrtc_connection.audio_input_track.return_value = object()
    client._handle_client_connected = AsyncMock()

    async def fake_connect(_self):
        return None

    monkeypatch.setattr(webrtc_fixup, "_original_connect", fake_connect)

    await webrtc_fixup._relay_small_webrtc_connect(client)

    client._handle_client_connected.assert_awaited_once()
