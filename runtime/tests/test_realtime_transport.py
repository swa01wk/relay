"""P02-TC-002 / P02-TC-003 — RealtimeTransport mock swap and teardown."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
import pytest_asyncio

from relay_adapter_agents_reference import ReferenceTextAgent
from relay_adapter_models_openai import OpenAIProvider
from relay_protocol import EventType
from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    SessionManager,
)
from relay_runtime.ports.realtime import RealtimeTransport


@dataclass
class MockRealtimeTransport(RealtimeTransport):
    connected: set[str] = field(default_factory=set)
    disconnect_calls: list[str] = field(default_factory=list)
    offers: list[tuple[str, dict[str, Any]]] = field(default_factory=list)

    async def connect(self, session_id: str, *, offer: dict[str, Any] | None = None) -> dict[str, Any]:
        self.offers.append((session_id, offer or {}))
        self.connected.add(session_id)
        return {"sdp": "mock-answer", "type": "answer", "pc_id": f"pc-{session_id[:8]}"}

    async def disconnect(self, session_id: str) -> None:
        self.disconnect_calls.append(session_id)
        self.connected.discard(session_id)

    async def is_connected(self, session_id: str) -> bool:
        return session_id in self.connected

    async def patch_ice(
        self,
        session_id: str,
        *,
        pc_id: str,
        candidates: list[dict[str, Any]],
    ) -> None:
        _ = (session_id, pc_id, candidates)


def _manager_with_transport(transport: RealtimeTransport) -> SessionManager:
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    router = ModelRouter(OpenAIProvider(api_key=None))
    runtime = AgentRuntime(model_router=router, agent=ReferenceTextAgent(router))
    return SessionManager(
        event_gateway=gateway,
        agent_runtime=runtime,
        session_lock=None,
        realtime_transport=transport,
    )


@pytest_asyncio.fixture
async def manager_with_mock_transport():
    transport = MockRealtimeTransport()
    manager = _manager_with_transport(transport)
    yield manager, transport
    for session_id in list(manager._sessions):
        await manager.end_session(session_id)


@pytest.mark.asyncio
async def test_p02_tc_002_mock_transport_swap_text_unchanged(manager_with_mock_transport):
    manager, transport = manager_with_mock_transport
    _session, _events = await manager.create_dev_session(project_id="p", agent_id="a")
    session_id = next(iter(manager._sessions))
    await manager.submit_user_text(session_id, "hello")
    assert transport.offers == []
    answer = await manager.start_realtime(session_id, {"sdp": "v=0", "type": "offer"})
    assert answer["pc_id"]
    assert await transport.is_connected(session_id)


@pytest.mark.asyncio
async def test_p02_tc_003_session_end_closes_webrtc(manager_with_mock_transport):
    manager, transport = manager_with_mock_transport
    _session, _events = await manager.create_dev_session(project_id="p", agent_id="a")
    session_id = next(iter(manager._sessions))
    await manager.start_realtime(session_id, {"sdp": "v=0", "type": "offer"})
    await manager.end_session(session_id)
    assert transport.disconnect_calls == [session_id]
    assert not await transport.is_connected(session_id)


@pytest.mark.asyncio
async def test_transport_metrics_published():
    store = MemoryEventStore()
    manager = _manager_with_transport(MockRealtimeTransport())
    manager.event_gateway = PersistingEventGateway(store)
    _session, _events = await manager.create_dev_session(project_id="p", agent_id="a")
    session_id = next(iter(manager._sessions))
    await manager.record_transport_metric(session_id, "transport.connect_latency_ms", 42.0)
    events = await store.list_for_session(session_id)
    assert any(e.type == EventType.METRIC for e in events)
    await manager.end_session(session_id)
