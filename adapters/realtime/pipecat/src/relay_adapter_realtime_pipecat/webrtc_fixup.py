"""Work around SmallWebRTC race: peer connects before transport ``setup()``."""

from __future__ import annotations

import asyncio
import logging
import time

from pipecat.transports.smallwebrtc.connection import SmallWebRTCTrack
from pipecat.transports.smallwebrtc.transport import SmallWebRTCClient

logger = logging.getLogger(__name__)

_original_setup = SmallWebRTCClient.setup
_original_connect = SmallWebRTCClient.connect
_original_idle_watcher = SmallWebRTCTrack._idle_watcher
_patched = False


async def _relay_bind_input_tracks_if_needed(self: SmallWebRTCClient) -> None:
    """Bind mic tracks once ``setup()`` has populated ``_params``.

    Pipecat's ``on_connected`` handler returns early when ``_params`` is unset, and
    ``connect()`` no-ops when the peer is already up — but ``is_connected()`` is
    also false until ``connect()`` runs, so a setup-only re-bind never fired.
    """
    if self._audio_input_track is not None or not self._params:
        return
    if self._webrtc_connection.audio_input_track() is None:
        logger.warning(
            "SmallWebRTC deferred bind: no audio input track yet pc_id=%s",
            getattr(self._webrtc_connection, "pc_id", "?"),
        )
        return
    logger.info(
        "SmallWebRTC binding input tracks after deferred setup pc_id=%s",
        getattr(self._webrtc_connection, "pc_id", "?"),
    )
    await self._handle_client_connected()


async def _relay_small_webrtc_setup(
    self: SmallWebRTCClient, _params, setup
) -> None:
    await _original_setup(self, _params, setup)
    await _relay_bind_input_tracks_if_needed(self)


async def _relay_small_webrtc_connect(self: SmallWebRTCClient) -> None:
    await _original_connect(self)
    await _relay_bind_input_tracks_if_needed(self)


async def _relay_idle_watcher(self: SmallWebRTCTrack) -> None:
    """Keep mic ingress open; Pipecat disables the audio receiver after 2s idle."""
    while self._receiver._enabled:
        await asyncio.sleep(self._idle_timeout)
        idle_duration = time.time() - self._last_recv_time
        if idle_duration >= self._idle_timeout:
            await self.discard_old_frames()
            if self._track.kind == "audio":
                logger.debug(
                    "SmallWebRTC audio idle %.2fs — discarding stale frames (receiver stays on)",
                    idle_duration,
                )
                self._last_recv_time = time.time()
            else:
                logger.debug(
                    "Disabling receiver for %s track after %.2fs idle",
                    self._track.kind,
                    idle_duration,
                )
                self._receiver._enabled = False


def apply_small_webrtc_audio_fixup() -> None:
    global _patched
    if _patched:
        return
    SmallWebRTCClient.setup = _relay_small_webrtc_setup  # type: ignore[method-assign]
    SmallWebRTCClient.connect = _relay_small_webrtc_connect  # type: ignore[method-assign]
    SmallWebRTCTrack._idle_watcher = _relay_idle_watcher  # type: ignore[method-assign]
    _patched = True
