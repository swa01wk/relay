"""Agent playout progress for heard-truth (Phase 7)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from relay_runtime.interruption_manager import InterruptionManager

PublishSpeechFn = Callable[[str, float], Awaitable[None]]

# Rough average speaking rate for heard-prefix estimation when playout is cut short.
_MS_PER_CHAR_ESTIMATE = 45.0


@dataclass
class PlaybackTracker:
    """Tracks generated vs delivered audio; emits RP speech events via callback."""

    session_id: str
    cursor_ms: float = 0.0
    speaking: bool = False
    generated_text: str = ""
    heard_text: str = ""
    delivered_ms: float = 0.0
    total_audio_ms: float = 0.0
    _on_progress: PublishSpeechFn | None = field(default=None, repr=False)
    _progress_step_ms: float = 250.0

    def set_progress_handler(self, handler: PublishSpeechFn | None) -> None:
        self._on_progress = handler

    def reset(self) -> None:
        self.cursor_ms = 0.0
        self.speaking = False
        self.generated_text = ""
        self.heard_text = ""
        self.delivered_ms = 0.0
        self.total_audio_ms = 0.0

    def note_generated_text(self, text: str) -> None:
        self.generated_text = text

    def append_generated_text(self, chunk: str) -> None:
        if chunk:
            self.generated_text += chunk

    async def on_speech_started(self) -> None:
        self.speaking = True
        self.cursor_ms = 0.0
        self.delivered_ms = 0.0

    async def on_playout_bytes(
        self,
        *,
        byte_count: int,
        sample_rate: int,
        num_channels: int = 1,
        bytes_per_sample: int = 2,
    ) -> None:
        if byte_count <= 0 or sample_rate <= 0:
            return
        frame_ms = (byte_count / (sample_rate * num_channels * bytes_per_sample)) * 1000.0
        self.cursor_ms += frame_ms
        self.delivered_ms = self.cursor_ms
        self.total_audio_ms = self.cursor_ms
        if self._on_progress and self._should_emit_progress():
            await self._on_progress("SPEECH_PROGRESS", self.cursor_ms)

    def _should_emit_progress(self) -> bool:
        if self._progress_step_ms <= 0:
            return True
        steps = int(self.cursor_ms // self._progress_step_ms)
        prev_steps = int((self.cursor_ms - 0.001) // self._progress_step_ms)
        return steps > prev_steps

    def finalize_heard(self, *, interrupted: bool) -> str:
        """Compute heard prefix after playout completes or barge-in (§7.2)."""
        if not interrupted:
            self.heard_text = self.generated_text
            return self.heard_text
        estimated_total = max(
            self.total_audio_ms,
            len(self.generated_text) * _MS_PER_CHAR_ESTIMATE,
        )
        self.heard_text = InterruptionManager.heard_prefix(
            generated_text=self.generated_text,
            delivered_ms=self.delivered_ms,
            total_audio_ms=estimated_total,
        )
        return self.heard_text

    async def on_speech_stopped(self, *, reason: str = "complete") -> None:
        self.speaking = False
        if self._on_progress:
            await self._on_progress("SPEECH_STOPPED", self.cursor_ms)
