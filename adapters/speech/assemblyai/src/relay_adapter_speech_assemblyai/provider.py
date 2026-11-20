"""AssemblyAI streaming STT — Pipecat service factory.

Selected with ``RELAY_STT_PROVIDER=assemblyai``. Runs in Pipecat turn mode
(``vad_force_turn_endpoint=True``): Relay's own turn detection decides when the user is done,
AssemblyAI just returns finals quickly.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable

from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.transcriptions.language import Language

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "universal-3-6-pro"
MAX_KEYTERMS = 100
MAX_KEYTERM_CHARS = 50


def stt_model() -> str:
    return os.environ.get("ASSEMBLYAI_STT_MODEL", "").strip() or DEFAULT_MODEL


def stt_language() -> Language:
    """``ASSEMBLYAI_STT_LANGUAGE`` (e.g. ``en``, ``hi``); falls back to the base language of
    ``DEEPGRAM_STT_LANGUAGE`` (``en-IN`` → ``en``). Unknown codes use English."""
    lang = os.environ.get("ASSEMBLYAI_STT_LANGUAGE", "").strip()
    if not lang:
        lang = os.environ.get("DEEPGRAM_STT_LANGUAGE", "").strip()
        if lang.lower() == "multi":
            lang = ""
    code = (lang.split("-")[0].lower() if lang else "") or "en"
    try:
        return Language(code)
    except ValueError:
        logger.warning("ASSEMBLYAI_STT_LANGUAGE=%r is not a known language; using en", code)
        return Language.EN


def stt_keyterms(agent_keyterms: Iterable[str] = ()) -> list[str]:
    """The agent's key terms, then ``ASSEMBLYAI_STT_KEYTERMS`` / ``DEEPGRAM_STT_KEYTERMS``
    (comma-separated): trimmed, de-duplicated, at most 100 of 50 characters."""
    gateway = os.environ.get("ASSEMBLYAI_STT_KEYTERMS") or os.environ.get("DEEPGRAM_STT_KEYTERMS", "")
    seen: set[str] = set()
    out: list[str] = []
    for term in [*agent_keyterms, *gateway.split(",")]:
        text = " ".join(str(term).split())[:MAX_KEYTERM_CHARS].strip()
        if not text or text.lower() in seen:
            continue
        seen.add(text.lower())
        out.append(text)
        if len(out) == MAX_KEYTERMS:
            break
    return out


def stt_settings(*, keyterms: Iterable[str] = ()) -> AssemblyAISTTService.Settings:
    terms = stt_keyterms(keyterms)
    return AssemblyAISTTService.Settings(
        model=stt_model(),
        language=stt_language(),
        keyterms_prompt=terms or None,
    )


def build_pipecat_stt_service(*, keyterms: Iterable[str] = ()) -> AssemblyAISTTService | None:
    """Live speech recognition for one voice session; ``None`` without ``ASSEMBLYAI_API_KEY``."""
    api_key = os.environ.get("ASSEMBLYAI_API_KEY", "").strip()
    if not api_key:
        return None
    return AssemblyAISTTService(
        api_key=api_key,
        settings=stt_settings(keyterms=keyterms),
        vad_force_turn_endpoint=True,
    )
