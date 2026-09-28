"""Gateway dependencies and wiring."""

from __future__ import annotations

import asyncio
import os

from relay_adapter_models_openai import OpenAIProvider
from relay_adapter_tools_http import HttpToolExecutor
from relay_mortgage_agent import MortgageServicingAgent
from relay_mortgage_agent.tools_local import LocalMortgageToolExecutor
from relay_adapter_persistence_postgres import PostgresEventStore
from relay_adapter_persistence_redis import RedisSessionLock
from relay_adapter_realtime_pipecat import PipecatSmallWebRtcTransport
from relay_adapter_realtime_pipecat.voice_pipeline import VoicePipelineHooks
from relay_adapter_speech_deepgram import build_text_to_speech_provider
from pipecat.transports.smallwebrtc.connection import IceServer
from relay_runtime import (
    AgentRuntime,
    LocalSessionLock,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    RegistryToolExecutor,
    SessionManager,
    ToolRegistry,
    TraceManager,
)
from relay_runtime.voice_output import VoiceOutputConfig
from relay_runtime.ports.events import EventStore
from relay_runtime.ports.tools import ToolExecutor
from relay_mortgage_agent.tool_definitions import register_mortgage_tools


def _build_event_store() -> EventStore:
    if os.environ.get("RELAY_DATABASE_URL"):
        return PostgresEventStore()
    return MemoryEventStore()


def _build_session_lock() -> LocalSessionLock | RedisSessionLock:
    if os.environ.get("RELAY_REDIS_URL"):
        return RedisSessionLock()
    return LocalSessionLock()


def _build_tool_delegate() -> ToolExecutor:
    url = os.environ.get("RELAY_MORTGAGE_TOOLS_URL", "").strip()
    if url:
        return HttpToolExecutor(base_url=url)
    return LocalMortgageToolExecutor()


def _build_registry_executor() -> RegistryToolExecutor:
    registry = ToolRegistry()
    register_mortgage_tools(registry)
    timeout = float(os.environ.get("RELAY_TOOL_TIMEOUT_SECONDS", "30"))
    return RegistryToolExecutor(
        registry=registry,
        delegate=_build_tool_delegate(),
        trace_manager=TraceManager(),
        default_timeout_seconds=timeout,
    )


event_store = _build_event_store()
event_gateway = PersistingEventGateway(event_store)
model_router = ModelRouter(OpenAIProvider())
registry_tool_executor = _build_registry_executor()
agent_runtime = AgentRuntime(
    model_router=model_router,
    agent=MortgageServicingAgent(model_router),
    tool_executor=registry_tool_executor,
)
session_lock = _build_session_lock()


def _build_realtime_transport() -> PipecatSmallWebRtcTransport | None:
    if os.environ.get("RELAY_DISABLE_WEBRTC", "").lower() in ("1", "true", "yes"):
        return None
    ice_url = os.environ.get("RELAY_ICE_STUN_URL", "stun:stun.l.google.com:19302")
    ice_servers = [IceServer(urls=ice_url)] if ice_url else None
    sample_rate = int(os.environ.get("DEEPGRAM_TTS_SAMPLE_RATE", "24000"))
    return PipecatSmallWebRtcTransport(
        ice_servers=ice_servers,
        voice_hooks=None,
        agent_output_sample_rate=sample_rate,
    )


realtime_transport = _build_realtime_transport()
text_to_speech = build_text_to_speech_provider()
voice_output = VoiceOutputConfig(
    sample_rate=int(os.environ.get("DEEPGRAM_TTS_SAMPLE_RATE", "24000")),
)
session_manager = SessionManager(
    event_gateway=event_gateway,
    agent_runtime=agent_runtime,
    tool_executor=registry_tool_executor,
    session_lock=session_lock,
    realtime_transport=realtime_transport,
    text_to_speech=text_to_speech,
    voice_output=voice_output,
)
registry_tool_executor.hitl_for_session = lambda session_id: (
    session_manager._sessions[session_id].hitl_manager
    if session_id in session_manager._sessions
    else None
)
if realtime_transport is not None:
    realtime_transport.on_metric = session_manager.record_transport_metric
    realtime_transport.on_connection_state = session_manager.record_transport_state
    realtime_transport.voice_hooks = VoicePipelineHooks(
        on_speech_started=session_manager.notify_voice_speech_started,
        on_speech_ended=session_manager.notify_voice_speech_ended,
        on_transcript_delta=session_manager.notify_voice_transcript_delta,
        on_transcript_final=session_manager.notify_voice_transcript_final,
    )

_voice_prewarm_task: asyncio.Task[None] | None = None


async def _prewarm_voice_stack() -> None:
    from pipecat.utils.prewarm import warm_deferred_imports
    from relay_adapter_speech_silero import build_turn_detector

    await asyncio.to_thread(warm_deferred_imports)
    await asyncio.to_thread(build_turn_detector)


async def startup() -> None:
    global _voice_prewarm_task
    if isinstance(event_store, PostgresEventStore):
        await event_store.connect()
    # Pipecat/Silero prewarm can take 60–90s; do not block HTTP /health or WebSocket connect.
    if realtime_transport is not None and _voice_prewarm_task is None:
        _voice_prewarm_task = asyncio.create_task(_prewarm_voice_stack())


async def shutdown() -> None:
    global _voice_prewarm_task
    if _voice_prewarm_task is not None:
        _voice_prewarm_task.cancel()
        try:
            await _voice_prewarm_task
        except asyncio.CancelledError:
            pass
        _voice_prewarm_task = None
    if realtime_transport is not None:
        await realtime_transport.close()
    if isinstance(event_store, PostgresEventStore):
        await event_store.close()
    if isinstance(session_lock, RedisSessionLock):
        await session_lock.close()
