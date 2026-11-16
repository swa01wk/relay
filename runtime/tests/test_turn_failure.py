"""A failed model call reports SESSION_ERROR, completes the turn, and keeps the session usable."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from relay_adapter_agents_reference import ReferenceTextAgent
from relay_protocol import EventType
from relay_runtime import AgentRuntime, MemoryEventStore, ModelRouter, PersistingEventGateway, SessionManager
from relay_runtime.ports.model import ModelProvider


class FailsOnceModel(ModelProvider):
    def __init__(self) -> None:
        self.calls = 0

    async def stream_completion(
        self, session_id: str, *, messages: list[dict[str, Any]], tools: Any = None
    ) -> AsyncIterator[dict[str, Any]]:
        del session_id, messages, tools
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("401 Unauthorized from upstream")
        yield {"type": "token", "text": "Recovered."}

    async def cancel(self, session_id: str) -> None:
        del session_id


@pytest.mark.asyncio
async def test_model_failure_completes_turn_and_next_message_works():
    router = ModelRouter(FailsOnceModel())
    store = MemoryEventStore()
    manager = SessionManager(
        event_gateway=PersistingEventGateway(store),
        agent_runtime=AgentRuntime(model_router=router, agent=ReferenceTextAgent(router)),
        session_lock=None,
        idle_grace_seconds=0,
    )
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "first")
        first = [e.type for e in store.all_events()]
        errors = [e for e in store.all_events() if e.type == EventType.SESSION_ERROR]
        assert errors and errors[-1].payload["code"] == "turn_failed"
        assert EventType.RESPONSE_CANCELLED in first
        assert first[-1] == EventType.TURN_COMPLETED

        await manager.submit_user_text(session.session_id, "second")
    finally:
        await manager.end_session(session.session_id)

    completed = [e for e in store.all_events() if e.type == EventType.RESPONSE_COMPLETED]
    assert completed[-1].payload["text"] == "Recovered."
    assert not [
        e for e in store.all_events()
        if e.type == EventType.SESSION_ERROR and e.payload.get("code") == "turn_in_progress"
    ]
