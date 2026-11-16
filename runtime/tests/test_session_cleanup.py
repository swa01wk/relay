"""Abandoned sessions are ended after a grace period; reconnects inside it keep them."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from relay_adapter_agents_reference import ReferenceTextAgent
from relay_protocol import EventType
from relay_runtime import (
    AgentRuntime,
    LocalSessionLock,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    SessionManager,
)
from relay_runtime.ports.model import ModelProvider


class HangingModel(ModelProvider):
    """Streams one token, then hangs like a slow upstream until cancelled."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = False

    async def stream_completion(
        self, session_id: str, *, messages: list[dict[str, Any]], tools: Any = None
    ) -> AsyncIterator[dict[str, Any]]:
        del session_id, messages, tools
        self.started.set()
        yield {"type": "token", "text": "Thinking"}
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def cancel(self, session_id: str) -> None:
        del session_id


def _manager(*, grace: float, model: ModelProvider | None = None, lock: Any = None):
    router = ModelRouter(model or HangingModel())
    store = MemoryEventStore()
    manager = SessionManager(
        event_gateway=PersistingEventGateway(store),
        agent_runtime=AgentRuntime(model_router=router, agent=ReferenceTextAgent(router)),
        session_lock=lock,
        idle_grace_seconds=grace,
    )
    return manager, store


@pytest.mark.asyncio
async def test_never_connected_session_is_reaped():
    manager, store = _manager(grace=0.05)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await asyncio.sleep(0.2)
    assert manager.get(session.session_id) is None
    assert store.all_events()[-1].type == EventType.SESSION_ENDED


@pytest.mark.asyncio
async def test_reconnect_within_grace_keeps_session():
    manager, _store = _manager(grace=0.15)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    manager.client_attached(session.session_id)
    manager.client_detached(session.session_id)  # e.g. page refresh
    await asyncio.sleep(0.05)
    manager.client_attached(session.session_id)  # new tab reconnects in time
    await asyncio.sleep(0.3)
    assert manager.get(session.session_id) is session
    await manager.end_session(session.session_id)


@pytest.mark.asyncio
async def test_two_tabs_session_survives_until_last_leaves():
    manager, _store = _manager(grace=0.05)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    manager.client_attached(session.session_id)
    manager.client_attached(session.session_id)
    manager.client_detached(session.session_id)
    await asyncio.sleep(0.15)
    assert manager.get(session.session_id) is session
    manager.client_detached(session.session_id)
    await asyncio.sleep(0.15)
    assert manager.get(session.session_id) is None


@pytest.mark.asyncio
async def test_abandoned_session_aborts_in_flight_turn_and_releases_lock():
    model = HangingModel()
    lock = LocalSessionLock()
    manager, store = _manager(grace=0.05, model=model, lock=lock)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    manager.client_attached(session.session_id)

    turn = asyncio.create_task(manager.submit_user_text(session.session_id, "hello"))
    await asyncio.wait_for(model.started.wait(), timeout=2)
    manager.client_detached(session.session_id)  # tab closed mid-turn

    with pytest.raises(RuntimeError, match="session ended"):
        await asyncio.wait_for(turn, timeout=2)  # caller is released, not left hanging
    assert model.cancelled
    assert manager.get(session.session_id) is None
    assert store.all_events()[-1].type == EventType.SESSION_ENDED
    assert await lock.acquire(session.session_id, owner="someone-else")


@pytest.mark.asyncio
async def test_zero_grace_disables_reaping():
    manager, _store = _manager(grace=0)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await asyncio.sleep(0.05)
    assert manager.get(session.session_id) is session
    await manager.end_session(session.session_id)
