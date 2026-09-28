"""TTS port adapter — mock streaming PCM."""

from __future__ import annotations

import pytest

from relay_adapter_speech_deepgram.tts_provider import MockTextToSpeechProvider


@pytest.mark.asyncio
async def test_mock_tts_streams_pcm_for_tokens():
    tts = MockTextToSpeechProvider(sample_rate=24000)

    async def text():
        yield "hello"
        yield " world"

    chunks = [c async for c in tts.synthesize_stream("sess-1", text())]
    assert chunks
    assert sum(len(c) for c in chunks) > 0


@pytest.mark.asyncio
async def test_mock_tts_speaks_after_cancel():
    """P07 barge-in: next utterance must not inherit cancel (regression)."""
    tts = MockTextToSpeechProvider(sample_rate=24000)

    async def text():
        yield "first"

    _ = [c async for c in tts.synthesize_stream("sess-1", text())]
    await tts.cancel("sess-1")

    async def text2():
        yield "second"

    chunks = [c async for c in tts.synthesize_stream("sess-1", text2())]
    assert chunks
