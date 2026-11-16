"""Forms bound to a write tool: fields from the tool schema, submit saves through the tool."""

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
    RegistryToolExecutor,
    SessionManager,
    ToolClassification,
    ToolDefinition,
    ToolRegistry,
    ToolUsingAgent,
)
from relay_runtime.ports.model import ModelProvider
from relay_runtime.ports.tools import ToolExecutor

LOG_ACTIVITY_SCHEMA = {
    "type": "object",
    "required": ["deal_id", "type", "subject"],
    "properties": {
        "deal_id": {"type": "string", "minLength": 1, "title": "Deal ID"},
        "type": {"type": "string", "enum": ["call", "email", "meeting"], "title": "Activity type"},
        "subject": {"type": "string", "minLength": 1, "title": "Subject"},
        "date_logged": {"type": "string", "format": "date", "title": "Date"},
        "duration_min": {"type": "integer", "minimum": 1},
        "notes": {"type": "string", "maxLength": 2000},
    },
}


class Store(ToolExecutor):
    def __init__(self) -> None:
        self.saved: list[tuple[str, dict[str, Any]]] = []
        self.fail_next = False

    async def execute(self, session_id, *, tool_name, arguments, idempotency_key=None):
        del session_id, idempotency_key
        if self.fail_next:
            self.fail_next = False
            return {"error": "deal_locked"}
        self.saved.append((tool_name, dict(arguments)))
        return {"activity": {"id": "ACT-0300", **arguments}}


class FormModel(ModelProvider):
    def __init__(self, form: dict[str, Any]) -> None:
        self.form = form
        self.user_texts: list[str] = []
        self.tool_results: list[dict[str, Any]] = []

    async def stream_completion(self, session_id, *, messages, tools=None) -> AsyncIterator[dict[str, Any]]:
        del session_id, tools
        last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        self.user_texts.append(last_user)
        if last_user.startswith("[Action") or last_user.startswith("[Form"):
            yield {"type": "token", "text": "ok"}
            return
        results = [m for m in messages if m.get("role") == "tool"]
        if not results:
            yield {"type": "tool_calls", "calls": [{"id": "c1", "name": "present_ui",
                                                     "arguments": json.dumps({"surfaces": [self.form]})}]}
            return
        self.tool_results.append(json.loads(results[-1]["content"]))
        yield {"type": "token", "text": "Here is the form."}

    async def cancel(self, session_id: str) -> None:
        del session_id


def _setup(form: dict[str, Any]):
    registry = ToolRegistry()
    registry.register(ToolDefinition(name="get_deal", classification=ToolClassification.READ_ONLY,
                                     input_schema={"type": "object", "properties": {}}))
    registry.register(ToolDefinition(name="log_activity", classification=ToolClassification.SIDE_EFFECTING,
                                     description="Log a call, email or meeting", input_schema=LOG_ACTIVITY_SCHEMA))
    model, store, events = FormModel(form), Store(), MemoryEventStore()
    router = ModelRouter(model)
    manager = SessionManager(
        event_gateway=PersistingEventGateway(events),
        agent_runtime=AgentRuntime(
            model_router=router,
            agent=ToolUsingAgent(router, system_prompt="CRM", registry=registry),
            tool_executor=RegistryToolExecutor(registry=registry, delegate=store),
        ),
        session_lock=None,
        idle_grace_seconds=0,
    )
    return manager, events, store, model


def _of(events: MemoryEventStore, kind: EventType):
    return [e for e in events.all_events() if e.type == kind]


def _shown_form(events: MemoryEventStore) -> dict[str, Any]:
    ui = [e for e in _of(events, EventType.ACTION_REQUESTED) if e.payload["action"] == "PRESENT_UI"]
    return ui[-1].payload["params"]["surfaces"][0]


async def _drain(manager: SessionManager, session_id: str) -> None:
    for _ in range(100):
        await asyncio.sleep(0.01)
        if manager.get(session_id).queue.empty():
            await asyncio.sleep(0.03)
            return


async def _submit(manager, session_id, form, values):
    await manager.submit_client_app_event(
        session_id, name="ui.form_submit", payload={"form_id": form["id"], "title": form["title"], "values": values}
    )
    await _drain(manager, session_id)


