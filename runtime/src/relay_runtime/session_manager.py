"""Session lifecycle, actor queue, and text turn orchestration."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from secrets import token_urlsafe
from typing import Any, Protocol
from uuid import uuid4

from relay_protocol import EventType, RelayEvent, RelayEventMetadata, minimal_payload_for

from relay_runtime.action_router import ActionRouter
from relay_runtime.agent_runtime import AgentRuntime
from relay_runtime.context_manager import ContextManager
from relay_runtime.hitl_manager import HitlLifecycleStage, HITLManager
from relay_runtime.observability import STAGE_HITL, STAGE_MODEL, STAGE_STT, STAGE_TTS, emit_trace_span
from relay_runtime.registry_tool_executor import RegistryToolExecutor
from relay_runtime.state_version_engine import StateApplyOutcome, StateVersionEngine
from relay_runtime.persisting_event_gateway import PersistingEventGateway
from relay_runtime.ports.realtime import RealtimeTransport
from relay_runtime.ports.speech import TextToSpeechProvider
from relay_runtime.trace_manager import TraceManager
from relay_runtime.interruption_manager import InterruptionManager, InterruptionPhase
from relay_runtime.playback_tracker import PlaybackTracker
from relay_runtime.turn_cancellation import TurnCancellation
from relay_runtime.turn_manager import TurnManager, TurnPhase, TurnTransitionError
from relay_runtime.speak_text import SpeechTextStream, plain_text_for_speech
from relay_runtime.voice_output import VoiceOutputConfig, play_tts_stream, queue_to_text_iterator

logger = logging.getLogger(__name__)


class SessionLock(Protocol):
    async def acquire(self, session_id: str, *, owner: str, ttl_seconds: int = 300) -> bool: ...

    async def release(self, session_id: str, *, owner: str) -> None: ...


class _CommandType(StrEnum):
    USER_TEXT = "USER_TEXT"
    CLIENT_STATE_SNAPSHOT = "CLIENT_STATE_SNAPSHOT"
    CLIENT_ACTION_RESULT = "CLIENT_ACTION_RESULT"
    CLIENT_APP_EVENT = "CLIENT_APP_EVENT"
    VOICE_SPEECH_STARTED = "VOICE_SPEECH_STARTED"
    VOICE_SPEECH_ENDED = "VOICE_SPEECH_ENDED"
    VOICE_TRANSCRIPT_DELTA = "VOICE_TRANSCRIPT_DELTA"
    VOICE_TRANSCRIPT_FINAL = "VOICE_TRANSCRIPT_FINAL"
    VOICE_CANCEL_UTTERANCE = "VOICE_CANCEL_UTTERANCE"
    VOICE_CANCEL_AGENT = "VOICE_CANCEL_AGENT"
    VOICE_TRY_COMMIT = "VOICE_TRY_COMMIT"
    VOICE_STT_FINAL_ENDPOINT = "VOICE_STT_FINAL_ENDPOINT"
    SHUTDOWN = "SHUTDOWN"


@dataclass
class _UserTextCommand:
    text: str
    done: asyncio.Future[None]


@dataclass
class _VoiceTranscriptDelta:
    text: str
    done: asyncio.Future[None]


@dataclass
class _VoiceTranscriptFinal:
    text: str
    done: asyncio.Future[None]


@dataclass
class _VoiceSignal:
    done: asyncio.Future[None]


@dataclass
class _ClientStateSnapshot:
    state: dict[str, Any]
    done: asyncio.Future[None]


@dataclass
class _ClientActionResult:
    action_id: str
    name: str
    outcome: str
    reason: str | None
    result: dict[str, Any] | None
    done: asyncio.Future[None]


@dataclass
class _ClientAppEvent:
    name: str
    payload: dict[str, Any]
    done: asyncio.Future[None]


@dataclass
class SessionRecord:
    session_id: str
    project_id: str
    agent_id: str
    trace_id: str
    dev_token: str
    token_expires_at: datetime
    sequence: int = 0
    ended: bool = False
    turn_manager: TurnManager = field(default_factory=TurnManager)
    playback_tracker: PlaybackTracker | None = None
    interruption_manager: InterruptionManager = field(default_factory=InterruptionManager)
    context: ContextManager = field(default_factory=ContextManager)
    action_router: ActionRouter = field(default_factory=ActionRouter)
    hitl_manager: HITLManager = field(default_factory=HITLManager)
    state_version_engine: StateVersionEngine = field(default_factory=StateVersionEngine)
    endpointing_started_at: float | None = None
    voice_capture_open: bool = False
    voice_cancelled: bool = False
    user_stopped_speaking_at: float | None = None
    voice_turn_cancel: TurnCancellation | None = None
    voice_response_task: asyncio.Task[None] | None = None
    voice_transcript_buffer: str = ""
    utterance_commit_task: asyncio.Task[None] | None = None
    stt_final_endpoint_task: asyncio.Task[None] | None = None
    active_response_id: str | None = None
    queue: asyncio.Queue[tuple[_CommandType, Any]] = field(default_factory=asyncio.Queue)
    worker: asyncio.Task[None] | None = None
    lock_owner: str = field(default_factory=lambda: str(uuid4()))
    context_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


@dataclass
class SessionManager:
    """Create sessions, serialize per-session work, run text turns."""

    event_gateway: PersistingEventGateway
    agent_runtime: AgentRuntime
    tool_executor: RegistryToolExecutor | None = None
    trace_manager: TraceManager = field(default_factory=TraceManager)
    session_lock: SessionLock | None = None
    realtime_transport: RealtimeTransport | None = None
    text_to_speech: TextToSpeechProvider | None = None
    voice_output: VoiceOutputConfig = field(default_factory=VoiceOutputConfig)
    _sessions: dict[str, SessionRecord] = field(default_factory=dict)
    dev_token_ttl_seconds: int = 3600

    @staticmethod
    def _utterance_commit_delay_ms() -> float:
        return float(os.environ.get("RELAY_UTTERANCE_COMMIT_DELAY_MS", "350"))

    @staticmethod
    def _stt_final_endpoint_ms() -> float:
        """Debounce after STT ``TRANSCRIPT_FINAL`` before synthetic VAD endpoint."""
        return float(os.environ.get("RELAY_STT_FINAL_ENDPOINT_MS", "500"))

    @staticmethod
    def _merge_voice_transcript(previous: str, incoming: str) -> str:
        incoming = incoming.strip()
        if not incoming:
            return previous.strip()
        if not previous.strip():
            return incoming
        prev = previous.strip()
        if incoming.startswith(prev) or prev in incoming:
            return incoming if len(incoming) >= len(prev) else prev
        return f"{prev} {incoming}".strip()

    def _next_sequence(self, session: SessionRecord) -> int:
        seq = session.sequence
        session.sequence += 1
        return seq

    def _base_metadata(self, session: SessionRecord, *, source: str) -> RelayEventMetadata:
        return RelayEventMetadata(
            session_id=session.session_id,
            project_id=session.project_id,
            trace_id=session.trace_id,
            sequence=self._next_sequence(session),
            source=source,
        )

    async def _publish(self, session: SessionRecord, event: RelayEvent) -> None:
        await self.event_gateway.publish(event)

    async def _run_session_actor(self, session: SessionRecord) -> None:
        while True:
            cmd_type, payload = await session.queue.get()
            try:
                if cmd_type == _CommandType.SHUTDOWN:
                    return
                if cmd_type == _CommandType.USER_TEXT:
                    assert isinstance(payload, _UserTextCommand)
                    await self._process_user_text(session, payload.text)
                    if not payload.done.done():
                        payload.done.set_result(None)
                elif cmd_type == _CommandType.CLIENT_STATE_SNAPSHOT:
                    assert isinstance(payload, _ClientStateSnapshot)
                    async with session.context_lock:
                        await self._process_client_state_snapshot(session, payload.state)
                    if not payload.done.done():
                        payload.done.set_result(None)
                elif cmd_type == _CommandType.CLIENT_ACTION_RESULT:
                    assert isinstance(payload, _ClientActionResult)
                    await self._process_client_action_result(session, payload)
                    if not payload.done.done():
                        payload.done.set_result(None)
                elif cmd_type == _CommandType.CLIENT_APP_EVENT:
                    assert isinstance(payload, _ClientAppEvent)
                    await self._process_client_app_event(session, payload.name, payload.payload)
                    if not payload.done.done():
                        payload.done.set_result(None)
                elif cmd_type == _CommandType.VOICE_SPEECH_STARTED:
                    assert isinstance(payload, _VoiceSignal)
                    await self._process_voice_speech_started(session)
                    if not payload.done.done():
                        payload.done.set_result(None)
                elif cmd_type == _CommandType.VOICE_SPEECH_ENDED:
                    assert isinstance(payload, _VoiceSignal)
                    await self._process_voice_speech_ended(session)
                    if not payload.done.done():
                        payload.done.set_result(None)
                elif cmd_type == _CommandType.VOICE_TRANSCRIPT_DELTA:
                    assert isinstance(payload, _VoiceTranscriptDelta)
                    await self._process_voice_transcript_delta(session, payload.text)
                    if not payload.done.done():
                        payload.done.set_result(None)
                elif cmd_type == _CommandType.VOICE_TRANSCRIPT_FINAL:
                    assert isinstance(payload, _VoiceTranscriptFinal)
                    await self._process_voice_transcript_final(session, payload.text)
                    if not payload.done.done():
                        payload.done.set_result(None)
                elif cmd_type == _CommandType.VOICE_CANCEL_UTTERANCE:
                    assert isinstance(payload, _VoiceSignal)
                    await self._process_voice_cancel(session)
                    if not payload.done.done():
                        payload.done.set_result(None)
                elif cmd_type == _CommandType.VOICE_CANCEL_AGENT:
                    assert isinstance(payload, _VoiceSignal)
                    await self._process_cancel_agent_playback(session)
                    if not payload.done.done():
                        payload.done.set_result(None)
                elif cmd_type == _CommandType.VOICE_TRY_COMMIT:
                    assert isinstance(payload, _VoiceSignal)
                    await self._maybe_commit_voice_utterance(session)
                    if not payload.done.done():
                        payload.done.set_result(None)
                elif cmd_type == _CommandType.VOICE_STT_FINAL_ENDPOINT:
                    assert isinstance(payload, _VoiceSignal)
                    await self._apply_stt_final_endpoint(session)
                    if not payload.done.done():
                        payload.done.set_result(None)
            except Exception:
                logger.exception("session actor error session_id=%s", session.session_id)
                done = getattr(payload, "done", None)
                if done is not None and not done.done():
                    done.set_exception(RuntimeError("session actor failed"))
            finally:
                session.queue.task_done()

    async def _process_user_text(self, session: SessionRecord, text: str) -> None:
        if session.ended:
            raise RuntimeError("session ended")
        phase = session.turn_manager.phase
        if phase in (TurnPhase.USER_SPEAKING, TurnPhase.ENDPOINTING):
            self._cancel_stt_final_endpoint_timer(session)
            self._cancel_utterance_commit_timer(session)
            try:
                session.turn_manager.cancel_utterance()
            except TurnTransitionError:
                pass
            session.voice_transcript_buffer = ""
            session.voice_capture_open = False
        elif phase == TurnPhase.AGENT_SPEAKING:
            await self._handle_barge_in(session)
        turn_id = str(uuid4())
        session.context.begin_turn(turn_id)
        try:
            session.turn_manager.begin_turn(turn_id)
        except TurnTransitionError:
            await self._publish(
                session,
                RelayEvent(
                    type=EventType.SESSION_ERROR,
                    metadata=self._base_metadata(session, source="turn_manager"),
                    payload={
                        "code": "turn_in_progress",
                        "message": (
                            "A voice utterance is in progress. "
                            "Wait for it to finish or cancel before sending text."
                        ),
                    },
                ),
            )
            return

        meta = self._base_metadata(session, source="turn_manager")
        await self._publish(
            session,
            RelayEvent(
                type=EventType.TURN_STARTED,
                metadata=meta.model_copy(update={"turn_id": turn_id}),
                payload=minimal_payload_for(EventType.TURN_STARTED),
            ),
        )
        await self._publish(
            session,
            RelayEvent(
                type=EventType.TURN_PROCESSING,
                metadata=self._base_metadata(session, source="turn_manager").model_copy(
                    update={"turn_id": turn_id}
                ),
                payload=minimal_payload_for(EventType.TURN_PROCESSING),
            ),
        )

        def next_meta(*, source: str) -> RelayEventMetadata:
            return self._base_metadata(session, source=source)

        async def emit_agent_event(event: RelayEvent) -> bool:
            return await self._emit_agent_event(session, event)

        assistant_text = await self.agent_runtime.run_text_turn(
            session_id=session.session_id,
            turn_id=turn_id,
            user_text=text,
            context=session.context,
            base_metadata=lambda source="agent_runtime": next_meta(source=source),
            publish=lambda event: self._publish(session, event),
            include_user_transcript=True,
            action_router=session.action_router,
            emit_agent_event=emit_agent_event,
        )

        await self._speak_assistant_if_voice_connected(
            session, turn_id=turn_id, assistant_text=assistant_text
        )

        await self._publish(
            session,
            RelayEvent(
                type=EventType.TURN_COMPLETED,
                metadata=self._base_metadata(session, source="turn_manager").model_copy(
                    update={"turn_id": turn_id}
                ),
                payload=minimal_payload_for(EventType.TURN_COMPLETED),
            ),
        )
        session.turn_manager.complete_turn(turn_id)

    async def _speak_assistant_if_voice_connected(
        self,
        session: SessionRecord,
        *,
        turn_id: str,
        assistant_text: str,
    ) -> None:
        """Play TTS on the WebRTC downlink when the user has voice connected (text Send path)."""
        if not assistant_text.strip():
            return
        tts = self.text_to_speech
        transport = self.realtime_transport
        use_tts = (
            tts is not None
            and transport is not None
            and await transport.is_connected(session.session_id)
        )
        if not use_tts or session.playback_tracker is None:
            return
        spoken = plain_text_for_speech(assistant_text)
        if not spoken.strip():
            return

        async def spoken_once():
            yield spoken

        session.playback_tracker.reset()

        async def on_playout_started() -> None:
            try:
                session.turn_manager.enter_agent_speaking(turn_id)
            except TurnTransitionError:
                logger.debug(
                    "skip enter_agent_speaking for text TTS turn_id=%s phase=%s",
                    turn_id,
                    session.turn_manager.phase,
                )
                return
            try:
                session.interruption_manager.on_agent_playout_started()
            except Exception:
                session.interruption_manager.on_idle()
                session.interruption_manager.on_agent_playout_started()
            await self._publish_speech_started(session, turn_id=turn_id)

        await play_tts_stream(
            session_id=session.session_id,
            text_tokens=spoken_once(),
            tts=tts,
            transport=transport,
            playback=session.playback_tracker,
            config=self.voice_output,
            cancel=None,
            on_metric=lambda name, value: self._publish_metric(session, name, value),
            on_playout_started=on_playout_started,
        )
        session.interruption_manager.on_idle()

    async def _publish_state_applied(
        self,
        session: SessionRecord,
        *,
        source: str,
        state_version: int,
        based_on_version: int | None = None,
    ) -> None:
        meta = self._base_metadata(session, source=source).model_copy(
            update={
                "state_version": state_version,
                "based_on_version": based_on_version,
            }
        )
        await self._publish(
            session,
            RelayEvent(
                type=EventType.STATE_SNAPSHOT,
                metadata=meta,
                payload={
                    "state": dict(session.context.state),
                    "state_version": state_version,
                },
            ),
        )
        await self._publish(
            session,
            RelayEvent(
                type=EventType.STATE_VERSION_ADVANCED,
                metadata=meta,
                payload={"state_version": state_version},
            ),
        )

    async def _process_client_state_snapshot(
        self, session: SessionRecord, snapshot: dict[str, Any]
    ) -> None:
        result = session.state_version_engine.apply_client_snapshot(session.context, snapshot)
        await self._publish_state_applied(
            session,
            source="client",
            state_version=result.state_version,
        )

    async def _emit_agent_event(self, session: SessionRecord, event: RelayEvent) -> bool:
        if event.type == EventType.APPROVAL_REQUESTED:
            tool_name = str(event.payload.get("tool_name", ""))
            arguments = dict(event.payload.get("arguments") or {})
            summary = str(event.payload.get("summary") or "")
            existing_id = event.payload.get("approval_id")
            record = session.hitl_manager.register_request(
                tool_name=tool_name,
                arguments=arguments,
                summary=summary,
                approval_id=str(existing_id) if existing_id else None,
            )
            enriched = RelayEvent(
                type=event.type,
                metadata=event.metadata,
                payload={
                    **event.payload,
                    "approval_id": record.approval_id,
                    "tool_name": record.tool_name,
                    "arguments": record.arguments,
                    "summary": record.summary or summary,
                    "lifecycle_stage": record.lifecycle_stage.value,
                },
            )
            await self._publish(session, enriched)
            return True

        if event.type != EventType.STATE_DELTA:
            await self._publish(session, event)
            return True

        patch = list(event.payload.get("patch") or [])
        based_on = event.metadata.based_on_version
        if based_on is None:
            based_on = event.payload.get("based_on_version")
        if based_on is None:
            logger.warning("STATE_DELTA missing based_on_version session_id=%s", session.session_id)
            await self._publish(session, event)
            return False

        conflict_followups: list[RelayEvent] = []
        applied = False
        async with session.context_lock:
            result = session.state_version_engine.try_apply_agent_delta(
                session.context,
                patch,
                based_on_version=int(based_on),
            )
            if result.outcome == StateApplyOutcome.CONFLICT:
                conflict_meta = self._base_metadata(session, source="state_version_engine").model_copy(
                    update={
                        "state_version": result.state_version,
                        "based_on_version": int(based_on),
                    }
                )
                conflict = RelayEvent(
                    type=EventType.STATE_CONFLICT,
                    metadata=conflict_meta,
                    payload={
                        "expected_version": result.expected_version,
                        "actual_version": result.actual_version,
                        "patch": patch,
                    },
                )
                await self._publish(session, conflict)
                await self._publish(session, event)
                conflict_followups = await self.agent_runtime.agent.handle_runtime_event(
                    session.session_id,
                    event=conflict,
                    context={
                        "state": session.context.state_summary_for_agent(),
                        "messages": session.context.as_chat_messages(),
                    },
                )
            else:
                applied = True
                await self._publish(session, event)
                await self._publish_state_applied(
                    session,
                    source="agent",
                    state_version=result.state_version,
                    based_on_version=int(based_on),
                )
        for followup in conflict_followups:
            if await self._emit_agent_event(session, followup):
                applied = True
        return applied

    async def _process_client_action_result(
        self, session: SessionRecord, payload: _ClientActionResult
    ) -> None:
        meta = self._base_metadata(session, source="client")
        if payload.outcome == "applied":
            event = ActionRouter.applied_event(
                metadata=meta,
                action_id=payload.action_id,
                name=payload.name,
                result=payload.result,
            )
            session.action_router.resolve(payload.action_id, "applied")
        else:
            event = ActionRouter.failed_event(
                metadata=meta,
                action_id=payload.action_id,
                name=payload.name,
                reason=payload.reason or "failed",
            )
            session.action_router.resolve(payload.action_id, "failed")
        await self._publish(session, event)

    async def _process_client_app_event(
        self, session: SessionRecord, name: str, payload: dict[str, Any]
    ) -> None:
        if name == "approval.grant":
            await self._handle_approval_grant(session, payload)
            return
        if name == "approval.reject":
            await self._handle_approval_reject(session, payload)
            return
        await self._publish(
            session,
            RelayEvent(
                type=EventType.METRIC,
                metadata=self._base_metadata(session, source="client"),
                payload={"name": f"app.{name}", "value": 1.0, "details": payload},
            ),
        )

    @staticmethod
    def _expected_approver_token() -> str:
        return os.environ.get("RELAY_DEV_APPROVER_TOKEN", "dev-approver")

    async def _handle_approval_reject(
        self, session: SessionRecord, payload: dict[str, Any]
    ) -> None:
        approval_id = str(payload.get("approval_id", ""))
        record = session.hitl_manager.reject(approval_id)
        if record is None:
            return
        await self._publish(
            session,
            RelayEvent(
                type=EventType.APPROVAL_REJECTED,
                metadata=self._base_metadata(session, source="client"),
                payload={
                    "approval_id": approval_id,
                    "tool_name": record.tool_name,
                    "lifecycle_stage": record.lifecycle_stage.value,
                },
            ),
        )

    async def _handle_approval_grant(
        self, session: SessionRecord, payload: dict[str, Any]
    ) -> None:
        approval_id = str(payload.get("approval_id", ""))
        auth_proof = str(payload.get("auth_proof", ""))
        if auth_proof != self._expected_approver_token():
            await self._publish(
                session,
                RelayEvent(
                    type=EventType.ERROR,
                    metadata=self._base_metadata(session, source="client"),
                    payload={
                        "message": "invalid_approver_credentials",
                        "approval_id": approval_id,
                    },
                ),
            )
            return
        record = session.hitl_manager.grant(approval_id, auth_proof=auth_proof)
        if record is None:
            return
        await self._publish(
            session,
            RelayEvent(
                type=EventType.APPROVAL_GRANTED,
                metadata=self._base_metadata(session, source="client"),
                payload={
                    "approval_id": approval_id,
                    "tool_name": record.tool_name,
                    "lifecycle_stage": record.lifecycle_stage.value,
                },
            ),
        )
        await self._execute_hitl_commit(session, approval_id)

    async def _execute_hitl_commit(self, session: SessionRecord, approval_id: str) -> None:
        record = session.hitl_manager.get(approval_id)
        if record is None or self.tool_executor is None:
            return
        session.hitl_manager.mark_commit(approval_id)
        commit_id = str(uuid4())
        await emit_trace_span(
            publish=lambda event: self._publish(session, event),
            base_metadata=lambda: self._base_metadata(session, source="hitl_manager"),
            stage=STAGE_HITL,
            trace_id=session.trace_id,
            attributes={"phase": "commit_start", "approval_id": approval_id},
        )
        commit_meta = self._base_metadata(session, source="hitl_manager")
        commit_meta.correlation_id = commit_id
        await self._publish(
            session,
            RelayEvent(
                type=EventType.COMMIT_STARTED,
                metadata=commit_meta,
                payload={
                    "commit_id": commit_id,
                    "approval_id": approval_id,
                    "tool_name": record.tool_name,
                    "lifecycle_stage": HitlLifecycleStage.COMMIT.value,
                },
            ),
        )
        base_meta = lambda: self._base_metadata(session, source="hitl_manager")

        async def publish(event: RelayEvent) -> None:
            await self._publish(session, event)

        commit_result = await self.tool_executor.execute(
            session.session_id,
            tool_name=record.tool_name,
            arguments=dict(record.arguments),
            approval_id=approval_id,
            publish=publish,
            base_metadata=base_meta,
        )
        if commit_result.get("error"):
            await self._publish(
                session,
                RelayEvent(
                    type=EventType.ERROR,
                    metadata=base_meta(),
                    payload={
                        "message": "commit_failed",
                        "error": commit_result.get("error"),
                        "commit_id": commit_id,
                    },
                ),
            )
            return

        backend_commit_id = str(commit_result.get("commit_id") or commit_id)
        verify_result = await self.tool_executor.execute(
            session.session_id,
            tool_name="verify_correction",
            arguments={
                "mortgage_id": record.arguments.get("mortgage_id"),
                "commit_id": backend_commit_id,
            },
            publish=publish,
            base_metadata=base_meta,
        )
        verified = bool(verify_result.get("verified"))
        session.hitl_manager.mark_verified(approval_id)
        await emit_trace_span(
            publish=publish,
            base_metadata=base_meta,
            stage=STAGE_HITL,
            trace_id=session.trace_id,
            attributes={
                "phase": "verify",
                "approval_id": approval_id,
                "verified": verified,
            },
        )
        verified_meta = base_meta()
        verified_meta.correlation_id = backend_commit_id
        await self._publish(
            session,
            RelayEvent(
                type=EventType.COMMIT_VERIFIED,
                metadata=verified_meta,
                payload={
                    "commit_id": backend_commit_id,
                    "approval_id": approval_id,
                    "verified": verified,
                    "mortgage": verify_result.get("mortgage"),
                    "lifecycle_stage": HitlLifecycleStage.VERIFY.value,
                },
            ),
        )
        if verified:
            async with session.context_lock:
                await self._apply_post_commit_state(session, verify_result, record.arguments)

    async def _apply_post_commit_state(
        self,
        session: SessionRecord,
        verify_result: dict[str, Any],
        commit_arguments: dict[str, Any],
    ) -> None:
        mortgage = verify_result.get("mortgage")
        if not isinstance(mortgage, dict):
            return
        state = dict(session.context.state)
        draft = dict(state.get("correction_draft") or {})
        draft["status"] = "committed"
        draft["mortgage_id"] = commit_arguments.get("mortgage_id") or draft.get("mortgage_id")
        state["correction_draft"] = draft
        state["screen"] = "mortgage_case"
        state["workflow"] = "correction_committed"
        state["case_summary"] = {
            **dict(state.get("case_summary") or {}),
            **mortgage,
        }
        session.context.apply_snapshot(state)
        await self._publish_state_applied(
            session,
            source="hitl_manager",
            state_version=session.context.state_version,
        )

    async def _enqueue_voice(self, session: SessionRecord, cmd: _CommandType, payload: Any) -> None:
        await session.queue.put((cmd, payload))

    async def _voice_done_future(self) -> asyncio.Future[None]:
        return asyncio.get_running_loop().create_future()

    async def notify_voice_speech_started(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if not session or session.ended:
            return
        if session.turn_manager.phase == TurnPhase.AGENT_SPEAKING:
            await self._handle_barge_in(session)
            return
        done = await self._voice_done_future()
        await self._enqueue_voice(session, _CommandType.VOICE_SPEECH_STARTED, _VoiceSignal(done=done))
        await done

    async def notify_voice_speech_ended(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if not session or session.ended:
            return
        done = await self._voice_done_future()
        await self._enqueue_voice(session, _CommandType.VOICE_SPEECH_ENDED, _VoiceSignal(done=done))
        await done

    async def notify_voice_transcript_delta(self, session_id: str, text: str) -> None:
        session = self._sessions.get(session_id)
        if not session or session.ended or not text:
            return
        done = await self._voice_done_future()
        await self._enqueue_voice(
            session,
            _CommandType.VOICE_TRANSCRIPT_DELTA,
            _VoiceTranscriptDelta(text=text, done=done),
        )
        await done

    async def notify_voice_transcript_final(self, session_id: str, text: str) -> None:
        session = self._sessions.get(session_id)
        if not session or session.ended:
            return
        done = await self._voice_done_future()
        await self._enqueue_voice(
            session,
            _CommandType.VOICE_TRANSCRIPT_FINAL,
            _VoiceTranscriptFinal(text=text.strip(), done=done),
        )
        await done

    async def cancel_voice_utterance(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if not session or session.ended:
            return
        done = await self._voice_done_future()
        await self._enqueue_voice(
            session, _CommandType.VOICE_CANCEL_UTTERANCE, _VoiceSignal(done=done)
        )
        await done

    async def _handle_barge_in(self, session: SessionRecord) -> None:
        """Runtime barge-in while actor may be blocked in voice playout (§7.1)."""
        if session.voice_turn_cancel is not None:
            session.voice_turn_cancel.cancel()
        await self._process_cancel_agent_playback(session)
        if session.interruption_manager.phase != InterruptionPhase.AGENT_PLAYOUT:
            try:
                session.interruption_manager.on_agent_playout_started()
            except Exception:
                pass
        try:
            session.interruption_manager.on_barge_in_detected()
        except Exception:
            logger.debug(
                "barge-in ignored (interruption phase) session_id=%s phase=%s",
                session.session_id,
                session.interruption_manager.phase,
            )
        interrupted_turn_id = session.turn_manager.active_turn_id
        try:
            session.turn_manager.on_barge_in()
        except TurnTransitionError:
            logger.debug(
                "barge-in turn transition skipped session_id=%s phase=%s",
                session.session_id,
                session.turn_manager.phase,
            )
        meta = self._base_metadata(session, source="interruption_manager")
        if interrupted_turn_id is not None:
            meta = meta.model_copy(update={"turn_id": interrupted_turn_id})
        await self._publish(
            session,
            RelayEvent(
                type=EventType.INTERRUPTION_DETECTED,
                metadata=meta.model_copy(update={"response_id": session.active_response_id}),
                payload=minimal_payload_for(EventType.INTERRUPTION_DETECTED),
            ),
        )
        await self._publish(
            session,
            RelayEvent(
                type=EventType.USER_SPEECH_STARTED,
                metadata=self._base_metadata(session, source="turn_detector"),
                payload=minimal_payload_for(EventType.USER_SPEECH_STARTED),
            ),
        )
        session.voice_capture_open = True
        session.voice_cancelled = False
        session.voice_transcript_buffer = ""
        self._cancel_utterance_commit_timer(session)

    async def _process_voice_speech_started(self, session: SessionRecord) -> None:
        if session.turn_manager.phase == TurnPhase.AGENT_SPEAKING:
            await self._handle_barge_in(session)
            return
        if session.turn_manager.phase == TurnPhase.USER_SPEAKING:
            self._cancel_stt_final_endpoint_timer(session)
            return
        session.voice_transcript_buffer = ""
        self._cancel_utterance_commit_timer(session)
        self._cancel_stt_final_endpoint_timer(session)
        try:
            session.turn_manager.on_user_speech_started()
        except TurnTransitionError:
            return
        await self._publish(
            session,
            RelayEvent(
                type=EventType.USER_SPEECH_STARTED,
                metadata=self._base_metadata(session, source="turn_detector"),
                payload=minimal_payload_for(EventType.USER_SPEECH_STARTED),
            ),
        )
        session.voice_capture_open = True
        session.voice_cancelled = False

    async def _process_voice_speech_ended(self, session: SessionRecord) -> None:
        self._cancel_stt_final_endpoint_timer(session)
        try:
            session.turn_manager.on_user_speech_ended()
        except TurnTransitionError:
            logger.debug(
                "ignore speech_ended session_id=%s phase=%s",
                session.session_id,
                session.turn_manager.phase,
            )
            return
        session.endpointing_started_at = time.perf_counter()
        session.user_stopped_speaking_at = time.perf_counter()
        await self._publish(
            session,
            RelayEvent(
                type=EventType.USER_SPEECH_ENDED,
                metadata=self._base_metadata(session, source="turn_detector"),
                payload=minimal_payload_for(EventType.USER_SPEECH_ENDED),
            ),
        )
        await self._arm_voice_utterance_commit(session)

    def _cancel_utterance_commit_timer(self, session: SessionRecord) -> None:
        task = session.utterance_commit_task
        session.utterance_commit_task = None
        if task is not None and not task.done():
            task.cancel()

    def _cancel_stt_final_endpoint_timer(self, session: SessionRecord) -> None:
        task = session.stt_final_endpoint_task
        session.stt_final_endpoint_task = None
        if task is not None and not task.done():
            task.cancel()

    async def _arm_stt_final_endpoint(self, session: SessionRecord) -> None:
        """When Silero never emits END, STT final + debounce still closes the utterance."""
        delay_ms = self._stt_final_endpoint_ms()
        self._cancel_stt_final_endpoint_timer(session)

        async def _fire() -> None:
            try:
                await asyncio.sleep(delay_ms / 1000.0)
                done = asyncio.get_running_loop().create_future()
                await session.queue.put(
                    (_CommandType.VOICE_STT_FINAL_ENDPOINT, _VoiceSignal(done=done))
                )
                await done
            except asyncio.CancelledError:
                return

        session.stt_final_endpoint_task = asyncio.create_task(_fire())

    async def _apply_stt_final_endpoint(self, session: SessionRecord) -> None:
        if session.turn_manager.phase != TurnPhase.USER_SPEAKING:
            return
        if not session.voice_transcript_buffer.strip():
            return
        await self._process_voice_speech_ended(session)

    async def _arm_voice_utterance_commit(self, session: SessionRecord) -> None:
        if session.turn_manager.phase != TurnPhase.ENDPOINTING:
            return
        delay_ms = self._utterance_commit_delay_ms()
        if delay_ms <= 0:
            await self._maybe_commit_voice_utterance(session)
            return
        self._cancel_utterance_commit_timer(session)

        async def _fire() -> None:
            try:
                await asyncio.sleep(delay_ms / 1000.0)
                done = asyncio.get_running_loop().create_future()
                await session.queue.put((_CommandType.VOICE_TRY_COMMIT, _VoiceSignal(done=done)))
                await done
            except asyncio.CancelledError:
                return

        session.utterance_commit_task = asyncio.create_task(_fire())

    async def _maybe_commit_voice_utterance(self, session: SessionRecord) -> None:
        if session.voice_cancelled or session.ended:
            return
        if session.turn_manager.phase != TurnPhase.ENDPOINTING:
            return
        text = session.voice_transcript_buffer.strip()
        if not text:
            return
        session.voice_transcript_buffer = ""
        await self._start_voice_turn(session, user_text=text)

    async def _process_voice_transcript_delta(self, session: SessionRecord, text: str) -> None:
        self._cancel_stt_final_endpoint_timer(session)
        await self._publish(
            session,
            RelayEvent(
                type=EventType.TRANSCRIPT_DELTA,
                metadata=self._base_metadata(session, source="speech_to_text"),
                payload={"text": text, "is_final": False},
            ),
        )

    async def _ensure_voice_endpointing(self, session: SessionRecord) -> None:
        """Align FSM when STT finalizes before or without Silero ``USER_SPEECH_ENDED``."""
        phase = session.turn_manager.phase
        if phase == TurnPhase.ENDPOINTING:
            return
        if phase == TurnPhase.USER_SPEAKING:
            await self._process_voice_speech_ended(session)
            return
        if phase == TurnPhase.IDLE:
            try:
                session.turn_manager.on_user_speech_started()
            except TurnTransitionError:
                return
            await self._publish(
                session,
                RelayEvent(
                    type=EventType.USER_SPEECH_STARTED,
                    metadata=self._base_metadata(session, source="turn_detector"),
                    payload=minimal_payload_for(EventType.USER_SPEECH_STARTED),
                ),
            )
            session.voice_capture_open = True
            await self._process_voice_speech_ended(session)

    async def _process_voice_transcript_final(self, session: SessionRecord, text: str) -> None:
        if not text.strip():
            try:
                session.turn_manager.cancel_utterance()
            except TurnTransitionError:
                pass
            session.endpointing_started_at = None
            session.voice_transcript_buffer = ""
            return

        await self._publish(
            session,
            RelayEvent(
                type=EventType.TRANSCRIPT_FINAL,
                metadata=self._base_metadata(session, source="speech_to_text"),
                payload={"text": text, "is_final": True},
            ),
        )

        if session.voice_cancelled:
            logger.info(
                "voice transcript ignored (cancelled) session_id=%s text=%r",
                session.session_id,
                text[:80],
            )
            return

        session.voice_transcript_buffer = self._merge_voice_transcript(
            session.voice_transcript_buffer,
            text,
        )

        phase = session.turn_manager.phase
        if phase == TurnPhase.USER_SPEAKING:
            await self._arm_stt_final_endpoint(session)
            return

        if phase == TurnPhase.AGENT_SPEAKING:
            await self._handle_barge_in(session)
            session.voice_transcript_buffer = self._merge_voice_transcript(
                session.voice_transcript_buffer,
                text,
            )
            await self._arm_stt_final_endpoint(session)
            return

        await self._ensure_voice_endpointing(session)

        if session.endpointing_started_at is not None:
            delay_ms = (time.perf_counter() - session.endpointing_started_at) * 1000.0
            session.endpointing_started_at = None
            await self._publish(
                session,
                RelayEvent(
                    type=EventType.METRIC,
                    metadata=self._base_metadata(session, source="turn_detector"),
                    payload={"name": "turn.endpointing_delay_ms", "value": delay_ms},
                ),
            )

        await self._arm_voice_utterance_commit(session)

    async def _await_voice_response_task(self, session: SessionRecord) -> None:
        task = session.voice_response_task
        if task is None:
            return
        session.voice_response_task = None
        if not task.done():
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.exception(
                    "voice response task failed session_id=%s",
                    session.session_id,
                )

    async def _start_voice_turn(self, session: SessionRecord, *, user_text: str) -> None:
        await self._await_voice_response_task(session)
        self._cancel_utterance_commit_timer(session)
        self._cancel_stt_final_endpoint_timer(session)
        if session.turn_manager.phase == TurnPhase.USER_SPEAKING:
            await self._process_voice_speech_ended(session)
        turn_id = str(uuid4())
        session.context.begin_turn(turn_id)
        try:
            session.turn_manager.begin_turn(turn_id, voice=True)
        except TurnTransitionError:
            logger.info(
                "voice turn not started session_id=%s phase=%s text=%r",
                session.session_id,
                session.turn_manager.phase,
                user_text[:80],
            )
            try:
                session.turn_manager.cancel_utterance()
            except TurnTransitionError:
                pass
            return

        meta = self._base_metadata(session, source="turn_manager")
        await self._publish(
            session,
            RelayEvent(
                type=EventType.TURN_STARTED,
                metadata=meta.model_copy(update={"turn_id": turn_id}),
                payload=minimal_payload_for(EventType.TURN_STARTED),
            ),
        )
        await self._publish(
            session,
            RelayEvent(
                type=EventType.TURN_PROCESSING,
                metadata=self._base_metadata(session, source="turn_manager").model_copy(
                    update={"turn_id": turn_id}
                ),
                payload=minimal_payload_for(EventType.TURN_PROCESSING),
            ),
        )
        await emit_trace_span(
            publish=lambda event: self._publish(session, event),
            base_metadata=lambda: self._base_metadata(session, source="turn_manager"),
            stage=STAGE_STT,
            trace_id=session.trace_id,
            turn_id=turn_id,
            attributes={"chars": len(user_text)},
        )

        session.voice_turn_cancel = TurnCancellation()

        async def _run() -> None:
            try:
                await self._run_voice_response_turn(
                    session, turn_id=turn_id, user_text=user_text
                )
            finally:
                if session.voice_response_task is asyncio.current_task():
                    session.voice_response_task = None
                session.voice_capture_open = False
                session.voice_cancelled = False
                session.user_stopped_speaking_at = None

        session.voice_response_task = asyncio.create_task(_run())

    async def _process_voice_cancel(self, session: SessionRecord) -> None:
        if session.turn_manager.phase == TurnPhase.AGENT_SPEAKING:
            await self._process_cancel_agent_playback(session)
            return
        try:
            session.turn_manager.cancel_utterance()
        except TurnTransitionError:
            return
        session.endpointing_started_at = None
        session.voice_capture_open = False
        session.voice_cancelled = True

    async def _process_cancel_agent_playback(self, session: SessionRecord) -> None:
        if session.voice_turn_cancel is not None:
            session.voice_turn_cancel.cancel()
        if self.realtime_transport is not None:
            await self.realtime_transport.cancel_output(session.session_id)
        if self.text_to_speech is not None:
            await self.text_to_speech.cancel(session.session_id)

    async def cancel_agent_playback(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if not session or session.ended:
            return
        if session.voice_turn_cancel is not None:
            session.voice_turn_cancel.cancel()
            await self._process_cancel_agent_playback(session)
            return
        done = await self._voice_done_future()
        await self._enqueue_voice(session, _CommandType.VOICE_CANCEL_AGENT, _VoiceSignal(done=done))
        await done

    def _attach_playback_handlers(self, session: SessionRecord) -> None:
        if session.playback_tracker is None:
            return

        async def on_playback(kind: str, position_ms: float) -> None:
            turn_id = session.turn_manager.active_turn_id
            if turn_id is None:
                return
            meta = self._base_metadata(session, source="playback_tracker").model_copy(
                update={
                    "turn_id": turn_id,
                    "response_id": session.active_response_id,
                }
            )
            if kind == "SPEECH_PROGRESS":
                tracker = session.playback_tracker
                heard_text = ""
                if tracker is not None and tracker.generated_text:
                    estimated_total = max(
                        tracker.total_audio_ms,
                        len(tracker.generated_text) * 45.0,
                    )
                    heard_text = InterruptionManager.heard_prefix(
                        generated_text=tracker.generated_text,
                        delivered_ms=position_ms,
                        total_audio_ms=estimated_total,
                    )
                await self._publish(
                    session,
                    RelayEvent(
                        type=EventType.SPEECH_PROGRESS,
                        metadata=meta,
                        payload={"position_ms": position_ms, "heard_text": heard_text},
                    ),
                )
            elif kind == "SPEECH_STOPPED":
                await self._publish(
                    session,
                    RelayEvent(
                        type=EventType.SPEECH_STOPPED,
                        metadata=meta,
                        payload=minimal_payload_for(EventType.SPEECH_STOPPED),
                    ),
                )

        session.playback_tracker.set_progress_handler(on_playback)

    async def _publish_speech_started(self, session: SessionRecord, *, turn_id: str) -> None:
        await self._publish(
            session,
            RelayEvent(
                type=EventType.SPEECH_STARTED,
                metadata=self._base_metadata(session, source="playback_tracker").model_copy(
                    update={
                        "turn_id": turn_id,
                        "response_id": session.active_response_id,
                    }
                ),
                payload=minimal_payload_for(EventType.SPEECH_STARTED),
            ),
        )

    async def _commit_interrupted_response(
        self,
        session: SessionRecord,
        *,
        turn_id: str,
        generated_text: str,
    ) -> None:
        if session.playback_tracker is None:
            heard_text = ""
        else:
            session.playback_tracker.note_generated_text(generated_text)
            heard_text = session.playback_tracker.finalize_heard(interrupted=True)

        meta = self._base_metadata(session, source="interruption_manager").model_copy(
            update={
                "turn_id": turn_id,
                "response_id": session.active_response_id,
            }
        )
        await self._publish(
            session,
            RelayEvent(
                type=EventType.RESPONSE_INTERRUPTED,
                metadata=meta,
                payload={
                    "generated_text": generated_text,
                    "heard_text": heard_text,
                    "delivered_ms": session.playback_tracker.delivered_ms
                    if session.playback_tracker
                    else 0.0,
                },
            ),
        )
        await self._publish(
            session,
            RelayEvent(
                type=EventType.HEARD_TEXT_COMMITTED,
                metadata=meta,
                payload={"text": heard_text, "generated_text": generated_text},
            ),
        )
        session.context.commit_assistant_heard(
            generated_text=generated_text,
            heard_text=heard_text,
        )
        session.context.active_turn_id = None
        try:
            session.interruption_manager.on_interrupt_settled()
        except Exception:
            session.interruption_manager.on_idle()

    async def _publish_metric(self, session: SessionRecord, name: str, value: float) -> None:
        await self._publish(
            session,
            RelayEvent(
                type=EventType.METRIC,
                metadata=self._base_metadata(session, source="agent_runtime"),
                payload={"name": name, "value": value},
            ),
        )

    async def _run_voice_response_turn(
        self,
        session: SessionRecord,
        *,
        turn_id: str,
        user_text: str,
    ) -> None:
        await emit_trace_span(
            publish=lambda event: self._publish(session, event),
            base_metadata=lambda: self._base_metadata(session, source="voice_turn"),
            stage=STAGE_STT,
            trace_id=session.trace_id,
            turn_id=turn_id,
            attributes={"chars": len(user_text), "path": "voice_response"},
        )
        def next_meta(*, source: str) -> RelayEventMetadata:
            return self._base_metadata(session, source=source)

        use_tts = (
            self.text_to_speech is not None
            and self.realtime_transport is not None
            and await self.realtime_transport.is_connected(session.session_id)
        )

        if session.voice_turn_cancel is None:
            session.voice_turn_cancel = TurnCancellation()
        else:
            session.voice_turn_cancel.reset()
        cancel = session.voice_turn_cancel
        token_queue: asyncio.Queue[str | None] = asyncio.Queue()
        agent_audio_started = False
        speech_stream = SpeechTextStream()

        async def on_token(token: str) -> None:
            if session.playback_tracker is not None:
                session.playback_tracker.append_generated_text(token)
            spoken = speech_stream.push(token)
            if spoken:
                await token_queue.put(spoken)

        async def on_metric(name: str, value: float) -> None:
            await self._publish_metric(session, name, value)

        async def on_playout_started() -> None:
            nonlocal agent_audio_started
            agent_audio_started = True
            session.turn_manager.enter_agent_speaking(turn_id)
            try:
                session.interruption_manager.on_agent_playout_started()
            except Exception:
                session.interruption_manager.on_idle()
                session.interruption_manager.on_agent_playout_started()
            await emit_trace_span(
                publish=lambda event: self._publish(session, event),
                base_metadata=lambda: self._base_metadata(session, source="voice_output"),
                stage=STAGE_TTS,
                trace_id=session.trace_id,
                turn_id=turn_id,
                attributes={"phase": "playout_start"},
            )
            await self._publish_speech_started(session, turn_id=turn_id)

        async def tts_worker() -> None:
            if not use_tts:
                return
            session.playback_tracker.reset()
            await play_tts_stream(
                session_id=session.session_id,
                text_tokens=queue_to_text_iterator(token_queue),
                tts=self.text_to_speech,
                transport=self.realtime_transport,
                playback=session.playback_tracker,
                config=self.voice_output,
                cancel=cancel,
                on_metric=on_metric,
                speech_started_at=session.user_stopped_speaking_at,
                on_playout_started=on_playout_started,
            )

        tts_task = asyncio.create_task(tts_worker()) if use_tts else None

        async def publish_turn(event: RelayEvent) -> None:
            if event.type == EventType.RESPONSE_STARTED:
                session.active_response_id = event.metadata.response_id
            await self._publish(session, event)

        async def emit_agent_event(event: RelayEvent) -> bool:
            return await self._emit_agent_event(session, event)

        assistant_text = ""
        try:
            assistant_text = await self.agent_runtime.run_streaming_turn(
                session_id=session.session_id,
                turn_id=turn_id,
                user_text=user_text,
                context=session.context,
                base_metadata=lambda source="agent_runtime": next_meta(source=source),
                publish=publish_turn,
                include_user_transcript=False,
                on_token=on_token if use_tts else None,
                cancel=cancel,
                on_metric=on_metric,
                action_router=session.action_router,
                emit_agent_event=emit_agent_event,
            )
            if session.playback_tracker is not None:
                session.playback_tracker.note_generated_text(assistant_text)
        finally:
            tail = speech_stream.flush()
            if tail:
                await token_queue.put(tail)
            await token_queue.put(None)
            if tts_task is not None:
                await tts_task

        interrupted = cancel.is_cancelled
        if interrupted:
            await self._commit_interrupted_response(
                session,
                turn_id=turn_id,
                generated_text=assistant_text,
            )
        else:
            if (
                use_tts
                and assistant_text.strip()
                and not agent_audio_started
            ):
                logger.warning(
                    "voice turn had no TTS playout; batch fallback session_id=%s turn_id=%s",
                    session.session_id,
                    turn_id,
                )
                await self._speak_assistant_if_voice_connected(
                    session, turn_id=turn_id, assistant_text=assistant_text
                )
                agent_audio_started = session.turn_manager.phase == TurnPhase.AGENT_SPEAKING
            if session.playback_tracker is not None:
                session.playback_tracker.finalize_heard(interrupted=False)
            session.context.append_assistant(assistant_text)
            session.interruption_manager.on_idle()
            if agent_audio_started and session.turn_manager.phase == TurnPhase.AGENT_SPEAKING:
                session.turn_manager.complete_turn(turn_id)
            elif session.turn_manager.phase == TurnPhase.PROCESSING:
                session.turn_manager.complete_turn(turn_id)

        await self._publish(
            session,
            RelayEvent(
                type=EventType.TURN_COMPLETED,
                metadata=self._base_metadata(session, source="turn_manager").model_copy(
                    update={"turn_id": turn_id}
                ),
                payload=minimal_payload_for(EventType.TURN_COMPLETED),
            ),
        )
        session.voice_turn_cancel = None
        session.active_response_id = None

    async def create_dev_session(
        self,
        *,
        project_id: str,
        agent_id: str,
    ) -> tuple[SessionRecord, list[RelayEvent]]:
        session_id = str(uuid4())
        trace_id = self.trace_manager.new_trace_id()
        dev_token = token_urlsafe(32)
        expires = datetime.now(timezone.utc) + timedelta(seconds=self.dev_token_ttl_seconds)
        session = SessionRecord(
            session_id=session_id,
            project_id=project_id,
            agent_id=agent_id,
            trace_id=trace_id,
            dev_token=dev_token,
            token_expires_at=expires,
            playback_tracker=PlaybackTracker(session_id=session_id),
        )
        self._attach_playback_handlers(session)
        if self.session_lock is not None:
            acquired = await self.session_lock.acquire(
                session_id, owner=session.lock_owner, ttl_seconds=self.dev_token_ttl_seconds
            )
            if not acquired:
                raise RuntimeError("session lock not acquired")
        self._sessions[session_id] = session
        session.worker = asyncio.create_task(self._run_session_actor(session))

        started = RelayEvent(
            type=EventType.SESSION_STARTED,
            metadata=self._base_metadata(session, source="session_manager"),
            payload=minimal_payload_for(EventType.SESSION_STARTED),
        )
        ready = RelayEvent(
            type=EventType.SESSION_READY,
            metadata=self._base_metadata(session, source="session_manager"),
            payload=minimal_payload_for(EventType.SESSION_READY),
        )
        for event in (started, ready):
            await self._publish(session, event)
        return session, [started, ready]

    async def submit_user_text(self, session_id: str, text: str) -> None:
        session = self._sessions.get(session_id)
        if not session or session.ended:
            raise KeyError("session not found")
        if not text.strip():
            raise ValueError("empty text")
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        await session.queue.put((_CommandType.USER_TEXT, _UserTextCommand(text=text.strip(), done=done)))
        await done

    async def submit_client_state_snapshot(self, session_id: str, state: dict[str, Any]) -> None:
        """Apply human UI state immediately (§10.3) — not queued behind in-flight turns."""
        session = self._sessions.get(session_id)
        if not session or session.ended:
            raise KeyError("session not found")
        async with session.context_lock:
            await self._process_client_state_snapshot(session, dict(state))

    async def submit_client_action_result(
        self,
        session_id: str,
        *,
        action_id: str,
        name: str,
        outcome: str,
        reason: str | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        """Correlate UI actions immediately — do not queue behind in-flight turns."""
        session = self._sessions.get(session_id)
        if not session or session.ended:
            raise KeyError("session not found")
        payload = _ClientActionResult(
            action_id=action_id,
            name=name,
            outcome=outcome,
            reason=reason,
            result=result,
            done=asyncio.get_running_loop().create_future(),
        )
        async with session.context_lock:
            await self._process_client_action_result(session, payload)

    async def submit_client_app_event(
        self, session_id: str, *, name: str, payload: dict[str, Any]
    ) -> None:
        session = self._sessions.get(session_id)
        if not session or session.ended:
            raise KeyError("session not found")
        if name in ("approval.grant", "approval.reject"):
            async with session.context_lock:
                await self._process_client_app_event(session, name, dict(payload))
            return
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        await session.queue.put(
            (_CommandType.CLIENT_APP_EVENT, _ClientAppEvent(name=name, payload=payload, done=done))
        )
        await done

    async def record_transport_metric(self, session_id: str, name: str, value: float) -> None:
        session = self._sessions.get(session_id)
        if not session or session.ended:
            return
        await self._publish(
            session,
            RelayEvent(
                type=EventType.METRIC,
                metadata=self._base_metadata(session, source="realtime_transport"),
                payload={"name": name, "value": value},
            ),
        )

    async def record_transport_state(self, session_id: str, state: str) -> None:
        session = self._sessions.get(session_id)
        if not session or session.ended:
            return
        await self._publish(
            session,
            RelayEvent(
                type=EventType.METRIC,
                metadata=self._base_metadata(session, source="realtime_transport"),
                payload={"name": "transport.connection_state", "value": 1.0, "state": state},
            ),
        )

    async def start_realtime(self, session_id: str, offer: dict[str, Any]) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if not session or session.ended:
            raise KeyError("session not found")
        if self.realtime_transport is None:
            raise RuntimeError("realtime transport not configured")
        return await self.realtime_transport.connect(session_id, offer=offer)

    async def patch_realtime_ice(
        self,
        session_id: str,
        *,
        pc_id: str,
        candidates: list[dict[str, Any]],
    ) -> None:
        session = self._sessions.get(session_id)
        if not session or session.ended:
            raise KeyError("session not found")
        if self.realtime_transport is None:
            raise RuntimeError("realtime transport not configured")
        await self.realtime_transport.patch_ice(session_id, pc_id=pc_id, candidates=candidates)

    async def end_session(self, session_id: str) -> None:
        session = self._sessions.get(session_id)
        if not session or session.ended:
            return
        if self.realtime_transport is not None:
            await self.realtime_transport.disconnect(session_id)
        session.ended = True
        if session.voice_turn_cancel is not None:
            session.voice_turn_cancel.cancel()
        await self._await_voice_response_task(session)
        await session.queue.put((_CommandType.SHUTDOWN, None))
        if session.worker is not None:
            await session.worker
        if self.session_lock is not None:
            await self.session_lock.release(session_id, owner=session.lock_owner)
        ended = RelayEvent(
            type=EventType.SESSION_ENDED,
            metadata=self._base_metadata(session, source="session_manager"),
            payload=minimal_payload_for(EventType.SESSION_ENDED),
        )
        await self._publish(session, ended)

    def validate_dev_token(self, session_id: str, token: str) -> bool:
        session = self._sessions.get(session_id)
        if not session or session.dev_token != token or session.ended:
            return False
        return datetime.now(timezone.utc) < session.token_expires_at

    def get(self, session_id: str) -> SessionRecord | None:
        return self._sessions.get(session_id)
