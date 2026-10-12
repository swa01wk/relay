"""Gateway dependencies and wiring."""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from collections.abc import Callable
from pathlib import Path

from relay_adapter_models_openai import OpenAIProvider
from relay_adapter_observability_otel import OtelTraceBridge, tracer_provider_from_env
from relay_adapter_observability_prometheus import PrometheusMetricsBridge
from relay_adapter_tools_http import HttpToolExecutor
from relay_mortgage_agent import MortgageServicingAgent
from relay_mortgage_agent.tools_local import LocalMortgageToolExecutor
from relay_adapter_persistence_postgres import PostgresEventStore
from relay_adapter_persistence_redis import RedisSessionLock
from relay_adapter_realtime_pipecat import PipecatSmallWebRtcTransport
from relay_adapter_realtime_pipecat.voice_pipeline import VoicePipelineHooks
from relay_adapter_speech_deepgram import build_text_to_speech_provider
from pipecat.transports.smallwebrtc.connection import IceServer
from relay_runtime.event_redaction import modes_from_env, redactor
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
from relay_gateway.manifests import load_agent_manifests
from relay_runtime.ports.agent import AgentAdapter
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


tool_delegate = _build_tool_delegate()


def _build_registry_executor() -> RegistryToolExecutor:
    registry = ToolRegistry()
    register_mortgage_tools(registry)
    timeout = float(os.environ.get("RELAY_TOOL_TIMEOUT_SECONDS", "30"))
    return RegistryToolExecutor(
        registry=registry,
        delegate=tool_delegate,
        trace_manager=TraceManager(),
        default_timeout_seconds=timeout,
    )


logger = logging.getLogger(__name__)

event_store = _build_event_store()
# Postgres round trips must not sit on the token-streaming path; batch them behind delivery.
event_gateway = PersistingEventGateway(
    event_store,
    write_behind=isinstance(event_store, PostgresEventStore),
    # RELAY_EVENT_STORE_REDACT=text,data limits what the log keeps; the live stream is unaffected.
    stored_copy=redactor(modes_from_env()),
)
model_provider = OpenAIProvider()
model_router = ModelRouter(model_provider)
registry_tool_executor = _build_registry_executor()
agent_runtime = AgentRuntime(
    model_router=model_router,
    agent=MortgageServicingAgent(model_router),
    tool_executor=registry_tool_executor,
)
session_lock = _build_session_lock()


extra_agent_runtimes: dict[str, AgentRuntime] = {}
extra_tool_delegates: list[ToolExecutor] = []


def add_tool_agent(
    agent_id: str,
    *,
    build_agent: Callable[[ModelRouter], AgentAdapter],
    register_tools: Callable[[ToolRegistry], None],
    tools_url_env: str,
    local_executor: ToolExecutor | None = None,
) -> None:
    """Serve ``agent_id`` with an agent whose tools live behind ``$tools_url_env``.

    Without the URL the ``local_executor`` (in-process tools) is used; with neither, the agent
    is skipped. Sessions created with this ``agent_id`` use this agent and these tools.
    """
    url = os.environ.get(tools_url_env, "").strip()
    delegate: ToolExecutor | None = HttpToolExecutor(base_url=url) if url else local_executor
    if delegate is None:
        return
    registry = ToolRegistry()
    register_tools(registry)
    extra_tool_delegates.append(delegate)
    extra_agent_runtimes[agent_id] = AgentRuntime(
        model_router=model_router,
        agent=build_agent(model_router),
        tool_executor=RegistryToolExecutor(
            registry=registry,
            delegate=delegate,
            trace_manager=TraceManager(),
            default_timeout_seconds=float(os.environ.get("RELAY_TOOL_TIMEOUT_SECONDS", "30")),
        ),
    )


# Most agents are declarative: ``$RELAY_AGENTS_DIR/*.yaml`` manifests loaded at startup (see
# manifests.py). ``add_tool_agent`` is for agents that need custom Python.
AGENTS_DIR = Path(os.environ.get("RELAY_AGENTS_DIR", "agents"))



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
    agent_runtimes=extra_agent_runtimes,
    tool_executor=registry_tool_executor,
    session_lock=session_lock,
    realtime_transport=realtime_transport,
    text_to_speech=text_to_speech,
    voice_output=voice_output,
)


