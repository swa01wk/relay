"""Voice hooks never make the audio pipeline wait, and still run in order."""

from __future__ import annotations

import asyncio

import pytest

from relay_adapter_realtime_pipecat.voice_pipeline import VoicePipelineHooks, non_blocking_hooks


@pytest.mark.asyncio
async def test_a_slow_hook_does_not_block_the_caller_and_order_is_kept():
    release = asyncio.Event()
    calls: list[tuple[str, str]] = []

    async def speech_started(session_id: str) -> None:
        await release.wait()  # the session is busy
        calls.append(("started", session_id))

    async def speech_ended(session_id: str) -> None:
        calls.append(("ended", session_id))

    async def delta(session_id: str, text: str) -> None:
        calls.append(("delta", text))

    async def final(session_id: str, text: str) -> None:
        calls.append(("final", text))

    hooks = non_blocking_hooks(
        VoicePipelineHooks(
            on_speech_started=speech_started,
            on_speech_ended=speech_ended,
            on_transcript_delta=delta,
            on_transcript_final=final,
        )
    )
    await asyncio.wait_for(hooks.on_speech_started("s"), timeout=0.1)
    await asyncio.wait_for(hooks.on_transcript_delta("s", "Hel"), timeout=0.1)
    await asyncio.wait_for(hooks.on_transcript_final("s", "Hello"), timeout=0.1)
    await asyncio.wait_for(hooks.on_speech_ended("s"), timeout=0.1)
    assert calls == []

    release.set()
    await hooks.dispatcher.idle()
    assert calls == [("started", "s"), ("delta", "Hel"), ("final", "Hello"), ("ended", "s")]


@pytest.mark.asyncio
async def test_a_failing_hook_does_not_stop_later_ones():
    calls: list[str] = []

    async def boom(session_id: str) -> None:
        raise RuntimeError("session gone")

    async def final(session_id: str, text: str) -> None:
        calls.append(text)

    async def noop(*args) -> None:
        return None

    hooks = non_blocking_hooks(
        VoicePipelineHooks(on_speech_started=boom, on_speech_ended=noop, on_transcript_delta=noop,
                           on_transcript_final=final)
    )
    await hooks.on_speech_started("s")
    await hooks.on_transcript_final("s", "still heard")
    await hooks.dispatcher.idle()
    assert calls == ["still heard"]
