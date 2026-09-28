"""Env-gated failure injection for hardening tests (Phase 11, PRD §14.2)."""

from __future__ import annotations

import os


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def inject_tool_timeout_seconds(default: float) -> float:
    raw = os.environ.get("RELAY_INJECT_TOOL_TIMEOUT_SEC", "").strip()
    if raw:
        return max(0.01, float(raw))
    return default


def inject_model_timeout() -> bool:
    return _flag("RELAY_INJECT_MODEL_TIMEOUT")


def inject_stt_timeout() -> bool:
    return _flag("RELAY_INJECT_STT_TIMEOUT")


def inject_transport_fail_connect() -> bool:
    return _flag("RELAY_INJECT_TRANSPORT_DISCONNECT")


def inject_tts_failure() -> bool:
    return _flag("RELAY_INJECT_TTS_FAILURE")