def _agent_label(session_id: str) -> str | None:
    """Metrics label: registered agent ids only (agent_id is client-supplied text)."""
    session = session_manager.get(session_id)
    if session is None:
        return None
    return session.agent_id if session.agent_id in session_manager.agent_runtimes else "default"


# Metrics are derived from the event stream; one subscriber sees every session.
metrics_bridge = PrometheusMetricsBridge(
    agent_for_session=_agent_label,
    active_sessions=lambda: len(session_manager._sessions),
)
event_gateway.subscribe("*", metrics_bridge.on_event)

# Traces are exported only when an OTLP endpoint is configured (OTEL_EXPORTER_OTLP_ENDPOINT).
_tracer_provider = tracer_provider_from_env()
trace_bridge = OtelTraceBridge(_tracer_provider, agent_for_session=_agent_label) if _tracer_provider else None
if trace_bridge is not None:
    event_gateway.subscribe("*", trace_bridge.on_event)

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
_retention_task: asyncio.Task[None] | None = None


def _warm_pipecat_deferred_imports() -> None:
    # pipecat 1.11 ships ``utils.prewarm``; 1.12 dropped it but still lazily loads
    # the NLTK sentence tokenizer on the first bot sentence. Warm whichever exists.
    try:
        from pipecat.utils.prewarm import warm_deferred_imports
    except ImportError:
        try:
            from pipecat.utils.string import _sent_tokenizer

            _sent_tokenizer()
        except Exception:
            pass
        return
    warm_deferred_imports()


async def _prewarm_voice_stack() -> None:
    from relay_adapter_speech_silero import build_turn_detector

    await asyncio.to_thread(_warm_pipecat_deferred_imports)
    await asyncio.to_thread(build_turn_detector)


def _retention_days() -> float:
    raw = os.environ.get("RELAY_EVENT_RETENTION_DAYS", "").strip()
    return float(raw) if raw else 0.0


async def _retention_loop(days: float) -> None:
    """Delete events older than the retention window, now and then hourly."""
    while True:
        try:
            await event_gateway.flush()
            removed = await event_store.delete_older_than(datetime.now(timezone.utc) - timedelta(days=days))
            if removed:
                logger.info("event retention removed %d events older than %g days", removed, days)
        except Exception:
            logger.exception("event retention failed")
        await asyncio.sleep(3600)


async def startup() -> None:
    global _voice_prewarm_task, _retention_task
    if isinstance(event_store, PostgresEventStore):
        await event_store.connect()
    await load_agent_manifests(
        AGENTS_DIR,
        model_router=model_router,
        runtimes=extra_agent_runtimes,
        delegates=extra_tool_delegates,
    )
    if _retention_days() > 0 and _retention_task is None:
        _retention_task = asyncio.create_task(_retention_loop(_retention_days()))
    # Pipecat/Silero prewarm can take 60–90s; do not block HTTP /health or WebSocket connect.
    if realtime_transport is not None and _voice_prewarm_task is None:
        _voice_prewarm_task = asyncio.create_task(_prewarm_voice_stack())


async def shutdown() -> None:
    global _voice_prewarm_task, _retention_task
    if _retention_task is not None:
        _retention_task.cancel()
        _retention_task = None
    if _voice_prewarm_task is not None:
        _voice_prewarm_task.cancel()
        try:
            await _voice_prewarm_task
        except asyncio.CancelledError:
            pass
        _voice_prewarm_task = None
    if realtime_transport is not None:
        await realtime_transport.close()
    await event_gateway.close()
    if trace_bridge is not None:
        await asyncio.to_thread(trace_bridge.shutdown)  # flush pending spans
    await model_provider.aclose()
    for delegate in (tool_delegate, *extra_tool_delegates):
        if isinstance(delegate, HttpToolExecutor):
            await delegate.aclose()
    if isinstance(event_store, PostgresEventStore):
        await event_store.close()
    if isinstance(session_lock, RedisSessionLock):
        await session_lock.close()
