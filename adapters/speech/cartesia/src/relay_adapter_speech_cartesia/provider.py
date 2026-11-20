"""Cartesia live STT (Ink models) — Pipecat service factory.

Selected with ``RELAY_STT_PROVIDER=cartesia``; the realtime adapter picks the factory.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable

from pipecat.services.cartesia.stt import CartesiaSTTService

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "ink-whisper"
# Cartesia honours key terms only on these model families.
KEYTERM_MODEL_PREFIXES = ("ink-2", "ink-preview")
MAX_KEYTERMS = 100
MAX_KEYTERMS_TOTAL_CHARS = 1200


def stt_model() -> str:
    return os.environ.get("CARTESIA_STT_MODEL", "").strip() or DEFAULT_MODEL


def stt_language() -> str:
    """``CARTESIA_STT_LANGUAGE`` (ISO 639-1, e.g. ``en``, ``hi``). Falls back to the base language
    of ``DEEPGRAM_STT_LANGUAGE`` (``en-IN`` → ``en``) so switching providers keeps the language."""
    lang = os.environ.get("CARTESIA_STT_LANGUAGE", "").strip()
    if not lang:
        lang = os.environ.get("DEEPGRAM_STT_LANGUAGE", "").strip()
        if lang.lower() == "multi":
            lang = ""
    return (lang.split("-")[0].lower() if lang else "") or "en"


def stt_keyterms(agent_keyterms: Iterable[str] = ()) -> list[str]:
    """The agent's key terms, then ``CARTESIA_STT_KEYTERMS`` / ``DEEPGRAM_STT_KEYTERMS``
    (comma-separated), de-duplicated, within Cartesia's per-connection limits."""
    gateway = os.environ.get("CARTESIA_STT_KEYTERMS") or os.environ.get("DEEPGRAM_STT_KEYTERMS", "")
    seen: set[str] = set()
    out: list[str] = []
    total = 0
    for term in [*agent_keyterms, *gateway.split(",")]:
        text = " ".join(str(term).split())
        if not text or text.lower() in seen:
            continue
        if len(out) == MAX_KEYTERMS or total + len(text) > MAX_KEYTERMS_TOTAL_CHARS:
            break
        seen.add(text.lower())
        out.append(text)
        total += len(text)
    return out


def stt_settings(*, keyterms: Iterable[str] = ()) -> CartesiaSTTService.Settings:
    model = stt_model()
    extra = {}
    terms = stt_keyterms(keyterms)
    if terms:
        if model.startswith(KEYTERM_MODEL_PREFIXES):
            extra["keyterm"] = terms
        else:
            logger.info(
                "speech key terms need a Cartesia ink-2 model; not sent for CARTESIA_STT_MODEL=%r", model
            )
    return CartesiaSTTService.Settings(model=model, language=stt_language(), **extra)


def build_pipecat_stt_service(*, keyterms: Iterable[str] = ()) -> CartesiaSTTService | None:
    """Live speech recognition for one voice session; ``None`` without ``CARTESIA_API_KEY``."""
    api_key = os.environ.get("CARTESIA_API_KEY", "").strip()
    if not api_key:
        return None
    return CartesiaSTTService(api_key=api_key, settings=stt_settings(keyterms=keyterms))
