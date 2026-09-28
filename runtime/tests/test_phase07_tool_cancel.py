"""P07-TC-004 — tool results dropped when turn is cancelled."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from relay_runtime.context_manager import ContextManager
from relay_runtime.registry_tool_executor import RegistryToolExecutor
from relay_runtime.tool_registry import ToolClassification, ToolDefinition, ToolRegistry
from relay_runtime.turn_cancellation import TurnCancellation


class _SlowToolDelegate:
    async def execute(
        self,
        session_id: str,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        _ = (session_id, arguments, idempotency_key)
        await asyncio.sleep(0.05)
        return {"ok": True, "tool": tool_name}


@pytest.mark.asyncio
async def test_p07_tc_004_side_effecting_result_not_merged_on_interrupt():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="get_payments",
            classification=ToolClassification.READ_ONLY,
            input_schema={"type": "object", "properties": {}},
            output_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
        )
    )
    executor = RegistryToolExecutor(registry=registry, delegate=_SlowToolDelegate())
    ctx = ContextManager()
    ctx.begin_turn("turn-1")
    cancel = TurnCancellation()

    async def run() -> dict[str, Any]:
        return await executor.execute(
            "sess",
            tool_name="get_payments",
            arguments={},
            turn_id="turn-1",
            context=ctx,
            cancel=cancel,
        )

    task = asyncio.create_task(run())
    await asyncio.sleep(0.01)
    cancel.cancel()
    ctx.active_turn_id = None
    result = await task
    assert result.get("ignored") is True
    assert not ctx.tool_results
