"""Generative UI — model fetches data, calls ``present_ui``, client receives ``PRESENT_UI``."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from relay_mortgage_agent.agent import MortgageServicingAgent
from relay_protocol import EventType
from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    RegistryToolExecutor,
    SessionManager,
    ToolRegistry,
    sanitize_present_ui_arguments,
)
from relay_runtime.ports.model import ModelProvider
from relay_mortgage_agent.tool_definitions import register_mortgage_tools
from relay_mortgage_agent.tools_local import LocalMortgageToolExecutor


class ScriptedToolModel(ModelProvider):
    """Round 1: get_payments. Round 2: present_ui with the fetched rows. Round 3: short reply."""

    def __init__(self) -> None:
        self.tool_names_seen: list[list[str]] = []

    async def stream_completion(
        self,
        session_id: str,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        del session_id
        self.tool_names_seen.append([t["function"]["name"] for t in tools or []])
        tool_results = [m for m in messages if m.get("role") == "tool"]
        if not tool_results:
            yield {
                "type": "tool_calls",
                "calls": [{"id": "c1", "name": "get_payments",
                           "arguments": json.dumps({"mortgage_id": "MORT-2931", "months": 2})}],
            }
            return
        if len(tool_results) == 1:
            payments = json.loads(tool_results[0]["content"])["payments"]
            yield {
                "type": "tool_calls",
                "calls": [{"id": "c2", "name": "present_ui", "arguments": json.dumps({
                    "surfaces": [{
                        "kind": "table",
                        "title": "Payments by month",
                        "columns": ["month", "amount"],
                        "rows": [{"month": p["month"], "amount": p["amount"]} for p in payments],
                    }],
                })}],
            }
            return
        yield {"type": "token", "text": "The payments table is on your screen."}

    async def cancel(self, session_id: str) -> None:
        del session_id


def _manager(model: ModelProvider) -> tuple[SessionManager, MemoryEventStore]:
    registry = ToolRegistry()
    register_mortgage_tools(registry)
    router = ModelRouter(model)
    runtime = AgentRuntime(
        model_router=router,
        agent=MortgageServicingAgent(router),
        tool_executor=RegistryToolExecutor(registry=registry, delegate=LocalMortgageToolExecutor()),
    )
    store = MemoryEventStore()
    manager = SessionManager(
        event_gateway=PersistingEventGateway(store), agent_runtime=runtime, session_lock=None
    )
    return manager, store


@pytest.mark.asyncio
async def test_model_table_request_emits_present_ui_with_fetched_rows():
    model = ScriptedToolModel()
    manager, store = _manager(model)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "give me a table of my recent payments")
    finally:
        await manager.end_session(session.session_id)

    events = store.all_events()
    present = [
        e for e in events
        if e.type == EventType.ACTION_REQUESTED and e.payload.get("action") == "PRESENT_UI"
    ]
    assert present, [e.type for e in events]
    table = present[-1].payload["params"]["surfaces"][0]
    assert table["kind"] == "table"
    assert [row["month"] for row in table["rows"]] == ["2025-09", "2025-08"]

    tool_names = [e.payload.get("name") for e in events if e.type == EventType.TOOL_CALL_COMPLETED]
    assert "get_payments" in tool_names
    completed = [e for e in events if e.type == EventType.RESPONSE_COMPLETED]
    assert "on your screen" in completed[-1].payload.get("text", "")

    offered = set(model.tool_names_seen[0])
    assert {"present_ui", "get_payments", "get_rate_history"} <= offered
    assert "commit_correction" not in offered
    assert "prepare_correction" not in offered


def test_sanitize_present_ui_drops_unknown_kinds_and_caps_rows():
    params = sanitize_present_ui_arguments({
        "surfaces": [
            {"kind": "script", "title": "x"},
            {"kind": "table", "title": "t", "rows": [{"i": i} for i in range(80)]},
        ],
        "replace": False,
    })
    assert [s["kind"] for s in params["surfaces"]] == ["table"]
    assert len(params["surfaces"][0]["rows"]) == 50
    assert params["replace"] is False


def test_sanitize_chart_defaults_type_and_caps_points_and_series():
    params = sanitize_present_ui_arguments({
        "surfaces": [{
            "kind": "chart",
            "title": "c",
            "chart_type": "radar",
            "x_key": "i",
            "series": [{"key": f"s{i}"} for i in range(9)],
            "data": [{"i": i, "s0": i} for i in range(300)],
        }],
    })
    chart = params["surfaces"][0]
    assert chart["chart_type"] == "bar"
    assert len(chart["data"]) == 200
    assert len(chart["series"]) == 6


def test_present_ui_tool_offers_chart_kind():
    from relay_runtime import present_ui_tool

    surface_schema = present_ui_tool()["function"]["parameters"]["properties"]["surfaces"]["items"]
    assert "chart" in surface_schema["properties"]["kind"]["enum"]
    assert surface_schema["properties"]["chart_type"]["enum"] == ["bar", "line", "area", "pie"]


@pytest.mark.asyncio
async def test_payments_route_emits_table_and_bar_chart():
    manager, store = _manager(ScriptedToolModel())
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_user_text(session.session_id, "Compare last 3 months payments")
    finally:
        await manager.end_session(session.session_id)

    present = [
        e for e in store.all_events()
        if e.type == EventType.ACTION_REQUESTED and e.payload.get("action") == "PRESENT_UI"
    ]
    kinds = [s["kind"] for s in present[-1].payload["params"]["surfaces"]]
    assert kinds == ["table", "chart"]
    chart = present[-1].payload["params"]["surfaces"][1]
    assert chart["chart_type"] == "bar"
    assert [p["month"] for p in chart["data"]] == ["2025-07", "2025-08", "2025-09"]


def test_sanitize_form_keeps_valid_fields_and_drops_empty_forms():
    params = sanitize_present_ui_arguments({
        "surfaces": [
            {"kind": "form", "title": "No fields", "fields": []},
            {
                "kind": "form",
                "title": "Contact",
                "fields": [
                    {"name": "email", "label": "Email", "type": "email"},
                    {"name": "x", "label": "X", "type": "file"},
                ],
            },
            {"kind": "markdown", "title": "Note", "body": "# hi"},
        ],
    })
    kinds = [s["kind"] for s in params["surfaces"]]
    assert kinds == ["form", "markdown"]
    assert [f["name"] for f in params["surfaces"][0]["fields"]] == ["email"]
    assert params["surfaces"][0]["id"] == "form"
    assert params["surfaces"][1]["markdown"] == "# hi"


def test_format_form_submission_truncates_and_ignores_empty():
    from relay_runtime import FORM_SUBMISSION_PREFIX, format_form_submission

    assert format_form_submission({"form_id": "f", "values": {}}) is None
    text = format_form_submission(
        {"form_id": "contact", "title": "Contact", "values": {"note": "x" * 900, "ok": True}}
    )
    assert text.startswith(f"{FORM_SUBMISSION_PREFIX} Contact: ")
    values = json.loads(text.split(": ", 1)[1])
    assert len(values["note"]) == 500 and values["ok"] is True


class EchoModel(ModelProvider):
    def __init__(self) -> None:
        self.last_user = ""

    async def stream_completion(self, session_id, *, messages, tools=None):
        del session_id, tools
        self.last_user = next(m["content"] for m in reversed(messages) if m["role"] == "user")
        yield {"type": "token", "text": "Thanks, I have your details."}

    async def cancel(self, session_id: str) -> None:
        del session_id


@pytest.mark.asyncio
async def test_form_submit_event_runs_model_turn_not_keyword_routes():
    model = EchoModel()
    manager, store = _manager(model)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        # "payment" would hit the payments keyword route if the agent didn't bypass it.
        await manager.submit_client_app_event(
            session.session_id,
            name="ui.form_submit",
            payload={"form_id": "pref", "title": "Preferences", "values": {"payment_day": "15"}},
        )
    finally:
        await manager.end_session(session.session_id)

    assert model.last_user.startswith("[Form submitted] Preferences:")
    events = store.all_events()
    finals = [e for e in events if e.type == EventType.TRANSCRIPT_FINAL]
    assert finals and "payment_day" in finals[-1].payload["text"]
    assert not [e for e in events if e.type == EventType.TOOL_CALL_STARTED]
    assert events[-1].type in (EventType.TURN_COMPLETED, EventType.SESSION_ENDED)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("find rajesh sharma", True),
        ("rajesh sharma.", True),
        ("can you look up rajesh?", True),
        ("compare rajesh's two mortgages side by side", False),
        ("give me a form to update rajesh's contact details", False),
    ],
)
def test_customer_search_intent_requires_explicit_lookup(text, expected):
    from relay_mortgage_agent.agent import _is_customer_search_intent

    assert _is_customer_search_intent(text) is expected


class CapturingModel(ModelProvider):
    def __init__(self) -> None:
        self.system_messages: list[str] = []

    async def stream_completion(self, session_id, *, messages, tools=None):
        del session_id, tools
        self.system_messages = [m["content"] for m in messages if m["role"] == "system"]
        yield {"type": "token", "text": "Received your details."}

    async def cancel(self, session_id: str) -> None:
        del session_id


@pytest.mark.asyncio
async def test_form_submission_turn_tells_model_nothing_was_saved():
    model = CapturingModel()
    manager, _store = _manager(model)
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    try:
        await manager.submit_client_app_event(
            session.session_id,
            name="ui.form_submit",
            payload={"form_id": "contact", "title": "Contact", "values": {"email": "a@b.co"}},
        )
    finally:
        await manager.end_session(session.session_id)

    instructions = " ".join(model.system_messages)
    assert "does not save anything" in instructions
    assert "never say details were saved" in instructions


@pytest.mark.asyncio
async def test_list_customers_tool_offered_to_model_and_returns_everyone():
    from relay_mortgage_agent.tools_local import LocalMortgageToolExecutor

    agent = MortgageServicingAgent(ModelRouter(ScriptedToolModel()))
    assert "list_customers" in agent._model_read_tool_names
    result = await LocalMortgageToolExecutor().execute("s", tool_name="list_customers", arguments={})
    assert {c["name"] for c in result["customers"]} == {"Rajesh Sharma", "Maria Lopez"}
    assert result["total"] == 2
