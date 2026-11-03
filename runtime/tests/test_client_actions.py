"""App-advertised UI actions: the agent changes what is on screen instead of drawing new UI."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from relay_protocol import EventType
from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    SessionManager,
    ToolRegistry,
    ToolUsingAgent,
)
from relay_runtime.ports.model import ModelProvider
from relay_runtime.ui_surfaces import sanitize_client_actions

FILTER_ACTION = {
    "name": "FILTER_DEALS_TABLE",
    "description": "Filter the deals table on the dashboard",
    "parameters": {"type": "object", "properties": {"min_amount": {"type": "number"}}},
}


class FilterModel(ModelProvider):
    def __init__(self) -> None:
        self.offered: list[str] = []
        self.tool_result: dict[str, Any] | None = None

    async def stream_completion(self, session_id, *, messages, tools=None) -> AsyncIterator[dict[str, Any]]:
        del session_id
        self.offered = [t["function"]["name"] for t in tools or []]
        results = [m for m in messages if m.get("role") == "tool"]
        if not results:
            yield {"type": "tool_calls", "calls": [{"id": "c1", "name": "ui_FILTER_DEALS_TABLE",
                                                     "arguments": json.dumps({"min_amount": 70000})}]}
            return
        self.tool_result = json.loads(results[0]["content"])
        yield {"type": "token", "text": f"Filtered: {self.tool_result.get('rows_shown')} deals."}

    async def cancel(self, session_id: str) -> None:
        del session_id


def _manager(model: ModelProvider):
    router = ModelRouter(model)
    events = MemoryEventStore()
    manager = SessionManager(
        event_gateway=PersistingEventGateway(events),
        agent_runtime=AgentRuntime(
            model_router=router, agent=ToolUsingAgent(router, system_prompt="CRM", registry=ToolRegistry())
        ),
        session_lock=None,
        idle_grace_seconds=0,
    )
    return manager, events


async def _ack_actions(manager: SessionManager, events: MemoryEventStore, session_id: str, result: dict) -> list:
    """Play the browser: acknowledge every ACTION_REQUESTED with ``result``."""
    seen: list[dict] = []
    for _ in range(100):
        await asyncio.sleep(0.01)
        for event in events.all_events():
            if event.type == EventType.ACTION_REQUESTED and event.payload["action_id"] not in [s["action_id"] for s in seen]:
                seen.append(event.payload)
                await manager.submit_client_action_result(
                    session_id, action_id=event.payload["action_id"], name=event.payload["action"],
                    outcome="applied", result=result,
                )
        if seen:
            return seen
    return seen


@pytest.mark.asyncio
async def test_agent_filters_existing_table_and_reads_the_result():
    model = FilterModel()
    manager, events = _manager(model)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_client_app_event(session.session_id, name="ui.capabilities", payload={"actions": [FILTER_ACTION]})
        turn = asyncio.create_task(manager.submit_user_text(session.session_id, "deals of at least 70k"))
        requested = await _ack_actions(manager, events, session.session_id, {"rows_shown": 23})
        await asyncio.wait_for(turn, 5)
    finally:
        await manager.end_session(session.session_id)

    assert "ui_FILTER_DEALS_TABLE" in model.offered
    assert [r["action"] for r in requested] == ["FILTER_DEALS_TABLE"]
    assert requested[0]["params"] == {"min_amount": 70000}
    assert model.tool_result == {"outcome": "applied", "rows_shown": 23}
    assert not [r for r in requested if r["action"] == "PRESENT_UI"]
    assert [e for e in events.all_events() if e.type == EventType.RESPONSE_COMPLETED][-1].payload["text"] == "Filtered: 23 deals."


@pytest.mark.asyncio
async def test_no_ui_tools_without_advertised_actions():
    model = FilterModel()
    manager, _events = _manager(model)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "hello")
    finally:
        await manager.end_session(session.session_id)
    assert not [n for n in model.offered if n.startswith("ui_")]


def test_sanitize_client_actions_drops_bad_entries():
    actions = sanitize_client_actions([
        FILTER_ACTION,
        {"name": "bad name!", "description": "x"},
        {"name": "PRESENT_UI"},
        {"name": "OPEN_DEAL", "parameters": "not a schema"},
        "junk",
    ])
    assert [a["name"] for a in actions] == ["FILTER_DEALS_TABLE", "OPEN_DEAL"]
    assert actions[1]["parameters"] == {"type": "object", "properties": {}}


NAVIGATE_ACTION = {
    "name": "NAVIGATE",
    "description": "Open a page of the app",
    "parameters": {"type": "object", "properties": {"path": {"type": "string", "enum": ["/", "/invoices/new"]}}},
}
PAGE_FORM_ACTION = {
    "name": "PAGE_FORM_NEW_INVOICE",
    "description": "Fill the New invoice form on this page",
    "parameters": {"type": "object", "properties": {"customer": {"type": "string"}, "amount": {"type": "number"}}},
}


class NavigateThenFillModel(ModelProvider):
    """Opens the page, then fills the form that page advertises — in one user message."""

    def __init__(self) -> None:
        self.offered_per_round: list[list[str]] = []
        self.system_texts: list[str] = []

    async def stream_completion(self, session_id, *, messages, tools=None) -> AsyncIterator[dict[str, Any]]:
        del session_id
        offered = [t["function"]["name"] for t in tools or []]
        self.offered_per_round.append(offered)
        self.system_texts = [str(m["content"]) for m in messages if m.get("role") == "system"]
        done = [m for m in messages if m.get("role") == "tool"]
        if not done:
            yield {"type": "tool_calls", "calls": [{"id": "c1", "name": "ui_NAVIGATE",
                                                     "arguments": json.dumps({"path": "/invoices/new"})}]}
        elif len(done) == 1 and "ui_PAGE_FORM_NEW_INVOICE" in offered:
            yield {"type": "tool_calls", "calls": [{"id": "c2", "name": "ui_PAGE_FORM_NEW_INVOICE",
                                                     "arguments": json.dumps({"customer": "Acme", "amount": 50000})}]}
        else:
            yield {"type": "token", "text": "Filled the invoice form — review it and submit."}

    async def cancel(self, session_id: str) -> None:
        del session_id


@pytest.mark.asyncio
async def test_agent_navigates_then_fills_the_new_pages_form_in_the_same_turn():
    model = NavigateThenFillModel()
    manager, events = _manager(model)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    sid = session.session_id
    try:
        await manager.submit_client_app_event(sid, name="ui.capabilities", payload={"actions": [NAVIGATE_ACTION]})
        turn = asyncio.create_task(manager.submit_user_text(sid, "open a new invoice for Acme, 50000"))
        acked: list[str] = []
        for _ in range(300):
            await asyncio.sleep(0.01)
            for event in events.all_events():
                if event.type != EventType.ACTION_REQUESTED or event.payload["action_id"] in acked:
                    continue
                acked.append(event.payload["action_id"])
                if event.payload["action"] == "NAVIGATE":
                    # Like the SDK: the new page's actions are advertised before the navigation result.
                    await manager.submit_client_app_event(
                        sid, name="ui.capabilities", payload={"actions": [NAVIGATE_ACTION, PAGE_FORM_ACTION]}
                    )
                await manager.submit_client_action_result(
                    sid, action_id=event.payload["action_id"], name=event.payload["action"],
                    outcome="applied", result={"ok": True},
                )
            if turn.done():
                break
        await asyncio.wait_for(turn, 5)
    finally:
        await manager.end_session(sid)

    requested = [e.payload for e in events.all_events() if e.type == EventType.ACTION_REQUESTED]
    assert [r["action"] for r in requested] == ["NAVIGATE", "PAGE_FORM_NEW_INVOICE"]
    assert requested[1]["params"] == {"customer": "Acme", "amount": 50000}
    assert "ui_PAGE_FORM_NEW_INVOICE" not in model.offered_per_round[0]
    assert "ui_PAGE_FORM_NEW_INVOICE" in model.offered_per_round[1]
    assert any("ui_PAGE_FORM_" in text and "never submits" in text for text in model.system_texts)


@pytest.mark.asyncio
async def test_capabilities_update_while_a_turn_is_running():
    """The update is applied at once, not queued behind the in-flight turn."""
    model = FilterModel()
    manager, events = _manager(model)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    sid = session.session_id
    try:
        await manager.submit_client_app_event(sid, name="ui.capabilities", payload={"actions": [FILTER_ACTION]})
        turn = asyncio.create_task(manager.submit_user_text(sid, "deals of at least 70k"))
        for _ in range(100):  # the turn is now waiting for the browser's action result
            await asyncio.sleep(0.01)
            if any(e.type == EventType.ACTION_REQUESTED for e in events.all_events()):
                break
        await asyncio.wait_for(
            manager.submit_client_app_event(sid, name="ui.capabilities", payload={"actions": [NAVIGATE_ACTION]}), 1
        )
        assert [a["name"] for a in manager._sessions[sid].context.client_actions] == ["NAVIGATE"]
        await _ack_actions(manager, events, sid, {"rows_shown": 1})
        await asyncio.wait_for(turn, 5)
    finally:
        await manager.end_session(sid)
