"""The gateway's composition root: builds the runtime, adapters, repositories and services once.

Controllers import the services (and nothing lower) from here. Everything environment-specific
— which store, which lock, which tools — is decided in this file.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from pathlib import Path

from relay_adapter_models_openai import OpenAIProvider
from relay_adapter_observability_otel import OtelTraceBridge, tracer_provider_from_env
from relay_adapter_observability_prometheus import PrometheusMetricsBridge
from relay_adapter_agents_reference import ReferenceTextAgent
from relay_adapter_tools_http import HttpToolExecutor
from relay_gateway.core import example_agents
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
from relay_gateway.repositories.account_repository import (
    AccountRepository,
    MemoryAccountRepository,
    PostgresAccountRepository,
)
from relay_gateway.repositories.api_key_repository import (
    ApiKeyRepository,
    MemoryApiKeyRepository,
    PostgresApiKeyRepository,
)
from relay_gateway.repositories.database import Database
from relay_gateway.repositories.device_login_repository import (
    DeviceLoginRepository,
    MemoryDeviceLoginRepository,
    PostgresDeviceLoginRepository,
)
from relay_gateway.repositories.email_token_repository import (
    EmailTokenRepository,
    MemoryEmailTokenRepository,
    PostgresEmailTokenRepository,
)
from relay_gateway.repositories.event_repository import EventRepository
from relay_gateway.integrations.email import email_sender_from_env
from relay_gateway.repositories.rate_limit_repository import (
    MemoryRateLimitRepository,
    RateLimitRepository,
    RedisRateLimitRepository,
)
from relay_gateway.repositories.project_agent_repository import (
    MemoryProjectAgentRepository,
    PostgresProjectAgentRepository,
    ProjectAgentRepository,
)
from relay_gateway.repositories.project_secret_repository import (
    MemoryProjectSecretRepository,
    PostgresProjectSecretRepository,
    ProjectSecretRepository,
)
from relay_gateway.repositories.session_repository import SessionRepository
from relay_gateway.services.account_email_service import AccountEmailService
from relay_gateway.services.admin_service import AdminService
from relay_gateway.services.agent_service import load_agent_manifests
from relay_gateway.services.auth_service import AuthService
from relay_gateway.services.device_login_service import DeviceLoginService
from relay_gateway.services.metrics_service import MetricsService
from relay_gateway.core.crypto import SecretBox
from relay_gateway.services.project_activity_service import ProjectActivityService
from relay_gateway.services.project_agent_service import ProjectAgentService
from relay_gateway.services.key_alert_service import KeyAlertService
from relay_gateway.services.project_service import ProjectService
from relay_gateway.services.rate_limit_service import RateLimitService
from relay_gateway.services.secret_service import SecretService
from relay_gateway.services.realtime_service import RealtimeService
from relay_gateway.services.retention_service import RetentionService
from relay_gateway.services.session_service import SessionService
from relay_gateway.services.stream_service import StreamService
from relay_runtime.ports.agent import AgentAdapter
from relay_runtime.ports.events import EventStore
from relay_runtime.ports.tools import ToolExecutor


def _build_event_store() -> EventStore:
    if os.environ.get("RELAY_DATABASE_URL"):
        return PostgresEventStore()
    return MemoryEventStore()


def _build_session_lock() -> LocalSessionLock | RedisSessionLock:
    if os.environ.get("RELAY_REDIS_URL"):
        return RedisSessionLock()
    return LocalSessionLock()


class _NoTools(ToolExecutor):
    """The default agent has no tools; anything that reaches this is a bug upstream."""

    async def execute(self, session_id, *, tool_name, arguments, idempotency_key=None):
        del session_id, arguments, idempotency_key
        return {"error": f"unknown_tool:{tool_name}"}


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
# The gateway-wide default agent serves dev sessions whose agent_id is not registered. It is a
# plain assistant with no tools unless the bundled example is switched on (core/example_agents.py; demos and tests).
# Sessions started with a project key never use it (see ProjectAgentService).
if example_agents.enabled():
    # The lambda reads session_repository (defined below) when a tool is called.
    _default_agent, _default_registry, tool_delegate = example_agents.build(
        model_router, user_for_session=lambda session_id: session_repository.end_user(session_id)
    )
else:
    _default_agent, _default_registry, tool_delegate = ReferenceTextAgent(model_router), ToolRegistry(), _NoTools()
registry_tool_executor = RegistryToolExecutor(
    registry=_default_registry,
    delegate=tool_delegate,
    trace_manager=TraceManager(),
    default_timeout_seconds=float(os.environ.get("RELAY_TOOL_TIMEOUT_SECONDS", "30")),
)
agent_runtime = AgentRuntime(
    model_router=model_router,
    agent=_default_agent,
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
    delegate: ToolExecutor | None = (
        HttpToolExecutor(base_url=url, user_for_session=lambda session_id: session_repository.end_user(session_id))
        if url
        else local_executor
    )
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
# services/agent_service.py). ``add_tool_agent`` is for agents that need custom Python.
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


# Repositories: the only gateway code that reads stores.
event_repository = EventRepository(event_store, event_gateway)
session_repository = SessionRepository(session_manager)
# Accounts, projects and keys live in Postgres when one is configured; in memory otherwise
# (local runs and tests — everything is lost on restart).
database: Database | None = Database() if os.environ.get("RELAY_DATABASE_URL") else None
account_repository: AccountRepository = (
    PostgresAccountRepository(database) if database else MemoryAccountRepository()
)
api_key_repository: ApiKeyRepository = PostgresApiKeyRepository(database) if database else MemoryApiKeyRepository()
device_login_repository: DeviceLoginRepository = (
    PostgresDeviceLoginRepository(database) if database else MemoryDeviceLoginRepository()
)
email_token_repository: EmailTokenRepository = (
    PostgresEmailTokenRepository(database) if database else MemoryEmailTokenRepository()
)
project_agent_repository: ProjectAgentRepository = (
    PostgresProjectAgentRepository(database) if database else MemoryProjectAgentRepository()
)
project_secret_repository: ProjectSecretRepository = (
    PostgresProjectSecretRepository(database) if database else MemoryProjectSecretRepository()
)

# Metrics are derived from the event stream; one subscriber sees every session.
metrics_bridge = PrometheusMetricsBridge(
    agent_for_session=session_repository.agent_label,
    active_sessions=session_repository.count,
)
event_gateway.subscribe("*", metrics_bridge.on_event)

# Traces are exported only when an OTLP endpoint is configured (OTEL_EXPORTER_OTLP_ENDPOINT).
_tracer_provider = tracer_provider_from_env()
trace_bridge = OtelTraceBridge(_tracer_provider, agent_for_session=session_repository.agent_label) if _tracer_provider else None
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
    realtime_transport.stt_keyterms_resolver = session_manager.speech_keyterms_for
    realtime_transport.voice_hooks = VoicePipelineHooks(
        on_speech_started=session_manager.notify_voice_speech_started,
        on_speech_ended=session_manager.notify_voice_speech_ended,
        on_transcript_delta=session_manager.notify_voice_transcript_delta,
        on_transcript_final=session_manager.notify_voice_transcript_final,
    )

# Services: what controllers call.
# Rate-limit counters: shared through Redis when several gateway processes run.
rate_limit_repository: RateLimitRepository = (
    RedisRateLimitRepository(os.environ["RELAY_REDIS_URL"])
    if os.environ.get("RELAY_REDIS_URL")
    else MemoryRateLimitRepository()
)
rate_limit_service = RateLimitService(rate_limit_repository)
auth_service = AuthService(account_repository, api_key_repository, rate_limit_service)
project_service = ProjectService(account_repository, api_key_repository, auth_service)
# SMTP when RELAY_SMTP_HOST is set; otherwise emails are printed to the gateway log (development).
email_sender = email_sender_from_env()
account_email_service = AccountEmailService(
    account_repository, email_token_repository, auth_service, email_sender, rate_limit_service
)
key_alert_service = KeyAlertService(api_key_repository, account_repository, email_sender, rate_limit_service)
device_login_service = DeviceLoginService(
    device_login_repository, auth_service, project_service, rate_limit_service, account_email_service
)
secret_service = SecretService(project_secret_repository, SecretBox())
# Sessions started with a project key run on that project's own agent, tools and model key.
project_agent_service = ProjectAgentService(
    project_agent_repository,
    secret_service,
    model_provider_factory=lambda api_key, model: OpenAIProvider(api_key=api_key, model=model),
    is_live=session_repository.is_live,
    user_for_session=session_repository.end_user,
)
secret_service.on_change = project_agent_service.invalidate
session_manager.runtime_resolver = lambda session: project_agent_service.runtime_of_session(session.session_id)
session_service = SessionService(
    session_manager,
    session_repository,
    event_repository,
    project_service,
    project_agent_service,
    rate_limit_service,
    key_alert_service,
)
stream_service = StreamService(session_manager, session_repository)
realtime_service = RealtimeService(session_manager)
admin_service = AdminService(session_repository, event_repository)
project_activity_service = ProjectActivityService(session_repository, event_repository)
metrics_service = MetricsService(metrics_bridge)
retention_service = RetentionService(event_repository)

_voice_prewarm_task: asyncio.Task[None] | None = None


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


async def startup() -> None:
    global _voice_prewarm_task
    if isinstance(event_store, PostgresEventStore):
        await event_store.connect()
    if database is not None:
        await database.pool()  # creates the identity tables on first start
    await load_agent_manifests(
        AGENTS_DIR,
        model_router=model_router,
        runtimes=extra_agent_runtimes,
        delegates=extra_tool_delegates,
        user_for_session=session_repository.end_user,
    )
    retention_service.start()
    # Pipecat/Silero prewarm can take 60–90s; do not block HTTP /health or WebSocket connect.
    if realtime_transport is not None and _voice_prewarm_task is None:
        _voice_prewarm_task = asyncio.create_task(_prewarm_voice_stack())


async def shutdown() -> None:
    global _voice_prewarm_task
    retention_service.stop()
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
    await project_agent_service.aclose()
    for delegate in (tool_delegate, *extra_tool_delegates):
        if isinstance(delegate, HttpToolExecutor):
            await delegate.aclose()
    if isinstance(event_store, PostgresEventStore):
        await event_store.close()
    if database is not None:
        await database.close()
    if isinstance(rate_limit_repository, RedisRateLimitRepository):
        await rate_limit_repository.aclose()
    if isinstance(session_lock, RedisSessionLock):
        await session_lock.close()
