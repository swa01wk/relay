"""In-process read tools when RELAY_MORTGAGE_TOOLS_URL is unset (local pytest / CI)."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from relay_runtime.ports.tools import ToolExecutor

try:
    from mortgage_tools_api import logic
except ImportError:  # pragma: no cover
    logic = None  # type: ignore[assignment]


class LocalMortgageToolExecutor(ToolExecutor):
    async def execute(
        self,
        session_id: str,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        del session_id
        if logic is None:
            return {"error": "mortgage_tools_api_not_installed"}

        slow_ms = int(arguments.get("_slow_ms") or 0)
        if slow_ms > 0:
            await asyncio.sleep(slow_ms / 1000.0)

        if tool_name == "search_customer":
            return logic.search_customer(str(arguments.get("query", "")))
        if tool_name == "get_mortgage":
            return logic.get_mortgage(str(arguments.get("mortgage_id", "")))
        if tool_name == "get_payments":
            return logic.get_payments(
                str(arguments.get("mortgage_id", "")),
                months=int(arguments.get("months") or 3),
            )
        if tool_name == "get_rate_history":
            return logic.get_rate_history(str(arguments.get("mortgage_id", "")))
        if tool_name == "get_audit_history":
            return logic.get_audit_history(
                str(arguments.get("mortgage_id", "")),
                limit=int(arguments.get("limit") or 10),
            )
        if tool_name == "calculate_adjustment":
            return logic.calculate_adjustment(
                str(arguments.get("mortgage_id", "")),
                new_rate=float(arguments.get("new_rate") or 0),
            )
        if tool_name == "prepare_correction":
            proposed = arguments.get("proposed_rate")
            return logic.prepare_correction(
                str(arguments.get("mortgage_id", "")),
                proposed_rate=float(proposed) if proposed is not None else None,
                effective_date=(
                    str(arguments.get("effective_date"))
                    if arguments.get("effective_date")
                    else None
                ),
                slow_ms=int(arguments.get("_slow_ms") or 0),
            )
        if tool_name == "recalculate_correction_draft":
            proposed = arguments.get("proposed_rate")
            return logic.recalculate_correction_draft(
                str(arguments.get("mortgage_id", "")),
                effective_date=str(arguments.get("effective_date", "")),
                proposed_rate=float(proposed) if proposed is not None else None,
            )
        if tool_name == "commit_correction":
            return logic.commit_correction(
                str(arguments.get("mortgage_id", "")),
                effective_date=str(arguments.get("effective_date", "")),
                proposed_rate=float(arguments.get("proposed_rate") or 0),
                auth_token=os.environ.get(
                    "RELAY_MORTGAGE_COMMIT_TOKEN",
                    os.environ.get("MORTGAGE_COMMIT_TOKEN", "dev-mortgage-commit"),
                ),
                idempotency_key=idempotency_key,
            )
        if tool_name == "verify_correction":
            commit_id = arguments.get("commit_id")
            return logic.verify_correction(
                str(arguments.get("mortgage_id", "")),
                commit_id=str(commit_id) if commit_id else None,
            )
        return {"error": f"unknown_tool:{tool_name}"}
