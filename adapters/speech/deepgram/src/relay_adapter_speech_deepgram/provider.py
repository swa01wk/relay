"""Deepgram live STT — Pipecat service factory + port wrapper."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from typing import Any

from pipecat.services.deepgram.stt import DeepgramSTTService
from pipecat.transcriptions.language import Language

from relay_runtime.ports.speech import SpeechToTextProvider

logger = logging.getLogger(__name__)


def _resolve_listen_v1_model() -> str:
    """Pipecat Deepgram adapter uses ``listen.v1`` — Flux models need listen v2."""
    model = os.environ.get("DEEPGRAM_STT_MODEL", "nova-3-general").strip()
    if "flux" in model.lower():
        logger.warning(
            "DEEPGRAM_STT_MODEL=%r is Flux (listen v2); Pipecat uses listen v1 — using nova-3-general",
            model,
        )
        return "nova-3-general"
    return model


def build_pipecat_stt_service() -> DeepgramSTTService | None:
    api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        return None
    model = _resolve_listen_v1_model()
    endpointing_ms = int(os.environ.get("RELAY_DEEPGRAM_ENDPOINTING_MS", "500"))
    return DeepgramSTTService(
        api_key=api_key,
        settings=DeepgramSTTService.Settings(
            model=model,
            language=Language.EN,
            interim_results=True,
            punctuate=True,
            smart_format=True,
            endpointing=endpointing_ms,
        ),
    )


class DeepgramSpeechToTextProvider(SpeechToTextProvider):
    """Port adapter — production path uses ``build_pipecat_stt_service`` in the media pipeline."""

    async def stream_transcription(
        self, session_id: str, audio: AsyncIterator[bytes]
    ) -> AsyncIterator[dict[str, Any]]:
        del session_id
        async for chunk in audio:
            if chunk:
                yield {"text": "", "is_final": False, "bytes": len(chunk)}
        yield {"text": "", "is_final": True}

    async def close(self, session_id: str) -> None:
        del session_id
