"""Deepgram live STT — Pipecat service factory + port wrapper."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator, Iterable
from typing import Any

from pipecat.services.deepgram.stt import DeepgramSTTService

from relay_runtime.ports.speech import SpeechToTextProvider

logger = logging.getLogger(__name__)


# Deepgram accepts up to 100 key terms per request; longer phrases are rejected or ignored.
MAX_KEYTERMS = 100
MAX_KEYTERM_CHARS = 50


def _resolve_listen_v1_model() -> str:
    """Pipecat's Deepgram service uses ``listen`` v1; Flux models only exist on v2."""
    model = os.environ.get("DEEPGRAM_STT_MODEL", "nova-3-general").strip()
    if "flux" in model.lower():
        logger.warning(
            "DEEPGRAM_STT_MODEL=%r is a Flux model, which this gateway cannot use for speech "
            "recognition; using nova-3-general instead (set DEEPGRAM_STT_MODEL to a nova model)",
            model,
        )
        return "nova-3-general"
    return model


def stt_language() -> str:
    """``DEEPGRAM_STT_LANGUAGE``: e.g. ``en``, ``en-US``, ``en-IN`` (Indian English) or ``multi``
    (code-switching, e.g. Hindi + English). Default ``en``."""
    return os.environ.get("DEEPGRAM_STT_LANGUAGE", "").strip() or "en"


def clean_keyterms(terms: Iterable[str]) -> list[str]:
    """Trimmed, de-duplicated (case-insensitive), at most ``MAX_KEYTERMS`` of ``MAX_KEYTERM_CHARS``."""
    seen: set[str] = set()
    out: list[str] = []
    for term in terms:
        text = " ".join(str(term).split())[:MAX_KEYTERM_CHARS].strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append(text)
        if len(out) == MAX_KEYTERMS:
            break
    return out


def stt_keyterms(agent_keyterms: Iterable[str] = ()) -> list[str]:
    """The agent's key terms first, then the gateway-wide ``DEEPGRAM_STT_KEYTERMS`` (comma-separated)."""
    gateway = [t for t in os.environ.get("DEEPGRAM_STT_KEYTERMS", "").split(",") if t.strip()]
    return clean_keyterms([*agent_keyterms, *gateway])


def stt_settings(*, keyterms: Iterable[str] = ()) -> DeepgramSTTService.Settings:
    model = _resolve_listen_v1_model()
    terms = stt_keyterms(keyterms)
    extra: dict[str, Any] = {}
    if terms:
        if model.startswith("nova-3"):
            extra["keyterm"] = terms
        else:
            logger.warning("speech key terms need a nova-3 model; ignored for DEEPGRAM_STT_MODEL=%r", model)
    return DeepgramSTTService.Settings(
        model=model,
        language=stt_language(),
        interim_results=True,
        punctuate=True,
        smart_format=True,
        endpointing=int(os.environ.get("RELAY_DEEPGRAM_ENDPOINTING_MS", "500")),
        **extra,
    )


def build_pipecat_stt_service(*, keyterms: Iterable[str] = ()) -> DeepgramSTTService | None:
    """Live speech recognition for one voice session; ``keyterms`` are the session agent's."""
    api_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
    if not api_key:
        return None
    return DeepgramSTTService(api_key=api_key, settings=stt_settings(keyterms=keyterms))


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
