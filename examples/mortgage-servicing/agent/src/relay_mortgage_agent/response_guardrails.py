"""Strip internal Relay/runtime vocabulary from user-facing assistant text."""

from __future__ import annotations

import re
from collections.abc import AsyncIterator

# Longest patterns first so partial overlaps resolve cleanly.
_REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"I don't (?:see|have) (?:a )?(?:\d{4} )?rate entry[^.]*\.?",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(
            r"I don't (?:see|have) (?:the )?(?:full )?origination[^.]*(?:visible|shown|in the current view)[^.]*\.?",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(
            r"I(?:'ve| have)n't actually synced (?:the )?(?:screen|UI) state[^.]*\.?",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(
            r"I can(?:'|no)?t directly sync (?:the )?(?:UI|screen) state[^.]*\.?",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(
            r"I can(?:'|no)?t verify (?:the )?UI change[^.]*\.?",
            re.IGNORECASE,
        ),
        "",
    ),
    (
        re.compile(r"\b(?:the )?routed handler\b[^.]*\.?", re.IGNORECASE),
        "",
    ),
    (
        re.compile(r"\bstate sync\b", re.IGNORECASE),
        "update",
    ),
    (
        re.compile(r"\bCurrent UI state I can see\b", re.IGNORECASE),
        "On your screen",
    ),
    (
        re.compile(r"\bUI state\b", re.IGNORECASE),
        "screen",
    ),
    (
        re.compile(r"\bruntime state\b", re.IGNORECASE),
        "the draft",
    ),
    (
        re.compile(r"\bSTATE_(?:SNAPSHOT|DELTA|CONFLICT)\b"),
        "",
    ),
    (
        re.compile(r"\bbased_on_version\b"),
        "",
    ),
    (
        re.compile(r"\bapply_state_delta\b"),
        "",
    ),
    (
        re.compile(r"\brequest_action\b"),
        "",
    ),
)

# Hold back trailing chars that might complete a forbidden phrase on the next chunk.
_HOLD_BACK = 96


def _apply_redactions(text: str, *, strip_edges: bool) -> str:
    cleaned = text
    for pattern, replacement in _REDACT_PATTERNS:
        cleaned = pattern.sub(replacement, cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\.\s+\.", ".", cleaned)
    if strip_edges:
        return cleaned.strip()
    return cleaned


def sanitize_assistant_text(text: str) -> str:
    return _apply_redactions(text, strip_edges=True)


class StreamingAssistantGuard:
    """Stateful sanitizer for token/chunk streaming."""

    def __init__(self) -> None:
        self._pending = ""

    def push(self, fragment: str) -> str:
        if not fragment:
            return ""
        self._pending += fragment
        if len(self._pending) <= _HOLD_BACK:
            return ""
        emit_raw = self._pending[:-_HOLD_BACK]
        self._pending = self._pending[-_HOLD_BACK:]
        # Do not strip chunk edges — leading/trailing spaces often belong to the next token.
        return _apply_redactions(emit_raw, strip_edges=False)

    def flush(self) -> str:
        tail = _apply_redactions(self._pending, strip_edges=True)
        self._pending = ""
        return tail


async def guard_stream(source: AsyncIterator[str]) -> AsyncIterator[str]:
    guard = StreamingAssistantGuard()
    async for token in source:
        out = guard.push(token)
        if out:
            yield out
    tail = guard.flush()
    if tail:
        yield tail
