"""Sessions run the agent registered for their ``agent_id``; unknown ids use the default."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from relay_adapter_agents_reference import ReferenceTextAgent
from relay_protocol import EventType
from relay_runtime import AgentRuntime, MemoryEventStore, ModelRouter, PersistingEventGateway, SessionManager
from relay_runtime.ports.model import ModelProvider


class FixedReplyModel(ModelProvider):
    def __init__(self, reply: str) -> None:
        self.reply = reply

    async def stream_completion(
        self, session_id: str, *, messages: list[dict[str, Any]], tools: Any = None
    ) -> AsyncIterator[dict[str, Any]]:
        del session_id, messages, tools
        yield {"type": "token", "text": self.reply}

    async def cancel(self, session_id: str) -> None:
        del session_id


def _runtime(reply: str) -> AgentRuntime:
    router = ModelRouter(FixedReplyModel(reply))
    return AgentRuntime(model_router=router, agent=ReferenceTextAgent(router))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("agent_id", "expected"),
    [("sales-crm", "crm reply"), ("agent-mortgage-ref", "default reply"), ("unknown", "default reply")],
)
async def test_session_uses_runtime_registered_for_agent_id(agent_id, expected):
    store = MemoryEventStore()
    manager = SessionManager(
        event_gateway=PersistingEventGateway(store),
        agent_runtime=_runtime("default reply"),
        agent_runtimes={"sales-crm": _runtime("crm reply")},
        session_lock=None,
        idle_grace_seconds=0,
    )
    session, _ = await manager.create_dev_session(project_id="p", agent_id=agent_id)
    try:
        await manager.submit_user_text(session.session_id, "hi")
    finally:
        await manager.end_session(session.session_id)

    completed = [e for e in store.all_events() if e.type == EventType.RESPONSE_COMPLETED]
    assert completed[-1].payload["text"] == expected
