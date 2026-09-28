"""Mortgage agent — user-facing guardrails and draft date parsing."""

from __future__ import annotations

import pytest
import pytest_asyncio

from relay_mortgage_agent.agent import (
    MortgageServicingAgent,
    _parse_month_name_date,
    _resolve_correction_date_request,
    _try_answer_rate_history_question,
)
from relay_mortgage_agent.response_guardrails import (
    StreamingAssistantGuard,
    sanitize_assistant_text,
)
from relay_runtime import (
    AgentRuntime,
    MemoryEventStore,
    ModelRouter,
    PersistingEventGateway,
    RegistryToolExecutor,
    SessionManager,
    ToolRegistry,
)
from relay_adapter_models_openai import OpenAIProvider
from relay_mortgage_agent.tool_definitions import register_mortgage_tools
from relay_mortgage_agent.tools_local import LocalMortgageToolExecutor


def test_streaming_guard_keeps_spaces_between_chunks():
    guard = StreamingAssistantGuard()
    parts: list[str] = []
    # Force an emit past the hold-back window without stripping inter-chunk spaces.
    guard.push("x" * 92 + " help with")
    parts.append(guard.push(" that. Done."))
    parts.append(guard.flush())
    text = "".join(p for p in parts if p)
    assert "with that" in text
    assert "withthat" not in text


def test_sanitize_strips_internal_sync_language():
    raw = (
        "You're right — I haven't actually synced the screen state here, so the draft still "
        "shows 2025-01-01. I can't directly sync the UI state from here; the routed handler "
        "will apply it."
    )
    cleaned = sanitize_assistant_text(raw)
    assert "routed handler" not in cleaned.lower()
    assert "sync the ui state" not in cleaned.lower()
    assert "haven't actually synced" not in cleaned.lower()


def test_resolve_march_not_january_on_draft():
    ctx = {
        "state": {
            "state": {
                "screen": "correction_draft",
                "correction_draft": {"effective_date": "2025-01-01", "status": "draft"},
            }
        },
        "messages": [],
    }
    assert (
        _resolve_correction_date_request(
            "No. Change it to March, not January.",
            "no. change it to march, not january.",
            ctx,
        )
        == "2025-03-01"
    )


def test_parse_month_name_date_respects_explicit_year():
    ctx = {"state": {"state": {"correction_draft": {"effective_date": "2025-01-01"}}}}
    assert (
        _parse_month_name_date("Use March 2026", "use march 2026", ctx) == "2026-03-01"
    )


@pytest.mark.asyncio
async def test_rate_history_2024_from_shared_state():
    ctx = {
        "state": {
            "state": {
                "screen": "rate_history",
                "rate_history": [
                    {"effective_date": "2023-06-01", "rate": 5.5, "reason": "origination"},
                    {"effective_date": "2024-01-01", "rate": 5.875, "reason": "arm_adjustment"},
                    {"effective_date": "2025-01-01", "rate": 6.125, "reason": "arm_adjustment"},
                ],
            }
        }
    }
    answer = await _try_answer_rate_history_question(
        "So what was it in 2024?",
        "so what was it in 2024?",
        ctx,
        mortgage_id="MORT-2931",
        run_tool=None,
    )
    assert answer
    assert "5.875" in answer
    assert "2024" in answer


@pytest.mark.asyncio
async def test_rate_history_origination_from_shared_state():
    ctx = {
        "state": {
            "state": {
                "screen": "rate_history",
                "rate_history": [
                    {"effective_date": "2023-06-01", "rate": 5.5, "reason": "origination"},
                ],
            }
        }
    }
    answer = await _try_answer_rate_history_question(
        "What was the origination rate?",
        "what was the origination rate?",
        ctx,
        mortgage_id="MORT-2931",
        run_tool=None,
    )
    assert answer
    assert "5.5" in answer
    assert "2023-06-01" in answer


def test_bare_slash_date_on_draft():
    ctx = {
        "state": {"state": {"screen": "correction_draft", "correction_draft": {"status": "draft"}}},
        "messages": [],
    }
    assert _resolve_correction_date_request("03/01/2025", "03/01/2025", ctx) == "2025-03-01"


@pytest_asyncio.fixture
async def manager_with_tools():
    store = MemoryEventStore()
    gateway = PersistingEventGateway(store)
    router = ModelRouter(OpenAIProvider(api_key=None))
    registry = ToolRegistry()
    register_mortgage_tools(registry)
    tools = RegistryToolExecutor(registry=registry, delegate=LocalMortgageToolExecutor())
    runtime = AgentRuntime(model_router=router, agent=MortgageServicingAgent(router), tool_executor=tools)
    manager = SessionManager(event_gateway=gateway, agent_runtime=runtime, session_lock=None)
    yield manager, store
    for session_id in list(manager._sessions):
        await manager.end_session(session_id)


@pytest.mark.asyncio
async def test_march_voice_phrase_updates_draft_state(manager_with_tools):
    manager, _store = manager_with_tools
    session, _ = await manager.create_dev_session(project_id="p", agent_id="a")
    await manager.submit_client_state_snapshot(
        session.session_id,
        {
            "screen": "correction_draft",
            "workflow": "correction_draft",
            "correction_draft": {
                "mortgage_id": "MORT-2931",
                "effective_date": "2025-01-01",
                "status": "draft",
            },
        },
    )
    await manager.submit_user_text(
        session.session_id,
        "Change it to March, not January.",
    )
    assert session.context.state["correction_draft"]["effective_date"] == "2025-03-01"
