"""A voice session's speech-recognition hints come from the session's agent."""

from __future__ import annotations

import pytest

from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    SessionManager,
    ToolRegistry,
    ToolUsingAgent,
)


class _NoModel:
    async def stream(self, *args, **kwargs):  # pragma: no cover - never called
        if False:
            yield {}

    async def cancel(self, session_id: str) -> None:
        del session_id


def _runtime(terms: tuple[str, ...] = ()) -> AgentRuntime:
    router = ModelRouter(_NoModel())
    agent = ToolUsingAgent(router, system_prompt="x", registry=ToolRegistry())
    return AgentRuntime(model_router=router, agent=agent, speech_keyterms=terms)


@pytest.mark.asyncio
async def test_speech_keyterms_follow_the_session_agent():
    manager = SessionManager(
        event_gateway=PersistingEventGateway(MemoryEventStore()),
        agent_runtime=_runtime(),
        agent_runtimes={"crm": _runtime(("Northwind Logistics", "Okafor"))},
        session_lock=None,
        idle_grace_seconds=0,
    )
    crm, _ = await manager.create_dev_session(project_id="p", agent_id="crm")
    other, _ = await manager.create_dev_session(project_id="p", agent_id="unknown")
    assert manager.speech_keyterms_for(crm.session_id) == ("Northwind Logistics", "Okafor")
    assert manager.speech_keyterms_for(other.session_id) == ()  # default agent has none
    assert manager.speech_keyterms_for("no-such-session") == ()

    # A resolved per-project runtime wins (customer agents).
    manager.runtime_resolver = lambda session: _runtime(("Acme",)) if session.agent_id == "unknown" else None
    assert manager.speech_keyterms_for(other.session_id) == ("Acme",)
