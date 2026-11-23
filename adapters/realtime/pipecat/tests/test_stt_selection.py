"""RELAY_STT_PROVIDER picks the speech-recognition service for voice sessions."""

from __future__ import annotations

from pipecat.services.assemblyai.stt import AssemblyAISTTService
from pipecat.services.cartesia.stt import CartesiaSTTService
from pipecat.services.deepgram.stt import DeepgramSTTService

from relay_adapter_realtime_pipecat.stt_selection import build_stt_service, stt_api_key_env, stt_provider


def test_deepgram_is_the_default(monkeypatch):
    monkeypatch.delenv("RELAY_STT_PROVIDER", raising=False)
    monkeypatch.setenv("DEEPGRAM_API_KEY", "dg_test")
    assert stt_provider() == "deepgram"
    assert isinstance(build_stt_service(), DeepgramSTTService)


def test_cartesia_when_selected(monkeypatch):
    monkeypatch.setenv("RELAY_STT_PROVIDER", " Cartesia ")
    monkeypatch.setenv("CARTESIA_API_KEY", "sk_test")
    assert stt_api_key_env() == "CARTESIA_API_KEY"
    assert isinstance(build_stt_service(keyterms=["Okafor"]), CartesiaSTTService)
    monkeypatch.delenv("CARTESIA_API_KEY")
    assert build_stt_service() is None


def test_unknown_provider_falls_back_to_deepgram(monkeypatch):
    monkeypatch.setenv("RELAY_STT_PROVIDER", "whisperx")
    assert stt_provider() == "deepgram"


def test_assemblyai_when_selected(monkeypatch):
    monkeypatch.setenv("RELAY_STT_PROVIDER", "assemblyai")
    monkeypatch.setenv("ASSEMBLYAI_API_KEY", "aai_test")
    assert stt_api_key_env() == "ASSEMBLYAI_API_KEY"
    assert isinstance(build_stt_service(keyterms=["Okafor"]), AssemblyAISTTService)
