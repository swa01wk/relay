"""Pick the speech-recognition provider for voice sessions (``RELAY_STT_PROVIDER``)."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from typing import Any

logger = logging.getLogger(__name__)

STT_PROVIDERS = ("deepgram", "cartesia", "assemblyai")
_API_KEY_ENV = {"deepgram": "DEEPGRAM_API_KEY", "cartesia": "CARTESIA_API_KEY", "assemblyai": "ASSEMBLYAI_API_KEY"}


def stt_provider() -> str:
    """``deepgram`` (default), ``cartesia`` or ``assemblyai``; unknown values log and use ``deepgram``."""
    name = os.environ.get("RELAY_STT_PROVIDER", "").strip().lower() or "deepgram"
    if name not in STT_PROVIDERS:
        logger.warning("RELAY_STT_PROVIDER=%r is not one of %s; using deepgram", name, STT_PROVIDERS)
        return "deepgram"
    return name


def stt_api_key_env() -> str:
    return _API_KEY_ENV[stt_provider()]


def build_stt_service(*, keyterms: Iterable[str] = ()) -> Any | None:
    """Pipecat STT service for one voice session, or ``None`` when the provider's key is missing."""
    provider = stt_provider()
    if provider == "cartesia":
        from relay_adapter_speech_cartesia import build_pipecat_stt_service
    elif provider == "assemblyai":
        from relay_adapter_speech_assemblyai import build_pipecat_stt_service
    else:
        from relay_adapter_speech_deepgram import build_pipecat_stt_service
    return build_pipecat_stt_service(keyterms=keyterms)
