"""Speech-recognition settings: language, key terms, model fallback."""

from __future__ import annotations

from relay_adapter_speech_deepgram.provider import MAX_KEYTERMS, clean_keyterms, stt_keyterms, stt_settings


def test_language_defaults_to_en_and_is_configurable(monkeypatch):
    monkeypatch.delenv("DEEPGRAM_STT_LANGUAGE", raising=False)
    monkeypatch.setenv("DEEPGRAM_STT_MODEL", "nova-3-general")
    assert stt_settings().language == "en"
    monkeypatch.setenv("DEEPGRAM_STT_LANGUAGE", "en-IN")
    assert stt_settings().language == "en-IN"


def test_agent_keyterms_come_first_then_gateway_ones_deduplicated(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_STT_MODEL", "nova-3-general")
    monkeypatch.setenv("DEEPGRAM_STT_KEYTERMS", "Relay, northwind  logistics ,")
    settings = stt_settings(keyterms=["Northwind Logistics", "  Okafor "])
    assert settings.keyterm == ["Northwind Logistics", "Okafor", "Relay"]


def test_no_keyterms_sends_none(monkeypatch):
    monkeypatch.setenv("DEEPGRAM_STT_MODEL", "nova-3-general")
    monkeypatch.delenv("DEEPGRAM_STT_KEYTERMS", raising=False)
    assert not stt_settings().keyterm


def test_keyterms_are_capped_and_trimmed():
    terms = clean_keyterms([f"term {i}" for i in range(150)] + ["x" * 80])
    assert len(terms) == MAX_KEYTERMS
    assert clean_keyterms(["x" * 80]) == ["x" * 50]


def test_flux_falls_back_to_nova_3_and_older_models_skip_keyterms(monkeypatch):
    monkeypatch.delenv("DEEPGRAM_STT_KEYTERMS", raising=False)
    monkeypatch.setenv("DEEPGRAM_STT_MODEL", "flux-general-en")
    flux = stt_settings(keyterms=["Okafor"])
    assert flux.model == "nova-3-general" and flux.keyterm == ["Okafor"]
    monkeypatch.setenv("DEEPGRAM_STT_MODEL", "nova-2-general")
    assert not stt_settings(keyterms=["Okafor"]).keyterm
    assert stt_keyterms(["a", "A"]) == ["a"]
