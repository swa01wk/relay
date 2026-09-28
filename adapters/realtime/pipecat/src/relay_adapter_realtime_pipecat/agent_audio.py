"""Agent PCM egress into SmallWebRTC transport output."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from pipecat.frames.frames import CancelFrame, EndFrame, Frame, OutputAudioRawFrame, StartFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

_FINISH = object()


@dataclass
class AgentAudioOutputProcessor(FrameProcessor):
    """Emit agent PCM on a background pump (independent of mic ingress)."""

    session_id: str
    _queue: asyncio.Queue[object] = field(default_factory=asyncio.Queue)
    _finished: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _cancelled: bool = field(default=False, init=False)
    _pump_task: asyncio.Task[None] | None = field(default=None, init=False)

    def __post_init__(self) -> None:
        super().__init__(name=f"AgentAudioOut-{self.session_id[:8]}")

    def _ensure_pump(self) -> None:
        if self._pump_task is not None and not self._pump_task.done():
            return
        self._pump_task = asyncio.create_task(
            self._pump_loop(),
            name=f"agent-audio-pump-{self.session_id[:8]}",
        )

    async def _pump_loop(self) -> None:
        try:
            while not self._cancelled:
                item = await self._queue.get()
                if item is _FINISH:
                    self._finished.set()
                    continue
                if not isinstance(item, tuple):
                    continue
                audio, sample_rate, num_channels = item
                if not audio:
                    continue
                await self.push_frame(
                    OutputAudioRawFrame(
                        audio=audio,
                        sample_rate=sample_rate,
                        num_channels=num_channels,
                    ),
                    FrameDirection.DOWNSTREAM,
                )
        except asyncio.CancelledError:
            raise

    def prepare_for_playout(self) -> None:
        """Reset after ``cancel()`` so the next agent utterance can enqueue PCM."""
        self._cancelled = False
        self._finished.clear()
        self._ensure_pump()

    async def enqueue_pcm(self, audio: bytes, *, sample_rate: int, num_channels: int) -> None:
        if self._cancelled or not audio:
            return
        self._ensure_pump()
        self._finished.clear()
        await self._queue.put((audio, sample_rate, num_channels))

    async def finish(self) -> None:
        self._ensure_pump()
        await self._queue.put(_FINISH)

    async def cancel(self) -> None:
        """Stop current playout; call ``prepare_for_playout()`` before the next utterance."""
        self._cancelled = True
        if self._pump_task is not None:
            self._pump_task.cancel()
            try:
                await self._pump_task
            except asyncio.CancelledError:
                pass
            self._pump_task = None
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        self._finished.set()

    async def wait_drained(self) -> None:
        await self._finished.wait()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, StartFrame):
            self._ensure_pump()
        elif isinstance(frame, (CancelFrame, EndFrame)):
            if self._pump_task is not None:
                self._pump_task.cancel()
                self._pump_task = None
        await self.push_frame(frame, direction)
