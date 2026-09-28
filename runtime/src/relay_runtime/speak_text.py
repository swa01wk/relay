"""Strip markdown/formatting before TTS (display text stays raw in RP/UI)."""

from __future__ import annotations

import re


def plain_text_for_speech(text: str) -> str:
    """Best-effort markdown removal for spoken output."""
    if not text:
        return ""
    out = text
    out = re.sub(r"\*\*([^*]+)\*\*", r"\1", out)
    out = re.sub(r"\*([^*]+)\*", r"\1", out)
    out = re.sub(r"`([^`]+)`", r"\1", out)
    out = re.sub(r"^[\s]*[-*•]\s+", "", out, flags=re.MULTILINE)
    out = re.sub(r"\s--\s", ", ", out)
    out = out.replace("**", "").replace("*", "")
    out = re.sub(r"\n{3,}", "\n\n", out)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out.strip()


class SpeechTextStream:
    """Map raw LLM token stream → speakable text stream for TTS."""

    def __init__(self) -> None:
        self._raw = ""
        self._spoken_len = 0

    def push(self, token: str) -> str:
        if not token:
            return ""
        self._raw += token
        speakable = plain_text_for_speech(self._raw)
        if len(speakable) <= self._spoken_len:
            return ""
        chunk = speakable[self._spoken_len :]
        self._spoken_len = len(speakable)
        return chunk

    def flush(self) -> str:
        speakable = plain_text_for_speech(self._raw)
        if len(speakable) <= self._spoken_len:
            return ""
        chunk = speakable[self._spoken_len :]
        self._spoken_len = len(speakable)
        return chunk