@pytest.mark.asyncio
async def test_bound_form_fields_come_from_the_tool_and_submit_saves():
    manager, events, store, model = _setup(
        {"kind": "form", "title": "Log a call", "submit_tool": "log_activity",
         "fields": [{"name": "type"}, {"name": "subject"}, {"name": "notes"}], "values": {"deal_id": "DEAL-2042", "type": "call"}}
    )
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "log a call for DEAL-2042")
        form = _shown_form(events)
        by_name = {f["name"]: f for f in form["fields"]}
        assert list(by_name) == ["type", "subject", "notes", "deal_id"]  # chosen order + required deal_id
        assert by_name["type"] == {"name": "type", "label": "Activity type", "type": "select", "required": True,
                                   "options": ["call", "email", "meeting"], "default": "call"}
        assert by_name["notes"]["type"] == "textarea" and by_name["deal_id"]["default"] == "DEAL-2042"
        assert form["submit_tool"] == "log_activity"
        assert form["id"].startswith("log_activity-")  # unique per render; bound server-side
        assert store.saved == []

        await _submit(manager, session.session_id, form,
                      {"deal_id": "DEAL-2042", "type": "call", "subject": "Pricing call", "notes": "  "})
    finally:
        await manager.end_session(session.session_id)

    assert store.saved == [("log_activity", {"deal_id": "DEAL-2042", "type": "call", "subject": "Pricing call"})]
    verified = _of(events, EventType.COMMIT_VERIFIED)[-1].payload
    assert verified["form_id"] == form["id"] and verified["verified"] is True
    granted = _of(events, EventType.APPROVAL_GRANTED)[-1].payload
    assert granted["via"] == "form_submit"
    assert model.user_texts[-1].startswith('[Action approved] Submitted form "Log a call"')
    assert not [t for t in model.user_texts if t.startswith("[Form submitted]")]


@pytest.mark.asyncio
async def test_failed_save_keeps_the_form_usable_for_a_retry():
    manager, events, store, model = _setup({"kind": "form", "title": "Log", "submit_tool": "log_activity"})
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "log something")
        form = _shown_form(events)
        store.fail_next = True
        await _submit(manager, session.session_id, form, {"deal_id": "D-1", "type": "call", "subject": "x"})
        failed = [e for e in _of(events, EventType.ERROR) if e.payload.get("message") == "commit_failed"]
        assert failed[-1].payload["form_id"] == form["id"] and failed[-1].payload["error"] == "deal_locked"
        assert model.user_texts[-1].startswith("[Action failed]")

        await _submit(manager, session.session_id, form, {"deal_id": "D-1", "type": "call", "subject": "x"})
    finally:
        await manager.end_session(session.session_id)
    assert store.saved == [("log_activity", {"deal_id": "D-1", "type": "call", "subject": "x"})]


@pytest.mark.asyncio
async def test_invalid_submission_is_rejected_by_the_tool_schema():
    manager, events, store, _model = _setup({"kind": "form", "title": "Log", "submit_tool": "log_activity"})
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "log something")
        await _submit(manager, session.session_id, _shown_form(events), {"type": "call"})  # missing deal_id, subject
    finally:
        await manager.end_session(session.session_id)
    assert store.saved == []
    assert [e for e in _of(events, EventType.ERROR) if e.payload.get("message") == "commit_failed"]


@pytest.mark.asyncio
async def test_read_only_submit_tool_is_rejected():
    manager, events, _store, model = _setup({"kind": "form", "title": "x", "submit_tool": "get_deal"})
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "form please")
    finally:
        await manager.end_session(session.session_id)
    assert model.tool_results[-1] == {"error": "submit_tool must be one of ['log_activity']"}
    assert not [e for e in _of(events, EventType.ACTION_REQUESTED) if e.payload["action"] == "PRESENT_UI"]


@pytest.mark.asyncio
async def test_unbound_form_still_goes_to_the_assistant():
    manager, events, store, model = _setup(
        {"kind": "form", "id": "prefs", "title": "Preferences", "fields": [{"name": "tone", "label": "Tone", "type": "text"}]}
    )
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "ask me")
        await _submit(manager, session.session_id, _shown_form(events), {"tone": "short"})
    finally:
        await manager.end_session(session.session_id)
    assert store.saved == []
    assert model.user_texts[-1].startswith("[Form submitted] Preferences:")


@pytest.mark.asyncio
async def test_agents_without_proposals_cannot_bind_forms_to_write_tools():
    manager, events, store, _model = _setup(
        {"kind": "form", "id": "f", "title": "Commit", "submit_tool": "log_activity",
         "fields": [{"name": "subject", "label": "Subject", "type": "text"}]}
    )
    manager.agent_runtime.agent._allow_proposals = False
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "form")
        form = _shown_form(events)
        assert "submit_tool" not in form
        await _submit(manager, session.session_id, form, {"subject": "x"})
    finally:
        await manager.end_session(session.session_id)
    assert store.saved == []
