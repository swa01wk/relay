"""Stream assistant tokens to TTS and WebRTC playout."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

from relay_runtime.playback_tracker import PlaybackTracker
from relay_runtime.ports.realtime import RealtimeTransport
from relay_runtime.ports.speech import TextToSpeechProvider
from relay_runtime.turn_cancellation import TurnCancellation

PublishMetricFn = Callable[[str, float], Awaitable[None]]


@dataclass
class VoiceOutputConfig:
    sample_rate: int = 24000
    num_channels: int = 1


async def stream_tokens_to_queue(
    token_source: AsyncIterator[str],
    queue: asyncio.Queue[str | None],
    *,
    cancel: TurnCancellation | None = None,
) -> None:
    try:
        async for token in token_source:
            if cancel and cancel.is_cancelled:
                break
            if token:
                await queue.put(token)
    finally:
        await queue.put(None)


async def queue_to_text_iterator(queue: asyncio.Queue[str | None]) -> AsyncIterator[str]:
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item


async def play_tts_stream(
    *,
    session_id: str,
    text_tokens: AsyncIterator[str],
    tts: TextToSpeechProvider,
    transport: RealtimeTransport,
    playback: PlaybackTracker,
    config: VoiceOutputConfig,
    cancel: TurnCancellation | None = None,
    on_metric: PublishMetricFn | None = None,
    speech_started_at: float | None = None,
    on_playout_started: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Synthesize streaming text and push PCM to the realtime transport."""

    first_byte_at: float | None = None
    await transport.prepare_output_playout(session_id)

    try:
        async for pcm in tts.synthesize_stream(session_id, text_tokens):
            if cancel and cancel.is_cancelled:
                await tts.cancel(session_id)
                break
            if not pcm:
                continue
            if first_byte_at is None:
                first_byte_at = time.perf_counter()
                await playback.on_speech_started()
                if on_playout_started is not None:
                    await on_playout_started()
                if on_metric:
                    await on_metric("voice.first_tts_byte_ms", 0.0)
                if speech_started_at is not None and on_metric:
                    latency = (first_byte_at - speech_started_at) * 1000.0
                    await on_metric("voice.user_stop_to_first_audio_ms", latency)
            await transport.push_output_pcm(
                session_id,
                audio=pcm,
                sample_rate=config.sample_rate,
                num_channels=config.num_channels,
            )
            await playback.on_playout_bytes(
                byte_count=len(pcm),
                sample_rate=config.sample_rate,
                num_channels=config.num_channels,
            )
            if cancel and cancel.is_cancelled:
                break
        await transport.finish_output_pcm(session_id)
        if not (cancel and cancel.is_cancelled):
            await transport.wait_output_drained(session_id)
    finally:
        reason = "cancelled" if cancel and cancel.is_cancelled else "complete"
        await playback.on_speech_stopped(reason=reason)
        if cancel and cancel.is_cancelled:
            await tts.cancel(session_id)
            await transport.cancel_output(session_id)
