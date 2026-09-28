"""Phase 6 — ToolRegistry, parallel executor, stale results."""

from __future__ import annotations

import asyncio

import pytest

from relay_protocol import EventType, RelayEventMetadata
from relay_mortgage_agent.tool_definitions import register_mortgage_tools
from relay_mortgage_agent.tools_local import LocalMortgageToolExecutor
from relay_runtime.context_manager import ContextManager
from relay_runtime.registry_tool_executor import RegistryToolExecutor
from relay_runtime.tool_registry import ToolRegistry
from relay_runtime.trace_manager import TraceManager


class _SlowDelegate:
    async def execute(
        self,
        session_id: str,
        *,
        tool_name: str,
        arguments: dict,
        idempotency_key: str | None = None,
    ) -> dict:
        del session_id, idempotency_key
        await asyncio.sleep(5)
        return {"payments": []}


def test_p06_tc_004_stale_tool_result_ignored():
    ctx = ContextManager()
    ctx.begin_turn("turn-a")
    assert ctx.merge_tool_result(
        turn_id="turn-a",
        tool_call_id="tc-1",
        tool_name="get_payments",
        result={"payments": []},
    )
    ctx.begin_turn("turn-b")
    assert not ctx.merge_tool_result(
        turn_id="turn-a",
        tool_call_id="tc-1",
        tool_name="get_payments",
        result={"payments": [{"month": "2025-09"}]},
    )
    assert len(ctx.tool_results) == 1


@pytest.mark.asyncio
async def test_p06_tc_003_tool_timeout_emits_failed():
    registry = ToolRegistry()
    register_mortgage_tools(registry)
    events: list[str] = []

    async def publish(event) -> None:
        events.append(event.type.value)

    executor = RegistryToolExecutor(
        registry=registry,
        delegate=_SlowDelegate(),
        trace_manager=TraceManager(),
        default_timeout_seconds=0.05,
        read_only_retries=0,
    )
    ctx = ContextManager()
    ctx.begin_turn("turn-1")
    meta = RelayEventMetadata(session_id="s1", sequence=1, source="test")

    result = await executor.execute(
        "s1",
        tool_name="get_payments",
        arguments={"mortgage_id": "MORT-2931", "months": 3},
        turn_id="turn-1",
        publish=publish,
        base_metadata=lambda: meta,
        context=ctx,
    )
    assert result.get("error") == "timeout"
    assert EventType.TOOL_CALL_FAILED.value in events
    assert EventType.TOOL_CALL_STARTED.value in events


@pytest.mark.asyncio
async def test_parallel_tools_emit_activity_and_complete():
    registry = ToolRegistry()
    register_mortgage_tools(registry)
    collected: list[str] = []

    async def publish(event) -> None:
        collected.append(event.type.value)

    executor = RegistryToolExecutor(
        registry=registry,
        delegate=LocalMortgageToolExecutor(),
        trace_manager=TraceManager(),
        default_timeout_seconds=5.0,
    )
    ctx = ContextManager()
    ctx.begin_turn("turn-1")
    meta = RelayEventMetadata(session_id="s1", sequence=1, source="test")

    results = await executor.execute_parallel(
        "s1",
        calls=[
            {"tool_name": "get_payments", "arguments": {"mortgage_id": "MORT-2931", "months": 3}},
            {"tool_name": "get_rate_history", "arguments": {"mortgage_id": "MORT-2931"}},
        ],
        turn_id="turn-1",
        publish=publish,
        base_metadata=lambda: meta,
        context=ctx,
        activity_label="demo",
    )
    assert len(results) == 2
    assert len(results[0].get("payments") or []) == 3
    assert len(results[1].get("rates") or []) >= 1
    assert EventType.ACTIVITY_STARTED.value in collected
    assert EventType.ACTIVITY_COMPLETED.value in collected
    assert collected.count(EventType.TOOL_CALL_COMPLETED.value) == 2


@pytest.mark.asyncio
async def test_commit_correction_blocked():
    registry = ToolRegistry()
    register_mortgage_tools(registry)
    executor = RegistryToolExecutor(
        registry=registry,
        delegate=LocalMortgageToolExecutor(),
        trace_manager=TraceManager(),
    )
    result = await executor.execute(
        "s1",
        tool_name="commit_correction",
        arguments={"mortgage_id": "MORT-2931"},
    )
    assert result.get("error") == "side_effecting_blocked_until_hitl"
