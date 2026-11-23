"""AssemblyAI speech-recognition settings: model, language, key terms."""

from __future__ import annotations

from pipecat.transcriptions.language import Language

from relay_adapter_speech_assemblyai import build_pipecat_stt_service, stt_settings


def _clear(monkeypatch):
    for name in (
        "ASSEMBLYAI_API_KEY",
        "ASSEMBLYAI_STT_MODEL",
        "ASSEMBLYAI_STT_LANGUAGE",
        "ASSEMBLYAI_STT_KEYTERMS",
        "DEEPGRAM_STT_LANGUAGE",
        "DEEPGRAM_STT_KEYTERMS",
    ):
        monkeypatch.delenv(name, raising=False)


def test_defaults(monkeypatch):
    _clear(monkeypatch)
    settings = stt_settings()
    assert settings.model == "universal-3-6-pro"
    assert settings.language == Language.EN
    assert settings.keyterms_prompt is None


def test_language_follows_deepgram_base_language_unless_set(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DEEPGRAM_STT_LANGUAGE", "en-IN")
    assert stt_settings().language == Language.EN
    monkeypatch.setenv("ASSEMBLYAI_STT_LANGUAGE", "hi")
    assert stt_settings().language == Language.HI


def test_agent_keyterms_then_gateway_ones(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("DEEPGRAM_STT_KEYTERMS", "Relay, okafor")
    assert stt_settings(keyterms=["Okafor"]).keyterms_prompt == ["Okafor", "Relay"]


def test_service_needs_a_key(monkeypatch):
    _clear(monkeypatch)
    assert build_pipecat_stt_service() is None
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "aai_test")
    monkeypatch.setenv("ASSEMBLYAI_STT_MODEL", "universal-streaming-english")
    assert build_pipecat_stt_service(keyterms=["Okafor"]) is not None
