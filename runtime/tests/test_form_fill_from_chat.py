"""Values the user gives in chat go into the form already on screen (checked, never saved)."""

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
from relay_runtime.ui_surfaces import open_forms_from_present_ui, sanitize_form_fill

FORM = {
    "kind": "form",
    "id": "report",
    "title": "Report a problem",
    "fields": [
        {"name": "summary", "type": "text", "required": True},
        {"name": "severity", "type": "select", "options": ["low", "high"]},
        {"name": "due", "type": "date"},
        {"name": "people", "type": "number"},
        {"name": "urgent", "type": "checkbox"},
    ],
}


class FormModel(ModelProvider):
    """Shows the form on the first message, fills it from the second."""

    def __init__(self) -> None:
        self.offered: list[list[str]] = []
        self.fill_result: dict[str, Any] | None = None

    async def stream_completion(self, session_id, *, messages, tools=None) -> AsyncIterator[dict[str, Any]]:
        del session_id
        start = max(i for i, m in enumerate(messages) if m["role"] == "user")
        last_user = messages[start]["content"]
        tool_results = [m for m in messages[start:] if m.get("role") == "tool"]
        if not tool_results:
            self.offered.append([t["function"]["name"] for t in tools or []])
        if tool_results:
            if last_user.startswith("summary is"):
                self.fill_result = json.loads(tool_results[0]["content"])
            yield {"type": "token", "text": "Done."}
        elif last_user == "report a problem":
            yield {"type": "tool_calls", "calls": [{"id": "c1", "name": "present_ui", "arguments": json.dumps({"surfaces": [FORM]})}]}
        elif last_user.startswith("summary is"):
            values = {"summary": "Login broken", "severity": "HIGH", "due": "2026-11-01", "people": "1,200",
                      "urgent": "yes", "color": "red"}
            yield {"type": "tool_calls", "calls": [{"id": "c2", "name": "fill_form", "arguments": json.dumps({"form_id": "report", "values": values})}]}
        else:
            yield {"type": "token", "text": "OK."}

    async def cancel(self, session_id: str) -> None:
        del session_id


def _manager(model: ModelProvider):
    router = ModelRouter(model)
    events = MemoryEventStore()
    manager = SessionManager(
        event_gateway=PersistingEventGateway(events),
        agent_runtime=AgentRuntime(model_router=router, agent=ToolUsingAgent(router, system_prompt="Help", registry=ToolRegistry())),
        session_lock=None,
        idle_grace_seconds=0,
    )
    return manager, events


async def _ack_fill(manager: SessionManager, events: MemoryEventStore, session_id: str) -> dict:
    """Play the browser: apply the FILL_FORM action and report back."""
    for _ in range(200):
        await asyncio.sleep(0.01)
        for event in events.all_events():
            if event.type == EventType.ACTION_REQUESTED and event.payload["action"] == "FILL_FORM":
                await manager.submit_client_action_result(
                    session_id, action_id=event.payload["action_id"], name="FILL_FORM",
                    outcome="applied", result={"form_open": True},
                )
                return event.payload["params"]
    raise AssertionError("no FILL_FORM action")


@pytest.mark.asyncio
async def test_values_given_in_chat_fill_the_open_form_and_bad_ones_are_reported():
    model = FormModel()
    manager, events = _manager(model)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "report a problem")
        turn = asyncio.create_task(manager.submit_user_text(session.session_id, "summary is login broken, high, due Nov 1"))
        params = await _ack_fill(manager, events, session.session_id)
        await asyncio.wait_for(turn, 5)
        await manager.submit_client_app_event(
            session.session_id, name="ui.form_submit",
            payload={"form_id": "report", "title": "Report a problem", "values": params["values"]},
        )
        await asyncio.sleep(0.05)
        await manager.submit_user_text(session.session_id, "thanks")
    finally:
        await manager.end_session(session.session_id)

    # Offered only while the form is on screen.
    assert "fill_form" not in model.offered[0]
    assert "fill_form" in model.offered[1]
    assert "fill_form" not in model.offered[-1]
    # Values are fitted to the fields: option spelling, numbers, booleans; unknown fields dropped.
    assert params == {"form_id": "report", "values": {
        "summary": "Login broken", "severity": "high", "due": "2026-11-01", "people": 1200, "urgent": True}}
    assert model.fill_result["outcome"] == "applied" and model.fill_result["form_open"] is True
    assert model.fill_result["rejected"] == {"color": "no such field"}
    assert "Nothing is saved" in model.fill_result["note"]
    # Filling saved nothing: no approval or commit happened.
    assert not [e for e in events.all_events() if e.type in (EventType.APPROVAL_GRANTED, EventType.COMMIT_VERIFIED)]


def test_fill_values_are_checked_against_the_form():
    forms = open_forms_from_present_ui({"surfaces": [FORM, {"kind": "table", "rows": []}]})
    assert [f["id"] for f in forms] == ["report"]

    params, report = sanitize_form_fill({"form_id": "report", "values": {
        "severity": "medium", "due": "next friday", "people": "many", "urgent": "maybe", "summary": "  Crash "}}, forms)
    assert params == {"form_id": "report", "values": {"summary": "Crash"}}
    assert set(report["rejected"]) == {"severity", "due", "people", "urgent"}
    assert "low" in report["rejected"]["severity"]

    assert sanitize_form_fill({"form_id": "gone", "values": {"summary": "x"}}, forms) == (
        None, {"error": "form_not_on_screen", "open_forms": ["report"]})
    params, report = sanitize_form_fill({"form_id": "report", "values": {"color": "red"}}, forms)
    assert params is None and report["error"] == "nothing_to_fill"
