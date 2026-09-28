"""Speech pipeline ports.

POC STT: ``adapters/speech/deepgram/``
POC TTS: ``adapters/speech/`` (provider-specific)
Turn/VAD: Pipecat or custom endpointing behind ``TurnDetector``.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from typing import Any


class SpeechToTextProvider(ABC):
    @abstractmethod
    async def stream_transcription(
        self, session_id: str, audio: AsyncIterator[bytes]
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield partial/final transcript dicts."""

    @abstractmethod
    async def close(self, session_id: str) -> None:
        ...


class TextToSpeechProvider(ABC):
    @abstractmethod
    async def synthesize_stream(
        self, session_id: str, text: AsyncIterator[str]
    ) -> AsyncIterator[bytes]:
        """Stream audio frames for spoken output."""

    @abstractmethod
    async def cancel(self, session_id: str) -> None:
        ...


class TurnDetector(ABC):
    @abstractmethod
    async def on_audio_frame(self, session_id: str, frame: bytes) -> dict[str, Any] | None:
        """Optional turn boundary signal (e.g. speech start/end)."""
