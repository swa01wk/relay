"""Cartesia speech-recognition settings: model, language, key terms."""

from __future__ import annotations

from relay_adapter_speech_cartesia import build_pipecat_stt_service, stt_settings


def _clear(monkeypatch):
    for name in (
        "CARTESIA_API_KEY",
        "CARTESIA_STT_MODEL",
        "CARTESIA_STT_LANGUAGE",
        "CARTESIA_STT_KEYTERMS",
        "DEEPGRAM_STT_LANGUAGE",
        "DEEPGRAM_STT_KEYTERMS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults_to_ink_whisper_english(monkeypatch):
    _clear(monkeypatch)
    settings = stt_settings()
    assert settings.model == "ink-whisper" and settings.language == "en"


def test_language_follows_deepgram_base_language_unless_set(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DEEPGRAM_STT_LANGUAGE", "en-IN")
    assert stt_settings().language == "en"
    monkeypatch.setenv("CARTESIA_STT_LANGUAGE", "hi")
    assert stt_settings().language == "hi"


def test_keyterms_only_for_ink_2(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DEEPGRAM_STT_KEYTERMS", "Relay, okafor")
    assert not stt_settings(keyterms=["Okafor"]).keyterm
    monkeypatch.setenv("CARTESIA_STT_MODEL", "ink-2")
    assert stt_settings(keyterms=["Okafor"]).keyterm == ["Okafor", "Relay"]


def test_no_key_means_no_service(monkeypatch):
    _clear(monkeypatch)
    assert build_pipecat_stt_service() is None
    monkeypatch.setenv("CARTESIA_API_KEY", "sk_test")
    assert build_pipecat_stt_service() is not None
