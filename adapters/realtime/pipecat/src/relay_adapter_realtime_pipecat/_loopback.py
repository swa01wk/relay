"""Phase 2 audio ingress helpers (no agent TTS until Phase 4)."""

from pipecat.frames.frames import Frame, InputAudioRawFrame, OutputAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


class AudioIngressSink(FrameProcessor):
    """Consume mic frames on the server; do not play them back to the client."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            return
        await self.push_frame(frame, direction)


class AudioLoopbackProcessor(FrameProcessor):
    """Echo mic to speaker — debug only (``RELAY_WEBRTC_AUDIO_LOOPBACK=1``)."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, InputAudioRawFrame):
            await self.push_frame(
                OutputAudioRawFrame(
                    audio=frame.audio,
                    sample_rate=frame.sample_rate,
                    num_channels=frame.num_channels,
                ),
                direction,
            )
        else:
            await self.push_frame(frame, direction)
