"""Deepgram SpeechToTextProvider port contract."""

import pytest

from relay_adapter_speech_deepgram import DeepgramSpeechToTextProvider


@pytest.mark.asyncio
async def test_deepgram_provider_stream_yields_final():
    provider = DeepgramSpeechToTextProvider()

    async def audio():
        yield b"\x00\x00" * 160

    parts = [part async for part in provider.stream_transcription("s1", audio())]
    assert parts[-1]["is_final"] is True
    await provider.close("s1")
