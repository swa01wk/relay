"""Deepgram Flux Speak v2 + deterministic mock TTS behind ``TextToSpeechProvider``."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
from collections.abc import AsyncIterator
from math import sin
from typing import Any
from urllib.parse import urlencode

import websockets

from relay_runtime.ports.speech import TextToSpeechProvider

logger = logging.getLogger(__name__)


def _tts_sample_rate() -> int:
    return int(os.environ.get("DEEPGRAM_TTS_SAMPLE_RATE", "24000"))


def _tts_model() -> str:
    return os.environ.get("DEEPGRAM_TTS_MODEL", "flux-haley-en").strip()


def _tts_encoding() -> str:
    return os.environ.get("DEEPGRAM_TTS_ENCODING", "linear16").strip()


class MockTextToSpeechProvider(TextToSpeechProvider):
    """Low-latency PCM tone chunks for CI and local pytest."""

    def __init__(self, *, sample_rate: int | None = None, chunk_ms: int = 20) -> None:
        self._sample_rate = sample_rate or _tts_sample_rate()
        self._chunk_ms = chunk_ms
        self._cancelled: set[str] = set()

    async def synthesize_stream(
        self, session_id: str, text: AsyncIterator[str]
    ) -> AsyncIterator[bytes]:
        # New utterance — do not inherit cancel from a prior barge-in on this session.
        self._cancelled.discard(session_id)
        samples_per_chunk = max(1, int(self._sample_rate * self._chunk_ms / 1000))
        byte_count = samples_per_chunk * 2
        phase = 0.0
        chunks = 0
        async for _token in text:
            if session_id in self._cancelled:
                break
            chunks += 1
            buf = bytearray()
            for _ in range(samples_per_chunk):
                value = int(8000 * sin(phase))
                phase += 0.05
                buf.extend(struct.pack("<h", value))
            yield bytes(buf[:byte_count])
            await asyncio.sleep(0)
        if chunks == 0 and session_id not in self._cancelled:
            yield b"\x00\x00" * samples_per_chunk

    async def cancel(self, session_id: str) -> None:
        self._cancelled.add(session_id)


class DeepgramTextToSpeechProvider(TextToSpeechProvider):
    """WebSocket ``/v2/speak`` — streams Speak messages, yields linear16 PCM."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        sample_rate: int | None = None,
        encoding: str | None = None,
    ) -> None:
        self._api_key = (api_key or os.environ.get("DEEPGRAM_API_KEY", "")).strip()
        self._model = model or _tts_model()
        self._sample_rate = sample_rate or _tts_sample_rate()
        self._encoding = encoding or _tts_encoding()
        self._cancelled: set[str] = set()
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, session_id: str) -> asyncio.Lock:
        return self._locks.setdefault(session_id, asyncio.Lock())

    def _ws_url(self) -> str:
        query = urlencode(
            {
                "model": self._model,
                "encoding": self._encoding,
                "sample_rate": str(self._sample_rate),
            }
        )
        return f"wss://api.deepgram.com/v2/speak?{query}"

    async def synthesize_stream(
        self, session_id: str, text: AsyncIterator[str]
    ) -> AsyncIterator[bytes]:
        if not self._api_key:
            async for chunk in MockTextToSpeechProvider(sample_rate=self._sample_rate).synthesize_stream(
                session_id, text
            ):
                yield chunk
            return

        async with self._lock_for(session_id):
            # Prior interrupt called cancel(); each new stream is a fresh speak request.
            self._cancelled.discard(session_id)
            headers = {"Authorization": f"Token {self._api_key}"}
            try:
                async with websockets.connect(
                    self._ws_url(),
                    additional_headers=headers,
                    open_timeout=15,
                ) as ws:
                    async for token in text:
                        if session_id in self._cancelled:
                            break
                        if not token.strip():
                            continue
                        await ws.send(json.dumps({"type": "Speak", "text": token}))
                    if session_id not in self._cancelled:
                        await ws.send(json.dumps({"type": "Flush"}))

                    while True:
                        if session_id in self._cancelled:
                            break
                        try:
                            message = await asyncio.wait_for(ws.recv(), timeout=45.0)
                        except asyncio.TimeoutError:
                            logger.warning(
                                "deepgram tts recv timeout session_id=%s", session_id
                            )
                            break
                        if isinstance(message, bytes):
                            if message:
                                yield message
                            continue
                        try:
                            payload = json.loads(message)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(payload, dict):
                            continue
                        msg_type = payload.get("type")
                        if msg_type == "Connected":
                            logger.debug(
                                "deepgram tts connected session_id=%s model=%s",
                                session_id,
                                payload.get("model_name"),
                            )
                        elif msg_type == "Error":
                            logger.error(
                                "deepgram tts error session_id=%s payload=%s",
                                session_id,
                                payload,
                            )
                            break
                        elif msg_type == "SpeechMetadata":
                            break
                        elif msg_type == "Close":
                            break
            except Exception:
                logger.exception("deepgram tts failed session_id=%s", session_id)

    async def cancel(self, session_id: str) -> None:
        self._cancelled.add(session_id)


def build_text_to_speech_provider() -> TextToSpeechProvider:
    api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if api_key:
        return DeepgramTextToSpeechProvider(api_key=api_key)
    return MockTextToSpeechProvider()
