"""Inject STT frames → hooks receive transcript callbacks."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from relay_adapter_realtime_pipecat.voice_pipeline import (
    RelayTranscriptProcessor,
    RelayVadStartHookProcessor,
    VoicePipelineHooks,
)
from pipecat.frames.frames import (
    InterimTranscriptionFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection


@pytest.mark.asyncio
async def test_inject_transcription_frames_notify_session():
    on_delta = AsyncMock()
    on_final = AsyncMock()
    hooks = VoicePipelineHooks(
        on_speech_started=AsyncMock(),
        on_speech_ended=AsyncMock(),
        on_transcript_delta=on_delta,
        on_transcript_final=on_final,
    )
    processor = RelayTranscriptProcessor(session_id="sess-1", hooks=hooks)
    await processor.process_frame(
        InterimTranscriptionFrame(text="hel", user_id="user", timestamp="2020"),
        FrameDirection.DOWNSTREAM,
    )
    await processor.process_frame(
        TranscriptionFrame(text="hello", user_id="user", timestamp="2020"),
        FrameDirection.DOWNSTREAM,
    )
    on_delta.assert_awaited_once_with("sess-1", "hel")
    on_final.assert_awaited_once_with("sess-1", "hello")


@pytest.mark.asyncio
async def test_vad_start_hook_notifies_speech_started():
    on_started = AsyncMock()
    hooks = VoicePipelineHooks(
        on_speech_started=on_started,
        on_speech_ended=AsyncMock(),
        on_transcript_delta=AsyncMock(),
        on_transcript_final=AsyncMock(),
    )
    processor = RelayVadStartHookProcessor(session_id="sess-2", hooks=hooks)
    await processor.process_frame(VADUserStartedSpeakingFrame(), FrameDirection.DOWNSTREAM)
    on_started.assert_awaited_once_with("sess-2")
